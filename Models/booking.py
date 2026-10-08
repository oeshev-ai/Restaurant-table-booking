"""Модель бронирования для мини-системы бронирования ресторана."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass
class Booking:
    """Одно бронирование стола (строка таблицы ``bookings``).

    ``user_id`` — пользователь, который создал бронь.
    ``table_id`` — стол, который забронирован.
    Для записи в БД через ``PostgresDriver`` используйте :meth:`to_db`.
    """

    TABLE = "bookings"

    id: int | None = None
    user_id: int = 0
    table_id: int = 0
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    guests_count: int = 1
    status: str = "confirmed"
    comment: str | None = None
    created_at: datetime | None = None

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS bookings (
        id              SERIAL PRIMARY KEY,
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        table_id        INTEGER NOT NULL REFERENCES tables(id) ON DELETE RESTRICT,
        starts_at       TIMESTAMPTZ NOT NULL,
        ends_at         TIMESTAMPTZ NOT NULL,
        guests_count    INTEGER NOT NULL CHECK (guests_count > 0),
        status          VARCHAR(32) NOT NULL DEFAULT 'confirmed',
        comment         TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (ends_at > starts_at)
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
    def from_row(cls, row: Mapping[str, Any]) -> Booking:
        """Собрать модель из строки, возвращённой PostgresDriver."""
        return cls(
            id=row.get("id"),
            user_id=row["user_id"],
            table_id=row["table_id"],
            starts_at=row.get("starts_at"),
            ends_at=row.get("ends_at"),
            guests_count=row["guests_count"],
            status=row.get("status", "confirmed"),
            comment=row.get("comment"),
            created_at=row.get("created_at"),
        )
