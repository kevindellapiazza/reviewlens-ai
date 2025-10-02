import os
import boto3
import pandas as pd
import json
import uuid

# Retrieve environment variables set by Terraform
SQS_QUEUE_URL = os.environ['SQS_QUEUE_URL']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
BATCH_SIZE = 200  # Number of rows per SQS message/batch

# Initialize AWS clients outside the handler for performance (reused in warm starts)
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def handler(event, context):
    """
    This function is triggered by an S3 upload. It reads a CSV file in chunks,
    sends each chunk as a message to an SQS queue, and creates a record
    in DynamoDB to track the job's status.
    """
    print("Splitter handler started...")
    
    # 1. Get file information from the S3 trigger event
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    file_key = event['Records'][0]['s3']['object']['key']
    print(f"Processing file: s3://{bucket_name}/{file_key}")

    # --- 2. Create a unique Job ID for this processing task ---
    job_id = str(uuid.uuid4())
    print(f"Generated new Job ID: {job_id}")

    try:
        # 3. Read the file once to count total rows and calculate total chunks
        s3_object = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        row_count = 0
        # Use a chunksize iterator to avoid loading the entire file into memory
        with pd.read_csv(s3_object['Body'], chunksize=BATCH_SIZE) as csv_iterator:
            for chunk in csv_iterator:
                row_count += len(chunk)
        total_chunks = -(-row_count // BATCH_SIZE)  # Ceiling division
        
        print(f"File has {row_count} rows, which will be split into {total_chunks} chunks.")

        # --- 4. Create the job entry in the DynamoDB table ---
        table.put_item(
            Item={
                'job_id': job_id,
                'status': 'IN_PROGRESS',
                'total_batches': total_chunks,
                'processed_batches': 0,
                'source_file': f"s3://{bucket_name}/{file_key}"
            }
        )
        print(f"Job {job_id} registered in DynamoDB.")

        # 5. Re-read the S3 object to stream and send messages
        s3_object = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        csv_iterator = pd.read_csv(s3_object['Body'], chunksize=BATCH_SIZE)
        
        chunk_num = 0
        for chunk in csv_iterator:
            chunk_num += 1
            print(f"Sending chunk #{chunk_num}...")

            # --- 6. Add the job_id to each message for tracking ---
            message_data = {
                'job_id': job_id,
                'data': chunk.to_json(orient='split')
            }
            
            sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps(message_data)
            )
        
        print(f"Successfully sent {chunk_num} messages to SQS for job {job_id}.")
        return {'statusCode': 200, 'body': f'Job {job_id} started with {chunk_num} batches.'}

    except Exception as e:
        print(f"Error in Splitter Lambda: {e}")
        raise e