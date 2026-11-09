"""Модель пользователя для системы бронирования."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping

ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLE_CUSTOMER = "customer"

ROLE_LABELS = {
    ROLE_ADMIN: "Администратор",
    ROLE_STAFF: "Сотрудник",
    ROLE_CUSTOMER: "Гость",
}

# Роли, которым разрешён вход в веб-интерфейс.
LOGIN_ROLES = frozenset({ROLE_ADMIN, ROLE_STAFF})


@dataclass
class User:
    """Строка таблицы ``users``."""

    TABLE = "users"

    id: int | None = None
    email: str = ""
    password_hash: str = ""
    full_name: str = ""
    phone: str | None = None
    role: str = ROLE_CUSTOMER
    is_active: bool = True
    created_at: datetime | None = None

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS users (
        id              SERIAL PRIMARY KEY,
        email           VARCHAR(255) NOT NULL UNIQUE,
        password_hash   VARCHAR(255) NOT NULL,
        full_name       VARCHAR(255) NOT NULL,
        phone           VARCHAR(32),
        role            VARCHAR(32) NOT NULL DEFAULT 'customer',
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    MIGRATE_SQL = """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'customer';
    """

    def can_login(self) -> bool:
        return self.is_active and self.role in LOGIN_ROLES

    def to_db(self, *, include_id: bool = False) -> dict[str, Any]:
        """Словарь для INSERT/UPDATE через PostgresDriver."""
        data = asdict(self)

        if not include_id:
            data.pop("id", None)

        if data.get("created_at") is None:
            data.pop("created_at", None)

        return data

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> User:
        """Собрать модель из строки, возвращённой PostgresDriver."""
        return cls(
            id=row.get("id"),
            email=row["email"],
            password_hash=row["password_hash"],
            full_name=row["full_name"],
            phone=row.get("phone"),
            role=row.get("role") or ROLE_CUSTOMER,
            is_active=bool(row.get("is_active", True)),
            created_at=row.get("created_at"),
        )
