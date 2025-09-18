# --- ECR Repositories ---
resource "aws_ecr_repository" "splitter_lambda_repo" {
  name = "reviewlens-splitter-lambda-repo"
}

resource "aws_ecr_repository" "processor_lambda_repo" {
  name = "reviewlens-processor-lambda-repo"
}


# --- IAM Role for the Splitter Lambda ---
# This role only needs to read from S3 Bronze and write to SQS
resource "aws_iam_role" "splitter_lambda_role" {
  name = "reviewlens-splitter-lambda-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# Attaches basic execution policy for logs
resource "aws_iam_role_policy_attachment" "splitter_basic_execution" {
  role       = aws_iam_role.splitter_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Custom policy for the Splitter
resource "aws_iam_policy" "splitter_policy" {
  name   = "reviewlens-splitter-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Action   = ["s3:GetObject"],
        Effect   = "Allow",
        Resource = ["${aws_s3_bucket.bronze_bucket.arn}/*"]
      },
      {
        Action   = ["sqs:SendMessage"],
        Effect   = "Allow",
        Resource = [aws_sqs_queue.reviews_queue.arn]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "splitter_policy_attachment" {
  role       = aws_iam_role.splitter_lambda_role.name
  policy_arn = aws_iam_policy.splitter_policy.arn
}


# --- IAM Role for the Processor Lambda ---
# This role now needs to read from SQS and write to S3 Silver
resource "aws_iam_role" "processor_lambda_role" {
  name               = "reviewlens-processor-lambda-role" # Renamed for clarity
  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "processor_basic_execution" {
  role       = aws_iam_role.processor_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "processor_policy" {
  name   = "reviewlens-processor-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
        Effect   = "Allow",
        Resource = [aws_sqs_queue.reviews_queue.arn]
      },
      {
        Action   = ["s3:PutObject"],
        Effect   = "Allow",
        Resource = ["${aws_s3_bucket.silver_bucket.arn}/*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "processor_policy_attachment" {
  role       = aws_iam_role.processor_lambda_role.name
  policy_arn = aws_iam_policy.processor_policy.arn
}


# --- Lambda Function #1: The Splitter ---
resource "aws_lambda_function" "splitter_lambda" {
  function_name = "reviewlens-splitter-lambda"
  role          = aws_iam_role.splitter_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.splitter_lambda_repo.repository_url}:latest"
  timeout       = 120 # 2 minutes is plenty to split a large file
  memory_size   = 512
}

# --- Lambda Function #2: The Processor ---
resource "aws_lambda_function" "processor_lambda" {
  function_name = "reviewlens-processor-lambda"
  role          = aws_iam_role.processor_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.processor_lambda_repo.repository_url}:latest"
  timeout       = 900
  memory_size   = 3008

  environment {
    variables = {
      HF_HOME = "/tmp/huggingface_cache"
      SILVER_BUCKET_NAME = aws_s3_bucket.silver_bucket.bucket
    }
  }
}


# --- Trigger #1: S3 to Splitter Lambda ---
resource "aws_s3_bucket_notification" "bronze_to_splitter_notification" {
  bucket = aws_s3_bucket.bronze_bucket.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.splitter_lambda.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".csv"
  }
  depends_on = [aws_lambda_permission.allow_s3_to_invoke_splitter]
}

resource "aws_lambda_permission" "allow_s3_to_invoke_splitter" {
  statement_id  = "AllowS3InvokeSplitter"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.splitter_lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.bronze_bucket.arn
}

# --- Trigger #2: SQS to Processor Lambda ---
resource "aws_lambda_event_source_mapping" "sqs_to_processor_trigger" {
  event_source_arn = aws_sqs_queue.reviews_queue.arn
  function_name    = aws_lambda_function.processor_lambda.arn
  batch_size       = 1 # Process one message (one batch of reviews) at a time
}