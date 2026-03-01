from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Consolidation Controller"
    environment: str = "dev"
    api_keys: str = ""
    allow_no_api_key_in_dev: bool = True
    database_url: str = "sqlite:///./data/consolidation.db"
    data_dir: Path = Path("data")
    uploads_dir: Path = Path("data/uploads")
    outputs_dir: Path = Path("data/outputs")
    max_upload_size_mb: int = 50
    default_presentation_currency: str = "USD"
    cta_account_code: str = "3999-CTA"
    cta_account_name: str = "Cumulative Translation Adjustment"
    katanox_base_url: str = "https://api.katanox.com/v2"
    katanox_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CONSOL_",
        case_sensitive=False,
    )


settings = Settings()
