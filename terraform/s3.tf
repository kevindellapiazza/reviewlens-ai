# --- Provider Configuration ---
provider "aws" {
  region = "eu-west-1"
}

# --- Data Layer Buckets ---

# Bronze Layer: For raw, unmodified data ingestion.
resource "aws_s3_bucket" "bronze_bucket" {
  bucket = "reviewlens-bronze-bucket-kevin"
}

# Silver Layer: For intermediate, cleaned, and enriched data (in batches).
resource "aws_s3_bucket" "silver_bucket" {
  bucket = "reviewlens-silver-bucket-kevin"
}

# Gold Layer: For the final, aggregated, business-ready data.
resource "aws_s3_bucket" "gold_bucket" {
  bucket = "reviewlens-gold-bucket-kevin"
}


# --- S3 Lifecycle Policy for Silver Bucket ---
# Automatically cleans up intermediate batch files after 7 days to manage costs and clutter.
resource "aws_s3_bucket_lifecycle_configuration" "silver_bucket_lifecycle" {
  bucket = aws_s3_bucket.silver_bucket.id

  rule {
    id     = "cleanup-processed-batches"
    status = "Enabled"

    filter {
      prefix = "processed-batches/"
    }

    expiration {
      days = 7
    }
  }
}


# --- S3 Bucket for Lambda Code Artifacts ---

# Helper to generate a unique suffix for the bucket name, preventing global naming conflicts.
resource "random_id" "id" {
  byte_length = 8
}

# This bucket serves as a staging area for large Lambda .zip packages.
resource "aws_s3_bucket" "lambda_code_bucket" {
  bucket = "reviewlens-lambda-code-bucket-${random_id.id.hex}"
}