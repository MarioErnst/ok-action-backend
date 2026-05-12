import os
import boto3
from dotenv import load_dotenv

load_dotenv("backend/.env")

S3_BUCKET = os.getenv("S3_BUCKET", "ok-actionbucket")
AWS_REGION = os.getenv("AWS_REGION", "us-east-005")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "https://s3.us-east-005.backblazeb2.com")

print(f"Bucket: {S3_BUCKET}")
print(f"Region: {AWS_REGION}")
print(f"Endpoint: {S3_ENDPOINT_URL}")
print(f"Key: {AWS_ACCESS_KEY_ID}")

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
    endpoint_url=S3_ENDPOINT_URL
)

try:
    response = s3_client.list_objects_v2(Bucket=S3_BUCKET)
    if 'Contents' in response:
        print("Objects found:")
        for obj in response['Contents']:
            print(f"- {obj['Key']}")
    else:
        print("Bucket is empty or 'Contents' not in response:", response)
except Exception as e:
    print(f"Error: {e}")
