import os
import json
import pandas as pd
from transformers import pipeline
import awswrangler as wr

# This model loading part is correct and stays the same
print("Loading Sentiment Analysis model...")
sentiment_pipeline = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
print("Model loaded successfully!")

def handler(event, context):
    """
    This function is triggered by an SQS message. It reads a batch of reviews from the message,
    processes them, and saves the result as a unique Parquet file in the Silver bucket.
    """
    print("Processor handler started...")
    silver_bucket_name = os.environ['SILVER_BUCKET_NAME']
    
    # Loop through all messages received in the event (usually just one with our config)
    for record in event['Records']:
        # 1. Read the data from the SQS message body
        message_body = record['body']
        # The body is a JSON string, convert it back to a Pandas DataFrame
        df = pd.read_json(message_body, orient='split')
        print(f"Successfully loaded a batch of {len(df)} rows from SQS.")

        # The core logic for cleaning and AI analysis is IDENTICAL
        df_cleaned = df.drop('Unnamed: 0', axis=1, errors='ignore')
        df_cleaned.dropna(subset=['Review Text'], inplace=True)
        df_cleaned['Title'] = df_cleaned['Title'].fillna('')
        df_cleaned['full_review_text'] = df_cleaned['Title'] + ' ' + df_cleaned['Review Text']
        df_cleaned.dropna(subset=['Division Name', 'Department Name', 'Class Name'], inplace=True)
        print("Data cleaning completed for the batch.")

        def get_sentiment(text):
            result = sentiment_pipeline(text[:512])
            return result[0]['label'], result[0]['score']

        sentiments = df_cleaned['full_review_text'].apply(get_sentiment)
        df_cleaned[['sentiment_label', 'sentiment_score']] = pd.DataFrame(sentiments.tolist(), index=df_cleaned.index)
        print("Sentiment analysis completed for the batch.")
        
        # We use the unique ID of this invocation to create a unique filename
        request_id = context.aws_request_id
        output_path = f"s3://{silver_bucket_name}/processed-batches/{request_id}.parquet"

        final_columns = [
            'Clothing ID', 'Age', 'Rating', 'Recommended IND',
            'Positive Feedback Count', 'Division Name', 'Department Name',
            'Class Name', 'full_review_text', 'sentiment_label', 'sentiment_score'
        ]
        # Filter for final columns, handling potential missing columns
        df_final = df_cleaned[[col for col in final_columns if col in df_cleaned.columns]]
        
        wr.s3.to_parquet(df=df_final, path=output_path, index=False)
        
        print(f"Successfully processed batch and saved data to {output_path}")

    return {
        'statusCode': 200,
        'body': 'Batch processed successfully!'
    }