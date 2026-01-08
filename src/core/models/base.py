"""
SQLAlchemy base class and common mixins.

Provides:
- Base: Declarative base for all models
- TimestampMixin: created_at/updated_at columns
- StateModelMixin: state_code column for multi-state support
- GUID: Cross-database UUID type (PostgreSQL native / SQLite string)
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, String, DateTime, func, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy.types import CHAR, JSON


class GUID(TypeDecorator):
    """
    Platform-independent UUID type.

    Uses PostgreSQL's native UUID type when available,
    otherwise stores as a 36-character string (for SQLite).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            else:
                return str(uuid.UUID(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    # Use GUID (cross-database UUID) as default for uuid.UUID annotations
    type_annotation_map = {
        uuid.UUID: GUID(),
    }

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamps.

    - created_at: Set automatically on insert
    - updated_at: Updated automatically on each update
    """

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


class StateModelMixin:
    """
    Mixin for models that belong to a specific state.

    Adds state_code column (e.g., 'FL', 'TX', 'CA').
    """

    state_code = Column(
        String(2),
        nullable=False,
        index=True,
        comment="Two-letter state code (e.g., FL, TX, CA)",
    )


class UUIDPrimaryKeyMixin:
    """
    Mixin that adds a UUID primary key.

    Alternative to auto-increment integers for distributed systems.
    """

    @declared_attr
    def id(cls):
        return Column(
            GUID(),
            primary_key=True,
            default=uuid.uuid4,
        )
