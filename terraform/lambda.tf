# --- ECR (Elastic Container Registry) Repository ---
# Creates a private Docker container registry to store our Lambda image.
resource "aws_ecr_repository" "lambda_repo" {
  name = "reviewlens-lambda-repo"
}

# --- IAM Role and Policies for Lambda Execution ---
# Defines the identity and permissions for the Lambda function.
resource "aws_iam_role" "lambda_exec_role" {
  name = "reviewlens-lambda-execution-role"

  # Trust policy allowing the Lambda service to assume this role.
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Attaches the AWS-managed policy for basic Lambda execution permissions (e.g., writing to CloudWatch Logs).
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Custom IAM policy to grant the Lambda function permissions to read from the Bronze bucket and write to the Silver bucket.
resource "aws_iam_policy" "lambda_s3_policy" {
  name        = "reviewlens-lambda-s3-policy"
  description = "Allows Lambda function to access project S3 buckets"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      Effect = "Allow",
      # Permissions are granted specifically on our two project buckets.
      Resource = [
        aws_s3_bucket.bronze_bucket.arn,
        "${aws_s3_bucket.bronze_bucket.arn}/*",
        aws_s3_bucket.silver_bucket.arn,
        "${aws_s3_bucket.silver_bucket.arn}/*"
      ]
    }]
  })
}

# Attaches the custom S3 policy to the Lambda execution role.
resource "aws_iam_role_policy_attachment" "lambda_s3_attachment" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_s3_policy.arn
}

# --- AWS Lambda Function ---
# Defines the Lambda function itself, configured to run from a container image.
resource "aws_lambda_function" "processing_lambda" {
  function_name = "reviewlens-processing-lambda"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"

  # Performance settings for a memory and time-intensive AI task.
  timeout     = 900
  memory_size = 3008

  # Point the Lambda to our specific image in our ECR repository.
  image_uri = "${aws_ecr_repository.lambda_repo.repository_url}:latest"

  # Add this block for environment variables
  environment {
    variables = {
      # Use the writable /tmp directory for its cache
      HF_HOME = "/tmp/huggingface_cache"
    }
  }
}

# --- S3 Trigger Configuration ---
# Configures the S3 bucket to trigger the Lambda function upon new object creation.
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.bronze_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.processing_lambda.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".csv" # The trigger will only fire for .csv files.
  }

  # This dependency ensures the Lambda permission is created before the notification is attached.
  depends_on = [aws_lambda_permission.allow_s3_invoke]
}

# Grants the S3 service permission to invoke the Lambda function.
resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.processing_lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.bronze_bucket.arn
}