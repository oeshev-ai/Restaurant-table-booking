"""Аутентификация и проверка ролей для веб-интерфейса."""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from flask import abort, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from Models.user import LOGIN_ROLES, ROLE_ADMIN, ROLE_STAFF, User
from backend import Backend

F = TypeVar("F", bound=Callable[..., object])


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    # Старые демо-хеши вида hash_ivanov не принимаем.
    if not password_hash.startswith(("pbkdf2:", "scrypt:", "argon2:")):
        return False
    return check_password_hash(password_hash, password)


def login_user(user: User) -> None:
    session.clear()
    session["user_id"] = user.id
    session["user_role"] = user.role
    session["user_name"] = user.full_name
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_user_id() -> int | None:
    raw = session.get("user_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def load_current_user(api: Backend) -> User | None:
    user_id = current_user_id()
    if user_id is None:
        return None
    user = api.get_user(user_id)
    if user is None or not user.can_login():
        logout_user()
        return None
    return user


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def roles_required(*roles: str) -> Callable[[F], F]:
    allowed = frozenset(roles)

    def decorator(view: F) -> F:
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if user is None:
                return redirect(url_for("login", next=request.path))
            if user.role not in allowed:
                abort(403)
            return view(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


admin_required = roles_required(ROLE_ADMIN)
staff_required = roles_required(ROLE_ADMIN, ROLE_STAFF)


def authenticate(api: Backend, email: str, password: str) -> User | None:
    user = api.get_user_by_email(email.strip().lower())
    if user is None:
        return None
    if user.role not in LOGIN_ROLES or not user.is_active:
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user
