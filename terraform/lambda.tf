# --- ECR Repository ---
resource "aws_ecr_repository" "processor_lambda_repo" {
  name = "reviewlens-processor-lambda-repo"
}
resource "aws_ecr_repository" "stitcher_lambda_repo" {
  name = "reviewlens-stitcher-lambda-repo"
}

# --- IAM Roles and Policies (Separate for each function) ---

# --- LAMBDA SPLITTER ROLE ---
resource "aws_iam_role" "splitter_lambda_role" {
  name               = "reviewlens-splitter-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_role_policy_attachment" "splitter_basic_execution" {
  role       = aws_iam_role.splitter_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
resource "aws_iam_role_policy_attachment" "splitter_policy_attachment" {
  role       = aws_iam_role.splitter_lambda_role.name
  policy_arn = aws_iam_policy.splitter_policy.arn
}
resource "aws_iam_policy" "splitter_policy" {
  name   = "reviewlens-splitter-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      { Action = ["s3:GetObject"], Effect = "Allow", Resource = ["${aws_s3_bucket.bronze_bucket.arn}/*"] },
      { Action = ["sqs:SendMessage"], Effect = "Allow", Resource = [aws_sqs_queue.reviews_queue.arn] }
    ]
  })
}

# --- LAMBDA PROCESSOR ROLE ---
resource "aws_iam_role" "processor_lambda_role" {
  name               = "reviewlens-processor-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_role_policy_attachment" "processor_basic_execution" {
  role       = aws_iam_role.processor_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
resource "aws_iam_role_policy_attachment" "processor_policy_attachment" {
  role       = aws_iam_role.processor_lambda_role.name
  policy_arn = aws_iam_policy.processor_policy.arn
}
resource "aws_iam_policy" "processor_policy" {
  name   = "reviewlens-processor-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      { Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Effect = "Allow", Resource = [aws_sqs_queue.reviews_queue.arn] },
      { Action = ["s3:PutObject"], Effect = "Allow", Resource = ["${aws_s3_bucket.silver_bucket.arn}/*"] }
    ]
  })
}

# --- LAMBDA STITCHER ROLE ---
resource "aws_iam_role" "stitcher_lambda_role" {
  name               = "reviewlens-stitcher-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}
resource "aws_iam_role_policy_attachment" "stitcher_basic_execution" {
  role       = aws_iam_role.stitcher_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
resource "aws_iam_role_policy_attachment" "stitcher_policy_attachment" {
  role       = aws_iam_role.stitcher_lambda_role.name
  policy_arn = aws_iam_policy.stitcher_policy.arn
}
resource "aws_iam_policy" "stitcher_policy" {
  name   = "reviewlens-stitcher-permissions"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      { Action = ["s3:GetObject", "s3:ListBucket", "s3:DeleteObject"], Effect = "Allow", Resource = [aws_s3_bucket.silver_bucket.arn, "${aws_s3_bucket.silver_bucket.arn}/*"] },
      { Action = ["s3:PutObject"], Effect = "Allow", Resource = ["${aws_s3_bucket.gold_bucket.arn}/*"] }
    ]
  })
}

# --- Data source for Lambda assume role policy ---
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- ZIP Archive Creation and Upload to S3 ---
data "archive_file" "splitter_zip" {
  type        = "zip"
  source_dir  = "../src/splitter_lambda/"
  output_path = "../dist/splitter_lambda.zip"
}
resource "aws_s3_object" "splitter_zip_object" {
  bucket = aws_s3_bucket.lambda_code_bucket.id
  key    = "splitter_lambda.zip"
  source = data.archive_file.splitter_zip.output_path
  etag   = data.archive_file.splitter_zip.output_md5
}

# --- Lambda Function #1: The Splitter (from S3 .zip) ---
resource "aws_lambda_function" "splitter_lambda" {
  function_name = "reviewlens-splitter-lambda"
  role          = aws_iam_role.splitter_lambda_role.arn
  package_type  = "Zip"
  handler       = "main.handler"
  runtime       = "python3.9"

  s3_bucket        = aws_s3_bucket.lambda_code_bucket.id
  s3_key           = aws_s3_object.splitter_zip_object.key
  source_code_hash = data.archive_file.splitter_zip.output_base64sha256

  timeout     = 120
  memory_size = 512
  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.reviews_queue.url
    }
  }
}

# --- Lambda Function #2: The Processor (using Docker) ---
resource "aws_lambda_function" "processor_lambda" {
  function_name = "reviewlens-processor-lambda"
  role          = aws_iam_role.processor_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.processor_lambda_repo.repository_url}:latest"
  timeout       = 900
  memory_size   = 3008
  environment {
    variables = {
      HF_HOME            = "/tmp/huggingface_cache"
      SILVER_BUCKET_NAME = aws_s3_bucket.silver_bucket.bucket
    }
  }
}

# --- Lambda Function #3: The Stitcher (using Docker) ---
resource "aws_lambda_function" "stitcher_lambda" {
  function_name = "reviewlens-stitcher-lambda"
  role          = aws_iam_role.stitcher_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.stitcher_lambda_repo.repository_url}:latest" # <--- Modificato

  timeout     = 300
  memory_size = 2048
  environment {
    variables = {
      SILVER_BUCKET_NAME = aws_s3_bucket.silver_bucket.bucket
      GOLD_BUCKET_NAME   = aws_s3_bucket.gold_bucket.bucket
    }
  }
}

# --- Triggers ---
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

resource "aws_lambda_event_source_mapping" "sqs_to_processor_trigger" {
  event_source_arn = aws_sqs_queue.reviews_queue.arn
  function_name    = aws_lambda_function.processor_lambda.arn
  batch_size       = 1
}

resource "aws_sns_topic_subscription" "stitcher_sns_subscription" {
  topic_arn = aws_sns_topic.stitching_topic.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.stitcher_lambda.arn
}
resource "aws_lambda_permission" "allow_sns_to_invoke_stitcher" {
  statement_id  = "AllowSNSInvokeStitcher"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stitcher_lambda.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.stitching_topic.arn
}