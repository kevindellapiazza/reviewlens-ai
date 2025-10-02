# --- Main SQS Queue ---
# This queue decouples the Splitter and Processor Lambdas, holding review batches for processing.
resource "aws_sqs_queue" "reviews_queue" {
  name = "reviewlens-reviews-queue"

  # How long a message can stay in the queue before being deleted (4 days).
  message_retention_seconds = 345600

  # Must be greater than the Processor Lambda's timeout to allow for successful processing.
  visibility_timeout_seconds = 960 # 16 minutes

  # Configures the redrive policy to send failed messages to the DLQ.
  redrive_policy = jsonencode({
    # After 3 failed processing attempts, move the message to the DLQ.
    maxReceiveCount     = 3
    deadLetterTargetArn = aws_sqs_queue.reviews_dlq.arn
  })
}

# --- Dead-Letter Queue (DLQ) ---
# This queue stores messages that fail processing multiple times, preventing data loss.
resource "aws_sqs_queue" "reviews_dlq" {
  name = "reviewlens-reviews-dlq"
}
