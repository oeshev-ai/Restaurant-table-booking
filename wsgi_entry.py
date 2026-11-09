"""Точка входа контейнера: схема БД, затем Gunicorn."""

from __future__ import annotations

import os
import sys


def main() -> None:
    from backend import Backend

    with Backend() as api:
        api.init_schema()

    os.environ["SKIP_SCHEMA_INIT"] = "1"
    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "-b",
            "0.0.0.0:5000",
            "-w",
            "2",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
            "app:app",
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — нужен ненулевой exit для Docker
        print(f"wsgi_entry failed: {exc}", file=sys.stderr)
        raise
