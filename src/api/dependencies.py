"""
FastAPI dependencies.

Provides dependency injection for:
- Database sessions
- Authentication/authorization
- Configuration
"""

from typing import Generator

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from src.core.config import get_settings, Settings
from src.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_settings_dep() -> Settings:
    """Settings dependency."""
    return get_settings()


async def require_admin(
    x_api_key: str = Header(None, alias="X-API-Key"),
    authorization: str = Header(None),
    settings: Settings = Depends(get_settings_dep),
) -> bool:
    """
    Admin authentication dependency.

    Checks for valid admin API key in:
    - X-API-Key header
    - Authorization: Bearer <key> header

    Usage:
        @app.post("/admin/action")
        def admin_action(_: bool = Depends(require_admin)):
            return {"status": "ok"}
    """
    api_key = x_api_key

    # Also check Authorization header
    if not api_key and authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return True


async def optional_admin(
    x_api_key: str = Header(None, alias="X-API-Key"),
    authorization: str = Header(None),
    settings: Settings = Depends(get_settings_dep),
) -> bool:
    """
    Optional admin authentication.

    Returns True if valid admin key provided, False otherwise.
    Does not raise exceptions.
    """
    api_key = x_api_key

    if not api_key and authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]

    if api_key and api_key == settings.admin_api_key:
        return True

    return False
