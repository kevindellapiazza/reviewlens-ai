import os
import boto3
import pandas as pd

# Get the SQS queue URL from an environment variable set in Terraform
SQS_QUEUE_URL = os.environ['SQS_QUEUE_URL']
BATCH_SIZE = 200  # How many rows per message/batch

# Initialize AWS clients outside the handler for efficiency
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')

def handler(event, context):
    """
    This function is triggered by an S3 upload. It reads the CSV file in chunks
    and sends each chunk as a message to an SQS queue.
    """
    print("Splitter handler started...")

    # 1. Get the uploaded file info from the S3 event
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    file_key = event['Records'][0]['s3']['object']['key']
    print(f"Processing file: s3://{bucket_name}/{file_key}")

    # 2. Read the large CSV from S3 in chunks to avoid memory issues
    try:
        # Get the object from S3
        s3_object = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        
        # Use pandas' chunksize iterator to read the file piece by piece
        csv_iterator = pd.read_csv(s3_object['Body'], chunksize=BATCH_SIZE)
        
        chunk_num = 0
        for chunk in csv_iterator:
            chunk_num += 1
            print(f"Processing chunk #{chunk_num} with {len(chunk)} rows...")

            # 3. Convert the chunk (DataFrame) to a JSON string
            message_body = chunk.to_json(orient='split')

            # 4. Send the chunk as a message to the SQS queue
            sqs_client.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=message_body
            )
        
        print(f"Successfully sent {chunk_num} messages to SQS.")
        return {
            'statusCode': 200,
            'body': f'Successfully processed {file_key} and sent {chunk_num} messages to SQS.'
        }

    except Exception as e:
        print(f"Error in Splitter Lambda: {e}")
        raise e