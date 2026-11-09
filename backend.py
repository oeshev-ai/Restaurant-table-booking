"""CRUD-операции для пользователей, столов и бронирований."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from Models.booking import Booking
from Models.tables import Table
from Models.user import User
from postgres_driver import PostgresDriver


class BookingConflictError(ValueError):
    """Стол уже занят в указанный интервал времени."""


class Backend:
    """Обёртка над PostgresDriver с CRUD для трёх моделей."""

    # Статусы, которые не блокируют стол.
    _INACTIVE_BOOKING_STATUSES = frozenset({"cancelled", "canceled"})

    def __init__(self, db: PostgresDriver | None = None) -> None:
        self.db = db if db is not None else PostgresDriver()

    def connect(self) -> Backend:
        self.db.connect()
        return self

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Backend:
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def init_schema(self) -> None:
        """Создать таблицы users → tables → bookings, если их ещё нет.

        Берёт session-level advisory lock, чтобы несколько воркеров
        Gunicorn не гонялись за созданием SERIAL-последовательностей.
        """
        lock_key = 0x5650633037  # VPc07
        self.db.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
        try:
            self.db.execute(User.CREATE_TABLE_SQL)
            self.db.execute(User.MIGRATE_SQL)
            self.db.execute(Table.CREATE_TABLE_SQL)
            self.db.execute(Booking.CREATE_TABLE_SQL)
        finally:
            self.db.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))

    # --- Users ---

    def create_user(self, user: User) -> User:
        row = self.db.create(User.TABLE, user.to_db())
        assert row is not None
        return User.from_row(row)

    def get_user(self, user_id: int) -> User | None:
        row = self.db.read_one(User.TABLE, where={"id": user_id})
        return User.from_row(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        row = self.db.read_one(User.TABLE, where={"email": email})
        return User.from_row(row) if row else None

    def get_users(
        self,
        where: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[User]:
        rows = self.db.read(
            User.TABLE,
            where=where,
            order_by="id",
            limit=limit,
            offset=offset,
        )
        return [User.from_row(row) for row in rows]

    def update_user(
        self,
        user_id: int,
        data: Mapping[str, Any],
    ) -> User | None:
        rows = self.db.update(User.TABLE, data, where={"id": user_id})
        return User.from_row(rows[0]) if rows else None

    def delete_user(self, user_id: int) -> User | None:
        rows = self.db.delete(User.TABLE, where={"id": user_id})
        return User.from_row(rows[0]) if rows else None

    # --- Tables ---

    def create_table(self, table: Table) -> Table:
        row = self.db.create(Table.TABLE, table.to_db())
        assert row is not None
        return Table.from_row(row)

    def get_table(self, table_id: int) -> Table | None:
        row = self.db.read_one(Table.TABLE, where={"id": table_id})
        return Table.from_row(row) if row else None

    def get_tables(
        self,
        where: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Table]:
        rows = self.db.read(
            Table.TABLE,
            where=where,
            order_by="number",
            limit=limit,
            offset=offset,
        )
        return [Table.from_row(row) for row in rows]

    def update_table(
        self,
        table_id: int,
        data: Mapping[str, Any],
    ) -> Table | None:
        rows = self.db.update(Table.TABLE, data, where={"id": table_id})
        return Table.from_row(rows[0]) if rows else None

    def delete_table(self, table_id: int) -> Table | None:
        try:
            rows = self.db.delete(Table.TABLE, where={"id": table_id})
        except Exception as exc:
            name = type(exc).__name__
            if "ForeignKey" in name or "foreign key" in str(exc).lower():
                raise ValueError(
                    f"Нельзя удалить стол #{table_id}: есть связанные бронирования. "
                    "Сначала удалите брони или сделайте стол неактивным."
                ) from exc
            raise
        return Table.from_row(rows[0]) if rows else None

    # --- Bookings ---

    def find_conflicting_bookings(
        self,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_booking_id: int | None = None,
    ) -> list[Booking]:
        """Найти активные брони того же стола, пересекающиеся с интервалом.

        Интервалы пересекаются, если::

            existing.starts_at < ends_at AND existing.ends_at > starts_at
        """
        query = """
            SELECT *
            FROM bookings
            WHERE table_id = %s
              AND LOWER(status) NOT IN ('cancelled', 'canceled')
              AND starts_at < %s
              AND ends_at > %s
        """
        params: list[Any] = [table_id, ends_at, starts_at]

        if exclude_booking_id is not None:
            query += " AND id <> %s"
            params.append(exclude_booking_id)

        query += " ORDER BY starts_at;"
        rows = self.db.execute(query, params, commit=False)
        return [Booking.from_row(row) for row in rows]

    def is_table_available(
        self,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_booking_id: int | None = None,
    ) -> bool:
        """Проверить, свободен ли стол в указанный интервал."""
        conflicts = self.find_conflicting_bookings(
            table_id,
            starts_at,
            ends_at,
            exclude_booking_id=exclude_booking_id,
        )
        return not conflicts

    def _ensure_booking_interval(
        self,
        starts_at: datetime | None,
        ends_at: datetime | None,
    ) -> tuple[datetime, datetime]:
        if starts_at is None or ends_at is None:
            raise ValueError("Нужно указать время начала и окончания бронирования")
        if ends_at <= starts_at:
            raise ValueError("Время окончания должно быть позже времени начала")
        return starts_at, ends_at

    def _ensure_table_free(
        self,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        *,
        exclude_booking_id: int | None = None,
        status: str | None = None,
    ) -> None:
        if status is not None and status.lower() in self._INACTIVE_BOOKING_STATUSES:
            return

        conflicts = self.find_conflicting_bookings(
            table_id,
            starts_at,
            ends_at,
            exclude_booking_id=exclude_booking_id,
        )
        if not conflicts:
            return

        conflict = conflicts[0]
        raise BookingConflictError(
            "Стол уже забронирован в это время "
            f"(бронь #{conflict.id}: {conflict.starts_at} — {conflict.ends_at}). "
            "Выберите другой стол или другое время."
        )

    def _ensure_table_bookable(
        self,
        table_id: int,
        guests_count: int,
        *,
        booking_status: str | None = None,
    ) -> Table:
        """Проверить, что стол существует, активен и вмещает гостей.

        Проверки активности и вместимости выполняются всегда.
        Статус брони влияет только на проверку пересечений по времени.
        """
        table = self.get_table(table_id)
        if table is None:
            raise ValueError(f"Стол #{table_id} не найден")

        if not table.is_active:
            raise ValueError(
                f"Стол №{table.number} неактивен и недоступен для бронирования. "
                "Выберите другой стол."
            )

        if guests_count > table.seats:
            raise ValueError(
                f"Число гостей ({guests_count}) больше вместимости стола №{table.number} "
                f"({table.seats} мест). Выберите другой стол или забронируйте несколько столов."
            )

        return table

    def create_booking(self, booking: Booking) -> Booking:
        starts_at, ends_at = self._ensure_booking_interval(
            booking.starts_at, booking.ends_at
        )
        self._ensure_table_bookable(
            booking.table_id,
            booking.guests_count,
            booking_status=booking.status,
        )
        self._ensure_table_free(
            booking.table_id,
            starts_at,
            ends_at,
            status=booking.status,
        )
        row = self.db.create(Booking.TABLE, booking.to_db())
        assert row is not None
        return Booking.from_row(row)

    def get_booking(self, booking_id: int) -> Booking | None:
        row = self.db.read_one(Booking.TABLE, where={"id": booking_id})
        return Booking.from_row(row) if row else None

    def get_bookings(
        self,
        where: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Booking]:
        rows = self.db.read(
            Booking.TABLE,
            where=where,
            order_by="starts_at",
            limit=limit,
            offset=offset,
        )
        return [Booking.from_row(row) for row in rows]

    def update_booking(
        self,
        booking_id: int,
        data: Mapping[str, Any],
    ) -> Booking | None:
        current = self.get_booking(booking_id)
        if current is None:
            return None

        table_id = int(data.get("table_id", current.table_id))
        starts_at = data.get("starts_at", current.starts_at)
        ends_at = data.get("ends_at", current.ends_at)
        status = str(data.get("status", current.status))
        guests_count = int(data.get("guests_count", current.guests_count))

        starts_at, ends_at = self._ensure_booking_interval(starts_at, ends_at)
        self._ensure_table_bookable(
            table_id,
            guests_count,
            booking_status=status,
        )
        self._ensure_table_free(
            table_id,
            starts_at,
            ends_at,
            exclude_booking_id=booking_id,
            status=status,
        )

        rows = self.db.update(Booking.TABLE, data, where={"id": booking_id})
        return Booking.from_row(rows[0]) if rows else None

    def delete_booking(self, booking_id: int) -> Booking | None:
        rows = self.db.delete(Booking.TABLE, where={"id": booking_id})
        return Booking.from_row(rows[0]) if rows else None
