# --- DynamoDB Table for Job Status Tracking ---
# This table acts as a state machine, tracking the progress of each processing job.
resource "aws_dynamodb_table" "jobs_status_table" {
  name         = "reviewlens-jobs-status"
  billing_mode = "PAY_PER_REQUEST" # Cost-effective for unpredictable workloads.
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S" # S for String
  }
}