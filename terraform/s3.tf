provider "aws" { region = "eu-west-1" }

resource "aws_s3_bucket" "bronze_bucket" { bucket = "reviewlens-bronze-bucket-kevin" }

resource "aws_s3_bucket" "silver_bucket" { bucket = "reviewlens-silver-bucket-kevin" }