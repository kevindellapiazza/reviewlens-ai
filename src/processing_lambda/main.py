import pandas as pd
from transformers import pipeline
import awswrangler as wr

# --- 1. Load the AI Model (once, during the Lambda's "cold start") ---
# By defining this outside the handler, we ensure the model is loaded only when
# the Lambda container starts up, not on every single invocation. This is a key optimization.
print("Loading Sentiment Analysis model...")
sentiment_pipeline = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
print("Model loaded successfully!")


# --- 2. The Main Handler Function (the "brain" of our Lambda) ---
def handler(event, context):
    """
    This is the main function that AWS Lambda will execute every time it's triggered.
    """
    print("Handler function started...")
    
    # --- 3. Get the uploaded file info from the S3 event ---
    # The 'event' object contains information about what triggered the Lambda.
    # We extract the bucket name and the file name (key) from it.
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    file_key = event['Records'][0]['s3']['object']['key']
    input_path = f"s3://{bucket_name}/{file_key}"
    
    print(f"New file detected in Bronze bucket: {input_path}")
    
    # --- 4. Load, Clean, and Analyze (Our "Recipe") ---
    try:
        # Use awswrangler to read the CSV file directly from S3 into a Pandas DataFrame
        df = wr.s3.read_csv(path=input_path)
        print(f"Successfully loaded {len(df)} rows from the CSV.")

        # --- Data Cleaning (same steps as the notebook) ---
        # Use errors='ignore' in case the column doesn't exist in a future file
        df_cleaned = df.drop('Unnamed: 0', axis=1, errors='ignore')
        df_cleaned.dropna(subset=['Review Text'], inplace=True)
        df_cleaned['Title'] = df_cleaned['Title'].fillna('')
        df_cleaned['full_review_text'] = df_cleaned['Title'] + ' ' + df_cleaned['Review Text']
        df_cleaned.dropna(subset=['Division Name', 'Department Name', 'Class Name'], inplace=True)
        print("Data cleaning completed.")

        # --- Sentiment Analysis ---
        # Helper function to run the model and handle long texts
        def get_sentiment(text):
            # Models have a maximum token limit. We truncate the text to the first 512 tokens.
            result = sentiment_pipeline(text[:512])
            # The result is a list with a dictionary, we extract the label and score
            return result[0]['label'], result[0]['score']

        # Apply the function to the text column
        sentiments = df_cleaned['full_review_text'].apply(get_sentiment)
        # Create two new columns from the results
        df_cleaned[['sentiment_label', 'sentiment_score']] = pd.DataFrame(sentiments.tolist(), index=df_cleaned.index)
        print("Sentiment analysis completed.")
        
        # --- 5. Save the Result to the Silver Bucket ---
        output_bucket = "reviewlens-silver-bucket-kevin"
        output_path = f"s3://{output_bucket}/processed_reviews.parquet"

        # Select the final columns to save
        final_columns = [
            'Clothing ID', 'Age', 'Rating', 'Recommended IND',
            'Positive Feedback Count', 'Division Name', 'Department Name',
            'Class Name', 'full_review_text', 'sentiment_label', 'sentiment_score'
        ]
        df_final = df_cleaned[final_columns]
        
        # Use awswrangler to write the final DataFrame to S3 as a Parquet file
        wr.s3.to_parquet(df=df_final, path=output_path, index=False)
        
        print(f"Successfully processed and saved data to {output_path}")
        
        # Return a success message
        return {
            'statusCode': 200,
            'body': 'File processed successfully!'
        }

    except Exception as e:
        print(f"Error processing file: {e}")
        # Raising the exception will cause the Lambda invocation to fail, which can be monitored.
        raise e