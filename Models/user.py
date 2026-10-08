"""Модель пользователя для мини-системы бронирования."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass
class User:
    """Строка таблицы ``users``.

    Поля соответствуют будущей таблице PostgreSQL.
    Для записи в БД через ``PostgresDriver`` используйте :meth:`to_db`.
    """

    TABLE = "users"

    id: int | None = None
    email: str = ""
    password_hash: str = ""
    full_name: str = ""
    phone: str | None = None
    is_active: bool = True
    created_at: datetime | None = None

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS users (
        id              SERIAL PRIMARY KEY,
        email           VARCHAR(255) NOT NULL UNIQUE,
        password_hash   VARCHAR(255) NOT NULL,
        full_name       VARCHAR(255) NOT NULL,
        phone           VARCHAR(32),
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    def to_db(self, *, include_id: bool = False) -> dict[str, Any]:
        """Словарь для INSERT/UPDATE через PostgresDriver.

        ``id`` и ``created_at`` по умолчанию не включаются —
        их задаёт СУБД.
        """
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
            is_active=bool(row.get("is_active", True)),
            created_at=row.get("created_at"),
        )
