import os
import boto3
from dotenv import load_dotenv

load_dotenv()

# S3 Configuration
S3_BUCKET = os.getenv("S3_BUCKET", "ok-actionbucket")
AWS_REGION = os.getenv("AWS_REGION", "us-east-005")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://s3.us-east-005.backblazeb2.com")

def get_s3_client():
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        return boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
            endpoint_url=S3_ENDPOINT_URL
        )
    return boto3.client('s3', region_name=AWS_REGION, endpoint_url=S3_ENDPOINT_URL)

def get_presigned_url(s3_key: str, expiration=3600) -> str:
    """Generates a presigned URL for an S3 object."""
    s3_client = get_s3_client()
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': s3_key
            },
            ExpiresIn=expiration
        )
        return response
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return ""
