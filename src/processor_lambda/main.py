import os
import json
import pandas as pd
from transformers import pipeline
import awswrangler as wr
import boto3

# --- Load the AI Model (once, during a cold start) ---
print("Loading Sentiment Analysis model...")
sentiment_pipeline = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
print("Model loaded successfully!")

# --- Initialize clients and environment variables ---
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
SILVER_BUCKET_NAME = os.environ['SILVER_BUCKET_NAME']
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def handler(event, context):
    """
    This function is triggered by an SQS message. It reads a batch of reviews,
    enriches it with AI sentiment analysis, saves the partial result to the Silver bucket,
    and updates the job status in DynamoDB.
    """
    print("Processor handler started...")
    
    # An SQS event can contain multiple messages, so we iterate through them
    for record in event['Records']:
        message_body_str = record['body']
        
        # --- 1. Parse the incoming SQS message ---
        message_data = json.loads(message_body_str)
        job_id = message_data['job_id']
        data_json = message_data['data']
        
        df = pd.read_json(data_json, orient='split')
        print(f"Successfully loaded a batch of {len(df)} rows from SQS for job {job_id}.")

        # --- 2. Data Cleaning and AI Analysis Logic ---
        df_cleaned = df.drop('Unnamed: 0', axis=1, errors='ignore')
        df_cleaned.dropna(subset=['Review Text'], inplace=True)
        df_cleaned['Title'] = df_cleaned['Title'].fillna('')
        df_cleaned['full_review_text'] = df_cleaned['Title'] + ' ' + df_cleaned['Review Text']
        try:
            df_cleaned.dropna(subset=['Division Name', 'Department Name', 'Class Name'], inplace=True)
        except KeyError:
            print("Category columns not found, proceeding without them.")
            pass
        print("Data cleaning completed for the batch.")

        def get_sentiment(text):
            result = sentiment_pipeline(text[:512])
            return result[0]['label'], result[0]['score']

        sentiments = df_cleaned['full_review_text'].apply(get_sentiment)
        df_cleaned[['sentiment_label', 'sentiment_score']] = pd.DataFrame(sentiments.tolist(), index=df_cleaned.index)
        print("Sentiment analysis completed for the batch.")
        
        # --- 3. Save the partial result to S3 with a unique name ---
        request_id = context.aws_request_id
        # Organize outputs in a subfolder named after the job_id
        output_path = f"s3://{SILVER_BUCKET_NAME}/processed-batches/{job_id}/{request_id}.parquet"

        final_columns = [
            'Clothing ID', 'Age', 'Rating', 'Recommended IND', 'Positive Feedback Count',
            'Division Name', 'Department Name', 'Class Name', 'full_review_text',
            'sentiment_label', 'sentiment_score'
        ]
        df_final = df_cleaned[[col for col in final_columns if col in df_cleaned.columns]]
        
        wr.s3.to_parquet(df=df_final, path=output_path, index=False)
        print(f"Successfully saved batch to {output_path}")

        # --- 4. Atomically update the job status in DynamoDB ---
        table.update_item(
            Key={'job_id': job_id},
            UpdateExpression="ADD processed_batches :inc", # Increment the counter
            ExpressionAttributeValues={":inc": 1}
        )
        print(f"Incremented processed_batches counter for job {job_id}.")

    return {'statusCode': 200, 'body': 'Batch processed successfully!'}