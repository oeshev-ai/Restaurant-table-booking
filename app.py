"""Веб-интерфейс системы бронирования (Flask)."""

from __future__ import annotations

import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator

from dotenv import load_dotenv
from flask import Flask, abort, flash, g, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFProtect

from Models.booking import Booking
from Models.tables import Table
from Models.user import (
    LOGIN_ROLES,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_LABELS,
    ROLE_STAFF,
    User,
)
from auth import (
    admin_required,
    authenticate,
    hash_password,
    load_current_user,
    login_required,
    login_user,
    logout_user,
    staff_required,
)
from backend import Backend

load_dotenv()

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"

STATUS_LABELS = {
    "confirmed": "Подтверждено",
    "pending": "Ожидает",
    "cancelled": "Отменено",
}

_WEAK_SECRETS = {
    "",
    "secret",
    "password",
    "postgres",
    "changeme",
    "dev-only-change-me",
}


def _require_env(name: str, *, forbid_weak: bool = False) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Переменная окружения {name} обязательна. "
            "Скопируйте .env.example в .env и задайте уникальные значения."
        )
    if forbid_weak and value.lower() in _WEAK_SECRETS:
        raise RuntimeError(
            f"Переменная {name} использует небезопасное значение. "
            "Задайте длинный случайный секрет (см. .env.example)."
        )
    return value


def create_app() -> Flask:
    _require_env("DB_PASSWORD", forbid_weak=True)
    app = Flask(__name__)
    app.secret_key = _require_env("SECRET_KEY", forbid_weak=True)
    app.config.update(
        WTF_CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    CSRFProtect(app)

    if os.getenv("SKIP_SCHEMA_INIT", "0") != "1":
        with Backend() as api:
            api.init_schema()

    @contextmanager
    def db() -> Iterator[Backend]:
        api = Backend()
        api.connect()
        try:
            yield api
        finally:
            api.close()

    @app.before_request
    def _load_user() -> None:
        g.current_user = None
        if request.endpoint == "static":
            return
        with db() as api:
            g.current_user = load_current_user(api)

    @app.context_processor
    def _inject_auth() -> dict[str, Any]:
        return {
            "current_user": getattr(g, "current_user", None),
            "ROLE_LABELS": ROLE_LABELS,
            "ROLE_ADMIN": ROLE_ADMIN,
            "ROLE_STAFF": ROLE_STAFF,
            "ROLE_CUSTOMER": ROLE_CUSTOMER,
        }

    def fmt_dt(value: datetime | None) -> str:
        if value is None:
            return ""
        return value.strftime(f"{DATE_FMT} {TIME_FMT}")

    def split_dt(value: datetime | None) -> tuple[str, str]:
        if value is None:
            return "", ""
        return value.strftime(DATE_FMT), value.strftime(TIME_FMT)

    def combine_dt(date_str: str, time_str: str) -> datetime:
        try:
            return datetime.strptime(
                f"{date_str.strip()} {time_str.strip()}", f"{DATE_FMT} {TIME_FMT}"
            )
        except ValueError as exc:
            raise ValueError("Укажите дату (ГГГГ-ММ-ДД) и время (ЧЧ:ММ)") from exc

    def checked(name: str) -> bool:
        return request.form.get(name) == "on"

    def user_form_data() -> dict[str, Any]:
        return {
            "email": request.form.get("email", "").strip().lower(),
            "password": request.form.get("password", ""),
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "role": request.form.get("role", ROLE_CUSTOMER).strip() or ROLE_CUSTOMER,
            "is_active": checked("is_active"),
        }

    def table_form_data() -> dict[str, Any]:
        return {
            "number": request.form.get("number", "").strip(),
            "seats": request.form.get("seats", "").strip(),
            "zone": request.form.get("zone", "").strip(),
            "is_active": checked("is_active"),
        }

    def booking_form_data() -> dict[str, Any]:
        return {
            "user_id": request.form.get("user_id", "").strip(),
            "table_id": request.form.get("table_id", "").strip(),
            "starts_date": request.form.get("starts_date", "").strip(),
            "starts_time": request.form.get("starts_time", "").strip(),
            "ends_date": request.form.get("ends_date", "").strip(),
            "ends_time": request.form.get("ends_time", "").strip(),
            "guests_count": request.form.get("guests_count", "").strip() or "1",
            "status": request.form.get("status", "confirmed").strip() or "confirmed",
            "comment": request.form.get("comment", "").strip(),
        }

    def parse_user(
        data: dict[str, Any],
        *,
        require_password: bool = True,
        existing_role: str | None = None,
    ) -> User:
        if not data["email"] or not data["full_name"]:
            raise ValueError("Заполните email и ФИО")
        role = data["role"]
        if role not in ROLE_LABELS:
            raise ValueError("Выберите роль из списка")
        # Пароль нужен только ролям с входом в систему (admin/staff).
        needs_password = role in LOGIN_ROLES
        promoting_to_login = (
            needs_password
            and existing_role is not None
            and existing_role not in LOGIN_ROLES
        )
        if needs_password and not data["password"] and (require_password or promoting_to_login):
            raise ValueError("Для администратора и сотрудника укажите пароль")
        if needs_password and data["password"]:
            password_hash = hash_password(data["password"])
        elif needs_password:
            password_hash = ""  # редактирование: пароль не меняем
        else:
            # Гостю вход не нужен — случайный хеш, который никто не знает.
            password_hash = hash_password(secrets.token_urlsafe(32))
        return User(
            email=data["email"],
            password_hash=password_hash,
            full_name=data["full_name"],
            phone=data["phone"] or None,
            role=role,
            is_active=bool(data["is_active"]),
        )

    def parse_table(data: dict[str, Any]) -> Table:
        try:
            number = int(data["number"])
            seats = int(data["seats"] or "2")
        except ValueError as exc:
            raise ValueError("Номер и вместимость должны быть целыми числами") from exc
        if seats <= 0:
            raise ValueError("Вместимость должна быть больше 0")
        return Table(
            number=number,
            seats=seats,
            zone=data["zone"] or None,
            is_active=bool(data["is_active"]),
        )

    def parse_booking(data: dict[str, Any]) -> Booking:
        try:
            user_id = int(data["user_id"])
            table_id = int(data["table_id"])
            guests_count = int(data["guests_count"] or "1")
        except ValueError as exc:
            raise ValueError("Выберите пользователя и стол, укажите число гостей") from exc
        if guests_count <= 0:
            raise ValueError("Число гостей должно быть больше 0")
        status = data["status"]
        if status not in STATUS_LABELS:
            raise ValueError("Выберите статус из списка")
        return Booking(
            user_id=user_id,
            table_id=table_id,
            starts_at=combine_dt(data["starts_date"], data["starts_time"]),
            ends_at=combine_dt(data["ends_date"], data["ends_time"]),
            guests_count=guests_count,
            status=status,
            comment=data["comment"] or None,
        )

    def user_to_form(user: User) -> dict[str, Any]:
        return {
            "email": user.email,
            "password": "",
            "full_name": user.full_name,
            "phone": user.phone or "",
            "role": user.role,
            "is_active": user.is_active,
        }

    def table_to_form(table: Table) -> dict[str, Any]:
        return {
            "number": table.number,
            "seats": table.seats,
            "zone": table.zone or "",
            "is_active": table.is_active,
        }

    def booking_to_form(booking: Booking) -> dict[str, Any]:
        starts_date, starts_time = split_dt(booking.starts_at)
        ends_date, ends_time = split_dt(booking.ends_at)
        return {
            "user_id": booking.user_id,
            "table_id": booking.table_id,
            "starts_date": starts_date,
            "starts_time": starts_time,
            "ends_date": ends_date,
            "ends_time": ends_time,
            "guests_count": booking.guests_count,
            "status": booking.status,
            "comment": booking.comment or "",
        }

    def empty_booking_form() -> dict[str, Any]:
        today = datetime.now().strftime(DATE_FMT)
        return {
            "user_id": "",
            "table_id": "",
            "starts_date": today,
            "starts_time": "",
            "ends_date": today,
            "ends_time": "",
            "guests_count": "1",
            "status": "confirmed",
            "comment": "",
        }

    def selected_id() -> int | None:
        raw = request.args.get("id", "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def booking_choices(
        api: Backend,
        current_table_id: int | None = None,
        current_user_id: int | None = None,
    ) -> tuple[list[User], list[Table]]:
        users = [
            user
            for user in api.get_users(where={"is_active": True, "role": ROLE_CUSTOMER})
        ]
        if current_user_id is not None and all(user.id != current_user_id for user in users):
            current_user = api.get_user(current_user_id)
            if current_user is not None:
                users.append(current_user)
        tables = api.get_tables(where={"is_active": True})
        if current_table_id is not None and all(table.id != current_table_id for table in tables):
            current = api.get_table(current_table_id)
            if current is not None:
                tables.append(current)
        return users, tables

    def check_slot(api: Backend, booking: Booking, exclude_id: int | None) -> str:
        if booking.starts_at is None or booking.ends_at is None:
            raise ValueError("Укажите начало и конец бронирования")
        if booking.ends_at <= booking.starts_at:
            raise ValueError("Время окончания должно быть позже времени начала")
        # Те же правила, что и при сохранении: активный стол + вместимость.
        api._ensure_table_bookable(
            booking.table_id,
            booking.guests_count,
            booking_status=booking.status,
        )
        conflicts = api.find_conflicting_bookings(
            booking.table_id,
            booking.starts_at,
            booking.ends_at,
            exclude_booking_id=exclude_id,
        )
        if not conflicts:
            return "На выбранное время стол свободен — конфликтующих бронирований нет."
        conflict = conflicts[0]
        raise ValueError(
            "Стол уже забронирован в это время "
            f"(бронь #{conflict.id}: {fmt_dt(conflict.starts_at)} — {fmt_dt(conflict.ends_at)}). "
            "Выберите другой стол или другое время."
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.current_user is not None:
            return redirect(url_for("index"))
        error = None
        email = ""
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            with db() as api:
                user = authenticate(api, email, password)
            if user is None:
                error = "Неверный email или пароль, либо нет доступа к системе."
            else:
                login_user(user)
                nxt = request.args.get("next") or url_for("index")
                if not nxt.startswith("/"):
                    nxt = url_for("index")
                return redirect(nxt)
        return render_template("login.html", error=error, email=email)

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        if g.current_user.role == ROLE_ADMIN:
            return redirect(url_for("users"))
        return redirect(url_for("bookings"))

    @app.route("/users")
    @admin_required
    def users():
        status = request.args.get("status", "all")
        role = request.args.get("role", "all")
        with db() as api:
            items = api.get_users()
            chosen = selected_id()
            selected = api.get_user(chosen) if chosen else None
        if status == "active":
            items = [item for item in items if item.is_active]
        elif status == "inactive":
            items = [item for item in items if not item.is_active]
        if role in ROLE_LABELS:
            items = [item for item in items if item.role == role]
        return render_template(
            "users.html",
            items=items,
            selected=selected,
            status=status,
            role=role,
            fmt_dt=fmt_dt,
        )

    @app.route("/users/new", methods=["GET", "POST"])
    @admin_required
    def user_new():
        data = user_form_data() if request.method == "POST" else {
            "email": "",
            "password": "",
            "full_name": "",
            "phone": "",
            "role": ROLE_CUSTOMER,
            "is_active": True,
        }
        error = None
        if request.method == "POST":
            try:
                user = parse_user(data)
                with db() as api:
                    created = api.create_user(user)
                return redirect(url_for("users", id=created.id))
            except Exception as exc:
                error = str(exc)
        return render_template("user_form.html", form=data, error=error, user_id=None)

    @app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
    @admin_required
    def user_edit(user_id: int):
        error = None
        with db() as api:
            user = api.get_user(user_id)
        if user is None:
            abort(404)
        data = user_form_data() if request.method == "POST" else user_to_form(user)
        if request.method == "POST":
            try:
                parsed = parse_user(
                    data,
                    require_password=False,
                    existing_role=user.role,
                )
                payload = parsed.to_db()
                if not data["password"] or data["role"] not in LOGIN_ROLES:
                    # Гостю пароль не храним из формы; staff/admin без ввода — не трогаем хеш.
                    if not data["password"]:
                        payload.pop("password_hash", None)
                # Нельзя снять с себя роль admin / деактивировать себя.
                if user_id == g.current_user.id:
                    payload["role"] = ROLE_ADMIN
                    payload["is_active"] = True
                with db() as api:
                    api.update_user(user_id, payload)
                return redirect(url_for("users", id=user_id))
            except Exception as exc:
                error = str(exc)
        return render_template("user_form.html", form=data, error=error, user_id=user_id)

    @app.post("/users/<int:user_id>/delete")
    @admin_required
    def user_delete(user_id: int):
        if user_id == g.current_user.id:
            flash("Нельзя удалить свою учётную запись.", "error")
            return redirect(url_for("users", id=user_id))
        with db() as api:
            api.delete_user(user_id)
        return redirect(url_for("users"))

    @app.route("/tables")
    @staff_required
    def tables():
        status = request.args.get("status", "all")
        with db() as api:
            items = api.get_tables()
            chosen = selected_id()
            selected = api.get_table(chosen) if chosen else None
        if status == "active":
            items = [item for item in items if item.is_active]
        elif status == "inactive":
            items = [item for item in items if not item.is_active]
        return render_template(
            "tables.html",
            items=items,
            selected=selected,
            status=status,
            fmt_dt=fmt_dt,
        )

    @app.route("/tables/new", methods=["GET", "POST"])
    @staff_required
    def table_new():
        data = table_form_data() if request.method == "POST" else {
            "number": "",
            "seats": "2",
            "zone": "",
            "is_active": True,
        }
        error = None
        if request.method == "POST":
            try:
                table = parse_table(data)
                with db() as api:
                    created = api.create_table(table)
                return redirect(url_for("tables", id=created.id))
            except Exception as exc:
                error = str(exc)
        return render_template("table_form.html", form=data, error=error, table_id=None)

    @app.route("/tables/<int:table_id>/edit", methods=["GET", "POST"])
    @staff_required
    def table_edit(table_id: int):
        error = None
        with db() as api:
            table = api.get_table(table_id)
        if table is None:
            abort(404)
        data = table_form_data() if request.method == "POST" else table_to_form(table)
        if request.method == "POST":
            try:
                parsed = parse_table(data)
                with db() as api:
                    api.update_table(table_id, parsed.to_db())
                return redirect(url_for("tables", id=table_id))
            except Exception as exc:
                error = str(exc)
        return render_template("table_form.html", form=data, error=error, table_id=table_id)

    @app.post("/tables/<int:table_id>/delete")
    @staff_required
    def table_delete(table_id: int):
        try:
            with db() as api:
                api.delete_table(table_id)
        except Exception as exc:
            with db() as api:
                items = api.get_tables()
                selected = api.get_table(table_id)
            return render_template(
                "tables.html",
                items=items,
                selected=selected,
                status="all",
                fmt_dt=fmt_dt,
                error=str(exc),
            )
        return redirect(url_for("tables"))

    @app.route("/bookings")
    @staff_required
    def bookings():
        status = request.args.get("status", "all")
        with db() as api:
            items = api.get_bookings()
            users = {user.id: user for user in api.get_users()}
            tables = {table.id: table for table in api.get_tables()}
            chosen = selected_id()
            selected = api.get_booking(chosen) if chosen else None
        if status in STATUS_LABELS:
            items = [item for item in items if item.status == status]
        return render_template(
            "bookings.html",
            items=items,
            users=users,
            tables=tables,
            selected=selected,
            status=status,
            status_labels=STATUS_LABELS,
            fmt_dt=fmt_dt,
        )

    def render_booking_form(
        form: dict[str, Any],
        *,
        booking_id: int | None,
        error: str | None = None,
        notice: str | None = None,
    ):
        current_table = None
        current_user = None
        try:
            current_table = int(form["table_id"]) if form.get("table_id") else None
        except (TypeError, ValueError):
            current_table = None
        try:
            current_user = int(form["user_id"]) if form.get("user_id") else None
        except (TypeError, ValueError):
            current_user = None
        with db() as api:
            users, tables = booking_choices(api, current_table, current_user)
        return render_template(
            "booking_form.html",
            form=form,
            error=error,
            notice=notice,
            booking_id=booking_id,
            users=users,
            tables=tables,
            status_labels=STATUS_LABELS,
        )

    @app.route("/bookings/new", methods=["GET", "POST"])
    @staff_required
    def booking_new():
        data = booking_form_data() if request.method == "POST" else empty_booking_form()
        if request.method == "POST":
            try:
                booking = parse_booking(data)
                with db() as api:
                    created = api.create_booking(booking)
                return redirect(url_for("bookings", id=created.id))
            except Exception as exc:
                return render_booking_form(data, booking_id=None, error=str(exc))
        return render_booking_form(data, booking_id=None)

    @app.route("/bookings/<int:booking_id>/edit", methods=["GET", "POST"])
    @staff_required
    def booking_edit(booking_id: int):
        with db() as api:
            booking = api.get_booking(booking_id)
        if booking is None:
            abort(404)
        data = booking_form_data() if request.method == "POST" else booking_to_form(booking)
        if request.method == "POST":
            try:
                parsed = parse_booking(data)
                with db() as api:
                    api.update_booking(booking_id, parsed.to_db())
                return redirect(url_for("bookings", id=booking_id))
            except Exception as exc:
                return render_booking_form(data, booking_id=booking_id, error=str(exc))
        return render_booking_form(data, booking_id=booking_id)

    @app.post("/bookings/check")
    @staff_required
    def booking_check_new():
        data = booking_form_data()
        try:
            booking = parse_booking(data)
            with db() as api:
                notice = check_slot(api, booking, None)
            return render_booking_form(data, booking_id=None, notice=notice)
        except Exception as exc:
            return render_booking_form(data, booking_id=None, error=str(exc))

    @app.post("/bookings/<int:booking_id>/check")
    @staff_required
    def booking_check_edit(booking_id: int):
        data = booking_form_data()
        try:
            booking = parse_booking(data)
            with db() as api:
                notice = check_slot(api, booking, booking_id)
            return render_booking_form(data, booking_id=booking_id, notice=notice)
        except Exception as exc:
            return render_booking_form(data, booking_id=booking_id, error=str(exc))

    @app.post("/bookings/<int:booking_id>/delete")
    @staff_required
    def booking_delete(booking_id: int):
        with db() as api:
            api.delete_booking(booking_id)
        return redirect(url_for("bookings"))

    @app.errorhandler(403)
    def forbidden(_exc):
        return render_template("error.html", code=403, message="Недостаточно прав."), 403

    return app


def main() -> None:
    """Локальный запуск (только для отладки). В Docker используется gunicorn."""
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    create_app().run(host=host, port=port, debug=debug)


app = create_app()


if __name__ == "__main__":
    main()
