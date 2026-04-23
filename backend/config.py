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

    @property
    def cloud_sql_instance_connection_name(self) -> str:
        return f"{self.gcp_project_id}:{self.gcp_region}:{self.gcp_instance_name}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
