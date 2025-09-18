# --- SQS (Simple Queue Service) ---
# Creates a standard queue to hold the review batches.
resource "aws_sqs_queue" "reviews_queue" {
  name = "reviewlens-reviews-queue"
  message_retention_seconds = 345600
  visibility_timeout_seconds  = 901
}