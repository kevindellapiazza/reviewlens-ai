# --- S3 (Simple Storage Service) ---
# Create S3 buckets.
provider "aws" {
  region = "eu-west-1"
}

resource "aws_s3_bucket" "bronze_bucket" {
  bucket = "reviewlens-bronze-bucket-kevin"
}

resource "aws_s3_bucket" "silver_bucket" {
  bucket = "reviewlens-silver-bucket-kevin"
}

resource "aws_s3_bucket" "gold_bucket" {
  bucket = "reviewlens-gold-bucket-kevin"
}

# --- S3 Bucket for Lambda Code Artifacts ---
resource "aws_s3_bucket" "lambda_code_bucket" {
  # Use the random_id to ensure the bucket name is always unique
  bucket = "reviewlens-lambda-code-bucket-${random_id.id.hex}"
}

resource "random_id" "id" {
  byte_length = 8
}