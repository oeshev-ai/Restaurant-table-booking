"""Заполнение БД тестовыми данными: сотрудники, гости, столы, бронирования."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Models.booking import Booking
from Models.tables import Table
from Models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_STAFF, User
from auth import hash_password
from backend import Backend


def clear_all(api: Backend) -> None:
    """Очистить таблицы в безопасном порядке (из‑за FK)."""
    api.db.execute("DELETE FROM bookings;")
    api.db.execute("DELETE FROM tables;")
    api.db.execute("DELETE FROM users;")


def seed(*, reset: bool = True) -> None:
    """Заполнить БД демо-данными.

    ``reset=True`` (по умолчанию) — сначала очищает таблицы, поэтому
    повторный запуск не падает на UNIQUE.
    """
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    users = [
        User(
            email="admin@example.com",
            password_hash=hash_password("admin123"),
            full_name="Администратор",
            phone="+79000000001",
            role=ROLE_ADMIN,
            is_active=True,
        ),
        User(
            email="staff@example.com",
            password_hash=hash_password("staff123"),
            full_name="Сотрудник Смены",
            phone="+79000000002",
            role=ROLE_STAFF,
            is_active=True,
        ),
        User(
            email="ivanov@example.com",
            password_hash=hash_password("guest123"),
            full_name="Иванов Иван",
            phone="+79001112233",
            role=ROLE_CUSTOMER,
            is_active=True,
        ),
        User(
            email="petrova@example.com",
            password_hash=hash_password("guest123"),
            full_name="Петрова Анна",
            phone="+79002223344",
            role=ROLE_CUSTOMER,
            is_active=True,
        ),
        User(
            email="sidorov@example.com",
            password_hash=hash_password("guest123"),
            full_name="Сидоров Пётр",
            phone="+79003334455",
            role=ROLE_CUSTOMER,
            is_active=True,
        ),
        User(
            email="smirnova@example.com",
            password_hash=hash_password("guest123"),
            full_name="Смирнова Ольга",
            phone="+79004445566",
            role=ROLE_CUSTOMER,
            is_active=True,
        ),
        User(
            email="kuznetsov@example.com",
            password_hash=hash_password("guest123"),
            full_name="Кузнецов Алексей",
            phone="+79005556677",
            role=ROLE_CUSTOMER,
            is_active=False,
        ),
    ]

    tables = [
        Table(number=1, seats=2, zone="Зал", is_active=True),
        Table(number=2, seats=4, zone="Зал", is_active=True),
        Table(number=3, seats=4, zone="Терраса", is_active=True),
        Table(number=4, seats=6, zone="VIP", is_active=True),
        Table(number=5, seats=8, zone="Банкетный", is_active=False),
    ]

    with Backend() as api:
        api.init_schema()
        if reset:
            clear_all(api)

        created_users = [api.create_user(user) for user in users]
        created_tables = [api.create_table(table) for table in tables]

        # Гости для броней: индексы 2..5 (после admin/staff).
        guests = created_users[2:]

        bookings = [
            Booking(
                user_id=guests[0].id,
                table_id=created_tables[0].id,
                starts_at=now + timedelta(days=1, hours=18),
                ends_at=now + timedelta(days=1, hours=20),
                guests_count=2,
                status="confirmed",
                comment="У окна",
            ),
            Booking(
                user_id=guests[1].id,
                table_id=created_tables[1].id,
                starts_at=now + timedelta(days=1, hours=19),
                ends_at=now + timedelta(days=1, hours=21),
                guests_count=3,
                status="confirmed",
                comment=None,
            ),
            Booking(
                user_id=guests[2].id,
                table_id=created_tables[2].id,
                starts_at=now + timedelta(days=2, hours=13),
                ends_at=now + timedelta(days=2, hours=15),
                guests_count=4,
                status="pending",
                comment="День рождения",
            ),
            Booking(
                user_id=guests[3].id,
                table_id=created_tables[3].id,
                starts_at=now + timedelta(days=2, hours=18),
                ends_at=now + timedelta(days=2, hours=21),
                guests_count=5,
                status="confirmed",
                comment="VIP ужин",
            ),
            Booking(
                user_id=guests[0].id,
                table_id=created_tables[1].id,
                starts_at=now + timedelta(days=3, hours=12),
                ends_at=now + timedelta(days=3, hours=14),
                guests_count=2,
                status="cancelled",
                comment="Отменено гостем",
            ),
        ]

        created_bookings = [api.create_booking(booking) for booking in bookings]

        print(f"Пользователи: {len(created_users)}")
        print(f"Столы: {len(created_tables)}")
        print(f"Бронирования: {len(created_bookings)}")
        print("Вход: admin@example.com / admin123")
        print("Вход: staff@example.com / staff123")


if __name__ == "__main__":
    seed()
