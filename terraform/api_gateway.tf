# --- API Gateway (HTTP API) ---
# Creates a HTTP API to expose our Lambda functions to the web.
resource "aws_apigatewayv2_api" "main_api" {
  name          = "reviewlens-api"
  protocol_type = "HTTP"
}

# Creates a default stage that auto-deploys API changes, making it live.
resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.main_api.id
  name        = "$default"
  auto_deploy = true
}

# --- API Gateway Integrations ---
# Integrations define the link between an API route and the backend service (our Lambdas).

resource "aws_apigatewayv2_integration" "status_checker_integration" {
  api_id           = aws_apigatewayv2_api.main_api.id
  integration_type = "AWS_PROXY" # Standard integration type for Lambda.
  integration_uri  = aws_lambda_function.status_checker_lambda.invoke_arn
}

resource "aws_apigatewayv2_integration" "stitcher_integration" {
  api_id           = aws_apigatewayv2_api.main_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.stitcher_lambda.invoke_arn
}

# --- API Gateway Routes ---
# A route maps an HTTP method (e.g., GET, POST) and a path to a specific integration.

resource "aws_apigatewayv2_route" "get_status_route" {
  api_id    = aws_apigatewayv2_api.main_api.id
  route_key = "GET /status/{job_id}" # e.g., GET /status/abc-123
  target    = "integrations/${aws_apigatewayv2_integration.status_checker_integration.id}"
}

resource "aws_apigatewayv2_route" "start_stitcher_route" {
  api_id    = aws_apigatewayv2_api.main_api.id
  route_key = "POST /stitch" # POST request to start the stitching process
  target    = "integrations/${aws_apigatewayv2_integration.stitcher_integration.id}"
}