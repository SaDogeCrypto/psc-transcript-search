"""
Configuration utilities for loading settings from environment.
"""

import os
from dataclasses import dataclass, fields
from typing import Optional, TypeVar, Type, Any


T = TypeVar('T')


def env_str(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get string from environment."""
    return os.getenv(key, default)


def env_int(key: str, default: int = 0) -> int:
    """Get integer from environment."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def env_float(key: str, default: float = 0.0) -> float:
    """Get float from environment."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def env_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() in ('true', '1', 'yes', 'on')


def env_list(key: str, default: Optional[list] = None, separator: str = ',') -> list:
    """Get list from comma-separated environment variable."""
    val = os.getenv(key)
    if val is None:
        return default or []
    return [item.strip() for item in val.split(separator) if item.strip()]


__all__ = ['env_str', 'env_int', 'env_float', 'env_bool', 'env_list']
