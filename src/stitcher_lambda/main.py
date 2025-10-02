import os
import json
import awswrangler as wr
import boto3

# Initialize clients and environment variables
SILVER_BUCKET_NAME = os.environ['SILVER_BUCKET_NAME']
GOLD_BUCKET_NAME = os.environ['GOLD_BUCKET_NAME']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def handler(event, context):
    """
    This function is triggered by API Gateway. It expects a job_id, merges all
    partial Parquet files from the Silver bucket for that job, saves the final
    result to the Gold bucket, and updates the final job status in DynamoDB.
    """
    print(f"Stitcher handler started with event: {event}")

    # 1. Extract job_id from the API Gateway request body
    try:
        body = json.loads(event.get('body', '{}'))
        job_id = body['job_id']
        print(f"Starting stitching process for job_id: {job_id}")
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error: 'job_id' not found or invalid JSON body. {e}")
        return {'statusCode': 400, 'body': json.dumps({'error': "Invalid request, 'job_id' is missing from the body."})}

    # Define the S3 paths specific to this job
    silver_path = f"s3://{SILVER_BUCKET_NAME}/processed-batches/{job_id}/"
    gold_path = f"s3://{GOLD_BUCKET_NAME}/{job_id}.parquet"

    try:
        # 2. Update status in DynamoDB to "STITCHING"
        table.update_item(
            Key={'job_id': job_id},
            UpdateExpression="SET #st = :s",
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={':s': 'STITCHING'}
        )
        
        # 3. Read and merge all partial Parquet files from the job's folder
        print(f"Reading all partial files from {silver_path}...")
        df_final = wr.s3.read_parquet(path=silver_path)
        print(f"Successfully loaded and merged {len(df_final)} total rows.")

        # 4. Write the unified DataFrame to the Gold bucket
        print(f"Writing final file to {gold_path}...")
        wr.s3.to_parquet(df=df_final, path=gold_path, index=False)
        print("Final file successfully saved to Gold layer.")
        
        # 5. Clean up the intermediate files from the Silver bucket
        print(f"Cleaning up intermediate files from {silver_path}...")
        wr.s3.delete_objects(path=silver_path)
        print("Cleanup complete.")
        
        # 6. Set the final status in DynamoDB to "COMPLETED"
        table.update_item(
            Key={'job_id': job_id},
            UpdateExpression="SET #st = :s",
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={':s': 'COMPLETED'}
        )
        print(f"Job {job_id} marked as COMPLETED.")

        return {
            'statusCode': 200,
            'body': json.dumps({'message': f'Job {job_id} completed successfully. Final file available at {gold_path}.'})
        }
        
    except Exception as e:
        print(f"Error in Stitcher Lambda: {e}")
        # In case of an error, set the status to FAILED to allow for investigation
        table.update_item(
            Key={'job_id': job_id},
            UpdateExpression="SET #st = :s",
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={':s': 'STITCHING_FAILED'}
        )
        raise e