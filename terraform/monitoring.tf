# --- SNS Topic to trigger the Stitcher Lambda ---
resource "aws_sns_topic" "stitching_topic" {
  name = "reviewlens-start-stitching-topic"
}

# --- CloudWatch Alarm that monitors the SQS Queue ---
# This alarm will trigger when the queue has been empty for 5 minutes.
resource "aws_cloudwatch_metric_alarm" "queue_empty_alarm" {
  alarm_name          = "reviewlens-queue-is-empty-alarm"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    QueueName = aws_sqs_queue.reviews_queue.name
  }

  # When the alarm state is reached (OK -> ALARM), it sends a message to the SNS topic.
  alarm_actions = [aws_sns_topic.stitching_topic.arn]
}

# Give CloudWatch Alarms permission to publish to our SNS topic
resource "aws_sns_topic_policy" "stitching_topic_policy" {
  arn    = aws_sns_topic.stitching_topic.arn
  policy = data.aws_iam_policy_document.sns_topic_policy.json
}

data "aws_iam_policy_document" "sns_topic_policy" {
  statement {
    actions   = ["SNS:Publish"]
    effect    = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    resources = [aws_sns_topic.stitching_topic.arn]
  }
}