import os
import awswrangler as wr

# Get bucket names from environment variables set in Terraform
SILVER_BUCKET_NAME = os.environ['SILVER_BUCKET_NAME']
GOLD_BUCKET_NAME = os.environ['GOLD_BUCKET_NAME']

# Define the folder prefix where the intermediate files are
SILVER_PROCESSED_PREFIX = "processed-batches/"
GOLD_OUTPUT_FILENAME = "final_reviews.parquet"

def handler(event, context):
    """
    This function is triggered when all processing is done.
    It reads all the small Parquet files from the Silver bucket,
    merges them into a single DataFrame, and saves it to the Gold bucket.
    """
    print("Stitcher handler started...")
    
    # Construct the S3 paths
    silver_path = f"s3://{SILVER_BUCKET_NAME}/{SILVER_PROCESSED_PREFIX}"
    gold_path = f"s3://{GOLD_BUCKET_NAME}/{GOLD_OUTPUT_FILENAME}"

    try:
        # 1. Read all Parquet files from the Silver "processed-batches" folder
        # awswrangler read them all and concatenate into one DataFrame
        print(f"Reading all partial files from {silver_path}...")
        df_final = wr.s3.read_parquet(path=silver_path)
        print(f"Successfully loaded and merged {len(df_final)} total rows.")

        # 2. Write the final, unified DataFrame to the Gold bucket
        print(f"Writing final file to {gold_path}...")
        wr.s3.to_parquet(df=df_final, path=gold_path, index=False)
        print("Final file successfully saved to Gold layer.")
        
        # 3. Clean up the intermediate files
        print(f"Cleaning up intermediate files from {silver_path}...")
        wr.s3.delete_objects(path=silver_path)
        print("Cleanup complete.")

        return {
            'statusCode': 200,
            'body': f'Successfully stitched {len(df_final)} rows and saved to Gold bucket.'
        }
        
    except Exception as e:
        print(f"Error in Stitcher Lambda: {e}")
        # Monitor for Lambda invocation fails.
        raise e