from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "OK Action API"
    environment: str = "development"

    # Cloud SQL
    gcp_project_id: str
    gcp_region: str
    gcp_instance_name: str
    db_user: str
    db_password: str
    db_name: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # CORS
    cors_origins: list[str] = Field(default_factory=list)

    # Gemini AI
    gemini_api_key: str
    # Streaming live model. Pinned GA id, not an alias. The live session
    # supervisor opens one WS to this model per active live session.
    gemini_live_model: str = "gemini-live-2.5-flash-native-audio"

    # Backblaze B2 (S3-compatible storage)
    s3_bucket: str = "ok-actionbucket"
    s3_endpoint_url: str = "https://s3.us-east-005.backblazeb2.com"
    aws_region: str = "us-east-005"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Dev user
    dev_user_email: str = ""
    dev_user_password: str = ""
    dev_user_full_name: str = ""

    # Demo user (consumed by backend/scripts/seed_demo_user.py).
    # Optional: when missing the seed falls back to its baked-in defaults.
    demo_user_email: str = ""
    demo_user_password: str = ""
    demo_user_full_name: str = ""

    @property
    def cloud_sql_instance_connection_name(self) -> str:
        return f"{self.gcp_project_id}:{self.gcp_region}:{self.gcp_instance_name}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
