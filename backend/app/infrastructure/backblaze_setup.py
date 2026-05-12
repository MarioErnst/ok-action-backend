import boto3

from config import settings


def get_s3_client():
    """Build a boto3 S3 client for the configured Backblaze B2 bucket.

    Falls back to a credential-less client (relies on the boto3 default chain)
    when explicit keys are not provided so local dev / unit tests can run
    without S3 access.
    """
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        return boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url,
        )
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.s3_endpoint_url,
    )


def get_presigned_url(s3_key: str, expiration: int = 3600) -> str:
    """Generate a time-limited presigned GET URL for an S3 object."""
    s3_client = get_s3_client()
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": s3_key},
            ExpiresIn=expiration,
        )
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return ""
