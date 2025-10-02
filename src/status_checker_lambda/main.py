import os
import json
import boto3
from decimal import Decimal

# Helper class to serialize DynamoDB's Decimal type into float for JSON responses
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize DynamoDB client
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def handler(event, context):
    """
    This function is triggered by API Gateway. It reads a job_id from the URL path
    and returns the current status of that job from the DynamoDB table.
    """
    print(f"Status-Checker handler started with event: {event}")
    
    try:
        # 1. Get the job_id from the API Gateway path parameters
        job_id = event['pathParameters']['job_id']
        print(f"Checking status for job_id: {job_id}")
        
        # 2. Query the DynamoDB table for the specific job item
        response = table.get_item(
            Key={'job_id': job_id}
        )
        
        item = response.get('Item')
        
        # 3. If the job is not found, return a 404 Not Found error
        if not item:
            print(f"Job with id {job_id} not found.")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Job {job_id} not found'})
            }

        # 4. If found, calculate progress and determine the final status
        total = item.get('total_batches', 0)
        processed = item.get('processed_batches', 0)
        
        if total > 0:
            item['progress_percentage'] = round((processed / total) * 100, 2)
        else:
            item['progress_percentage'] = 0
            
        # If processing is complete, update the status field for clarity
        if processed >= total and item.get('status') == 'IN_PROGRESS':
            item['status'] = 'PROCESSING_COMPLETE'

        print(f"Job status found: {item}")
        
        return {
            'statusCode': 200,
            # Use the custom encoder to handle DynamoDB's numeric types
            'body': json.dumps(item, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"Error in Status-Checker Lambda: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'An internal error occurred.'})
        }