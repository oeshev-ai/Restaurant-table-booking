"""Модель стола для мини-системы бронирования ресторана."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass
class Table:
    """Один конкретный стол в ресторане (строка таблицы ``tables``).

    Поля соответствуют будущей таблице PostgreSQL.
    Для записи в БД через ``PostgresDriver`` используйте :meth:`to_db`.
    """

    TABLE = "tables"

    id: int | None = None
    number: int = 0
    seats: int = 2
    zone: str | None = None
    is_active: bool = True
    created_at: datetime | None = None

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS tables (
        id              SERIAL PRIMARY KEY,
        number          INTEGER NOT NULL UNIQUE,
        seats           INTEGER NOT NULL CHECK (seats > 0),
        zone            VARCHAR(100),
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
    def from_row(cls, row: Mapping[str, Any]) -> Table:
        """Собрать модель из строки, возвращённой PostgresDriver."""
        return cls(
            id=row.get("id"),
            number=row["number"],
            seats=row["seats"],
            zone=row.get("zone"),
            is_active=bool(row.get("is_active", True)),
            created_at=row.get("created_at"),
        )
