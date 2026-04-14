import boto3

from app.utils.env_load import r2_endpoint, r2_secret_key, r2_access_key

s3 = boto3.client(
    "s3",
    endpoint_url=r2_endpoint,
    aws_access_key_id=r2_access_key,
    aws_secret_access_key=r2_secret_key,
    region_name="auto",
)
