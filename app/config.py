from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "curationbysarrie"

    # Bumpa
    bumpa_base_url: str = "https://api.getbumpa.com/api/commerce/v1"
    bumpa_api_key: str = ""
    bumpa_store_id: str = ""

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Auth
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Super admin
    super_admin_email: str = "admin@curationbysarrie.com"
    super_admin_password: str = "ChangeMe123!"
    super_admin_name: str = "Super Admin"

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Curation by Sarrie"
    admin_panel_url: str = "http://localhost:3000/admin/login"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()