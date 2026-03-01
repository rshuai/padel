from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    configured = [item.strip() for item in settings.api_keys.split(",") if item.strip()]
    if not configured and settings.environment == "dev" and settings.allow_no_api_key_in_dev:
        return

    if not x_api_key or x_api_key not in configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
