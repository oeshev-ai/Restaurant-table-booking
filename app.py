"""Графический интерфейс мини-системы бронирования ресторана."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable

from Models.booking import Booking
from Models.tables import Table
from Models.user import User
from backend import Backend

DT_FMT = "%Y-%m-%d %H:%M"
DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"
SIDEBAR_WIDTH = 220

# Код статуса в БД → подпись в интерфейсе
BOOKING_STATUS_LABELS: dict[str, str] = {
    "confirmed": "Подтверждено",
    "pending": "Ожидает",
    "cancelled": "Отменено",
}
BOOKING_STATUS_CODES: dict[str, str] = {
    label: code for code, label in BOOKING_STATUS_LABELS.items()
}


def parse_date(value: str) -> datetime:
    value = value.strip()
    try:
        return datetime.strptime(value, DATE_FMT)
    except ValueError as exc:
        raise ValueError(
            f"Некорректная дата: {value!r}. Ожидается формат YYYY-MM-DD"
        ) from exc


def parse_time(value: str) -> tuple[int, int]:
    value = value.strip()
    for fmt in (TIME_FMT, "%H:%M:%S"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.hour, parsed.minute
        except ValueError:
            continue
    raise ValueError(
        f"Некорректное время: {value!r}. Ожидается формат HH:MM"
    )


def combine_date_time(date_str: str, time_str: str) -> datetime:
    base = parse_date(date_str)
    hour, minute = parse_time(time_str)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def fmt_dt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(DT_FMT)
    return str(value)


def fmt_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(DATE_FMT)
    return str(value)


def fmt_time(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(TIME_FMT)
    return str(value)


def add_entry_row(
    parent: ttk.Frame,
    label: str,
    *,
    show: str | None = None,
    readonly: bool = False,
    width: int = 36,
) -> tuple[tk.StringVar, ttk.Entry]:
    row = ttk.Frame(parent)
    row.pack(fill=tk.X, pady=3)
    ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
    var = tk.StringVar()
    entry = ttk.Entry(row, textvariable=var, width=width, show=show or "")
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    if readonly:
        entry.configure(state="readonly")
    return var, entry


def set_readonly(entry: ttk.Entry, var: tk.StringVar, value: Any) -> None:
    entry.configure(state="normal")
    var.set("" if value is None else str(value))
    entry.configure(state="readonly")


def make_sidebar_button(parent: ttk.Frame, text: str, command: Callable[[], None]) -> None:
    ttk.Button(parent, text=text, command=command).pack(fill=tk.X, pady=3)


class BookingApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Система бронирования столов")
        self.geometry("1100x680")
        self.minsize(900, 560)

        self.api = Backend()
        self.status = tk.StringVar(value="Подключение...")
        self._ready = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill=tk.X)
        ttk.Button(top, text="Создать таблицы БД", command=self._init_schema).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(top, text="Переподключить БД", command=self._reconnect).pack(
            side=tk.LEFT
        )

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.users_tab = UsersTab(self.notebook, self)
        self.tables_tab = TablesTab(self.notebook, self)
        self.bookings_tab = BookingsTab(self.notebook, self)

        self.notebook.add(self.users_tab, text="Пользователи")
        self.notebook.add(self.tables_tab, text="Столы")
        self.notebook.add(self.bookings_tab, text="Бронирования")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        status_bar = ttk.Label(
            self, textvariable=self.status, relief=tk.SUNKEN, anchor=tk.W, padding=4
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def set_status(self, text: str) -> None:
        self.status.set(text)

    def run_api(self, action: Callable[[], Any], *, ok_message: str) -> Any:
        try:
            result = action()
            self.set_status(ok_message)
            return result
        except Exception as exc:
            self.set_status(f"Ошибка: {exc}")
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return None

    def reload_all(self) -> None:
        if not self._ready:
            return
        try:
            current = self.notebook.select()
        except tk.TclError:
            current = None

        for index, tab in enumerate(
            (self.users_tab, self.tables_tab, self.bookings_tab)
        ):
            self.notebook.select(index)
            self.update_idletasks()
            tab.refresh(quiet=True)

        if current:
            self.notebook.select(current)
        self.set_status("Данные загружены")

    def _on_tab_changed(self, _event: object = None) -> None:
        if not self._ready:
            return
        try:
            tab = self.nametowidget(self.notebook.select())
        except Exception:
            return
        if hasattr(tab, "refresh"):
            tab.refresh(quiet=True)

    def startup(self) -> None:
        try:
            self.api.connect()
            self.api.init_schema()
        except Exception as exc:
            self.set_status(f"Ошибка: {exc}")
            messagebox.showerror("Ошибка подключения", str(exc), parent=self)
            return

        self._ready = True
        self.update_idletasks()
        self.reload_all()

    def _init_schema(self) -> None:
        self.run_api(self.api.init_schema, ok_message="Таблицы созданы / уже существуют")

    def _reconnect(self) -> None:
        def reconnect() -> None:
            self.api.close()
            self.api.connect()

        if self.run_api(reconnect, ok_message="Переподключено") is None:
            return
        self._ready = True
        self.reload_all()

    def _on_close(self) -> None:
        try:
            self.api.close()
        except Exception:
            pass
        self.destroy()


class EntityTab(ttk.Frame):
    """Вкладка: список слева, панель управления и деталей справа."""

    columns: tuple[str, ...] = ()
    headings: dict[str, str] = {}
    list_title: str = "Список"
    manage_title: str = "Управление"
    details_title: str = "Информация"
    entity_title: str = "запись"
    add_button_text: str = "Добавить"
    filter_label: str = "Фильтр:"
    filter_options: tuple[str, ...] = ("Все",)

    def __init__(self, parent: ttk.Notebook, app: BookingApp) -> None:
        super().__init__(parent, padding=8)
        self.app = app
        self._items: list[Any] = []
        self.detail_vars: dict[str, tk.StringVar] = {}
        self._build()

    def _build(self) -> None:
        left = ttk.LabelFrame(self, text=self.list_title, padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            tree_frame, columns=self.columns, show="headings", selectmode="browse"
        )
        for col in self.columns:
            self.tree.heading(col, text=self.headings.get(col, col))
            self.tree.column(col, width=100, anchor=tk.W, stretch=True)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(
            tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self.open_edit())

        right = ttk.Frame(self, width=SIDEBAR_WIDTH)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        manage = ttk.LabelFrame(right, text=self.manage_title, padding=8)
        manage.pack(fill=tk.X, pady=(0, 8))
        make_sidebar_button(manage, self.add_button_text, self.open_create)
        make_sidebar_button(manage, "Редактировать", self.open_edit)
        make_sidebar_button(manage, "Удалить", self.delete)
        ttk.Separator(manage, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        make_sidebar_button(manage, "Обновить список", self.refresh)

        filt = ttk.Frame(right)
        filt.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(filt, text=self.filter_label).pack(anchor=tk.W)
        self.filter_var = tk.StringVar(value=self.filter_options[0])
        self.filter_combo = ttk.Combobox(
            filt,
            textvariable=self.filter_var,
            values=self.filter_options,
            state="readonly",
        )
        self.filter_combo.pack(fill=tk.X, pady=(4, 0))
        self.filter_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_filter())

        details = ttk.LabelFrame(right, text=self.details_title, padding=8)
        details.pack(fill=tk.BOTH, expand=True)
        ttk.Label(details, text="Детали", font=("", 9, "bold")).pack(anchor=tk.W)
        ttk.Separator(details, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        self.details_body = ttk.Frame(details)
        self.details_body.pack(fill=tk.BOTH, expand=True)
        self._build_details(self.details_body)
        self.clear_details()

    def _build_details(self, parent: ttk.Frame) -> None:
        raise NotImplementedError

    def _add_detail(self, parent: ttk.Frame, key: str, label: str) -> tk.StringVar:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=f"{label}:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar(value="—")
        ttk.Label(row, textvariable=var, anchor=tk.W, wraplength=120).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self.detail_vars[key] = var
        return var

    def set_details(self, values: dict[str, Any]) -> None:
        for key, var in self.detail_vars.items():
            value = values.get(key)
            var.set("—" if value in (None, "") else str(value))

    def clear_details(self) -> None:
        for var in self.detail_vars.values():
            var.set("—")

    def selected_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        return int(values[0])

    def require_id(self) -> int | None:
        item_id = self.selected_id()
        if item_id is None:
            messagebox.showwarning(
                "Внимание",
                f"Выберите {self.entity_title} в списке",
                parent=self,
            )
        return item_id

    def fill_tree(self, rows: list[tuple[Any, ...]]) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert(
                "",
                tk.END,
                values=tuple("" if v is None else str(v) for v in row),
            )
        self.tree.update_idletasks()

    def _on_select(self, _event: object = None) -> None:
        selection = self.tree.selection()
        if not selection:
            self.clear_details()
            return
        values = self.tree.item(selection[0], "values")
        self.show_details_from_values(values)

    def show_details_from_values(self, values: tuple[Any, ...] | list[Any]) -> None:
        raise NotImplementedError

    def apply_filter(self) -> None:
        self.render_items()

    def render_items(self) -> None:
        raise NotImplementedError

    def refresh(self, *, quiet: bool = False) -> None:
        raise NotImplementedError

    def open_create(self) -> None:
        raise NotImplementedError

    def open_edit(self) -> None:
        raise NotImplementedError

    def delete(self) -> None:
        raise NotImplementedError


class RecordDialog(tk.Toplevel):
    """Модальное окно ввода / редактирования записи."""

    def __init__(
        self,
        parent: tk.Tk,
        title: str,
        *,
        on_save: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.on_save = on_save
        self.result: dict[str, Any] | None = None
        self.saved: Any = None

        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill=tk.BOTH, expand=True)

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Сохранить", command=self._on_ok).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        self.grab_set()
        self.focus_set()

    def center_on_parent(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        pw = parent.winfo_rootx()
        ph = parent.winfo_rooty()
        px = parent.winfo_width()
        py = parent.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{pw + (px - w) // 2}+{ph + (py - h) // 2}")

    def collect(self) -> dict[str, Any]:
        raise NotImplementedError

    def _on_ok(self) -> None:
        try:
            data = self.collect()
        except ValueError as exc:
            messagebox.showwarning("Внимание", str(exc), parent=self)
            return

        if self.on_save is not None:
            try:
                self.saved = self.on_save(data)
            except Exception as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return

        self.result = data
        self.destroy()

    def show(self) -> dict[str, Any] | None:
        self.wait_window()
        return self.result


class UserDialog(RecordDialog):
    def __init__(
        self,
        parent: tk.Tk,
        *,
        user: User | None = None,
        on_save: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        title = "Изменить пользователя" if user else "Новый пользователь"
        super().__init__(parent, title, on_save=on_save)

        self.id_var, self.id_entry = add_entry_row(self.body, "ID (авто)", readonly=True)
        self.email_var, _ = add_entry_row(self.body, "Email")
        self.password_var, _ = add_entry_row(self.body, "Пароль (hash)", show="*")
        self.name_var, _ = add_entry_row(self.body, "ФИО")
        self.phone_var, _ = add_entry_row(self.body, "Телефон")
        self.active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.body, text="Активен", variable=self.active_var).pack(
            anchor=tk.W, pady=(6, 0)
        )

        if user is not None:
            set_readonly(self.id_entry, self.id_var, user.id)
            self.email_var.set(user.email)
            self.password_var.set(user.password_hash)
            self.name_var.set(user.full_name)
            self.phone_var.set(user.phone or "")
            self.active_var.set(user.is_active)

        self.center_on_parent(parent)

    def collect(self) -> dict[str, Any]:
        email = self.email_var.get().strip()
        password_hash = self.password_var.get().strip()
        full_name = self.name_var.get().strip()
        if not email or not password_hash or not full_name:
            raise ValueError("Заполните email, пароль (hash) и ФИО")
        return {
            "email": email,
            "password_hash": password_hash,
            "full_name": full_name,
            "phone": self.phone_var.get().strip() or None,
            "is_active": bool(self.active_var.get()),
        }


class TableDialog(RecordDialog):
    def __init__(
        self,
        parent: tk.Tk,
        *,
        table: Table | None = None,
        on_save: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        title = "Изменить стол" if table else "Новый стол"
        super().__init__(parent, title, on_save=on_save)

        self.id_var, self.id_entry = add_entry_row(self.body, "ID (авто)", readonly=True)
        self.number_var, _ = add_entry_row(self.body, "Номер стола")
        self.seats_var, _ = add_entry_row(self.body, "Вместимость")
        self.zone_var, _ = add_entry_row(self.body, "Расположение")
        self.active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.body, text="Активен", variable=self.active_var).pack(
            anchor=tk.W, pady=(6, 0)
        )

        self.seats_var.set("2")
        if table is not None:
            set_readonly(self.id_entry, self.id_var, table.id)
            self.number_var.set(str(table.number))
            self.seats_var.set(str(table.seats))
            self.zone_var.set(table.zone or "")
            self.active_var.set(table.is_active)

        self.center_on_parent(parent)

    def collect(self) -> dict[str, Any]:
        try:
            number = int(self.number_var.get().strip())
            seats = int(self.seats_var.get().strip() or "2")
        except ValueError as exc:
            raise ValueError(
                "Номер и вместимость должны быть целыми числами"
            ) from exc
        if seats <= 0:
            raise ValueError("Вместимость должна быть больше 0")
        return {
            "number": number,
            "seats": seats,
            "zone": self.zone_var.get().strip() or None,
            "is_active": bool(self.active_var.get()),
        }


class BookingDialog(RecordDialog):
    def __init__(
        self,
        parent: tk.Tk,
        app: BookingApp,
        *,
        booking: Booking | None = None,
        on_save: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        title = "Изменить бронирование" if booking else "Новое бронирование"
        super().__init__(parent, title, on_save=on_save)
        self.app = app
        self.booking_id = booking.id if booking is not None else None
        self.user_label_to_id: dict[str, int] = {}
        self.table_label_to_id: dict[str, int] = {}
        self.user_id_to_label: dict[int, str] = {}
        self.table_id_to_label: dict[int, str] = {}

        self.id_var, self.id_entry = add_entry_row(self.body, "ID (авто)", readonly=True)

        user_row = ttk.Frame(self.body)
        user_row.pack(fill=tk.X, pady=3)
        ttk.Label(user_row, text="Пользователь", width=16).pack(side=tk.LEFT)
        self.user_var = tk.StringVar()
        self.user_combo = ttk.Combobox(
            user_row, textvariable=self.user_var, state="readonly", width=34
        )
        self.user_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        table_row = ttk.Frame(self.body)
        table_row.pack(fill=tk.X, pady=3)
        ttk.Label(table_row, text="Стол", width=16).pack(side=tk.LEFT)
        self.table_var = tk.StringVar()
        self.table_combo = ttk.Combobox(
            table_row, textvariable=self.table_var, state="readonly", width=34
        )
        self.table_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.starts_date_var, self.starts_time_var = self._add_date_time_row(
            self.body, "Начало"
        )
        self.ends_date_var, self.ends_time_var = self._add_date_time_row(
            self.body, "Конец"
        )
        self.guests_var, _ = add_entry_row(self.body, "Гостей")

        status_row = ttk.Frame(self.body)
        status_row.pack(fill=tk.X, pady=3)
        ttk.Label(status_row, text="Статус", width=16).pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value=BOOKING_STATUS_LABELS["confirmed"])
        self.status_combo = ttk.Combobox(
            status_row,
            textvariable=self.status_var,
            values=tuple(BOOKING_STATUS_LABELS.values()),
            state="readonly",
            width=34,
        )
        self.status_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.comment_var, _ = add_entry_row(self.body, "Комментарий")

        self.guests_var.set("1")

        ttk.Label(
            self.body,
            text="Дата: YYYY-MM-DD · время: HH:MM",
            foreground="#555555",
        ).pack(anchor=tk.W, pady=(6, 0))

        ttk.Button(
            self.body,
            text="Проверить доступность",
            command=self.check_availability,
        ).pack(fill=tk.X, pady=(10, 0))

        self._load_lookups()

        if booking is not None:
            set_readonly(self.id_entry, self.id_var, booking.id)
            self.user_var.set(self._label_for_user(booking.user_id))
            self.table_var.set(self._label_for_table(booking.table_id))
            self.starts_date_var.set(fmt_date(booking.starts_at))
            self.starts_time_var.set(fmt_time(booking.starts_at))
            self.ends_date_var.set(fmt_date(booking.ends_at))
            self.ends_time_var.set(fmt_time(booking.ends_at))
            self.guests_var.set(str(booking.guests_count))
            self.status_var.set(self._status_label(booking.status))
            self.comment_var.set(booking.comment or "")
        else:
            today = datetime.now().strftime(DATE_FMT)
            self.starts_date_var.set(today)
            self.ends_date_var.set(today)

        self.center_on_parent(parent)

    @staticmethod
    def _status_label(code: str) -> str:
        return BOOKING_STATUS_LABELS.get(code, BOOKING_STATUS_LABELS["confirmed"])

    @staticmethod
    def _status_code(label: str) -> str:
        if label in BOOKING_STATUS_CODES:
            return BOOKING_STATUS_CODES[label]
        if label in BOOKING_STATUS_LABELS:
            return label
        return "confirmed"

    @staticmethod
    def _add_date_time_row(
        parent: ttk.Frame, label: str
    ) -> tuple[tk.StringVar, tk.StringVar]:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)

        date_var = tk.StringVar()
        ttk.Entry(row, textvariable=date_var, width=14).pack(side=tk.LEFT)
        ttk.Label(row, text="дата").pack(side=tk.LEFT, padx=(4, 8))

        time_var = tk.StringVar()
        ttk.Entry(row, textvariable=time_var, width=8).pack(side=tk.LEFT)
        ttk.Label(row, text="время").pack(side=tk.LEFT, padx=(4, 0))
        return date_var, time_var

    @staticmethod
    def _user_label(user: User) -> str:
        suffix = "" if user.is_active else " [неактивен]"
        return f"#{user.id} — {user.full_name} ({user.email}){suffix}"

    @staticmethod
    def _table_label(table: Table) -> str:
        zone = f", {table.zone}" if table.zone else ""
        return f"#{table.id} — стол {table.number} ({table.seats} мест{zone})"

    def _load_lookups(self) -> None:
        users = self.app.api.get_users()
        # Для бронирования доступны только активные столы.
        tables = self.app.api.get_tables(where={"is_active": True})

        user_labels: list[str] = []
        for user in users:
            if user.id is None:
                continue
            label = self._user_label(user)
            self.user_label_to_id[label] = user.id
            self.user_id_to_label[user.id] = label
            user_labels.append(label)

        table_labels: list[str] = []
        for table in tables:
            if table.id is None:
                continue
            label = self._table_label(table)
            self.table_label_to_id[label] = table.id
            self.table_id_to_label[table.id] = label
            table_labels.append(label)

        self.user_combo["values"] = user_labels
        self.table_combo["values"] = table_labels

    def _label_for_user(self, user_id: int) -> str:
        label = self.user_id_to_label.get(user_id)
        if label:
            return label
        label = f"#{user_id}"
        self.user_combo["values"] = [*self.user_combo["values"], label]
        self.user_label_to_id[label] = user_id
        return label

    def _label_for_table(self, table_id: int) -> str:
        label = self.table_id_to_label.get(table_id)
        if label:
            return label
        label = f"#{table_id}"
        self.table_combo["values"] = [*self.table_combo["values"], label]
        self.table_label_to_id[label] = table_id
        return label

    def collect(self) -> dict[str, Any]:
        user_label = self.user_var.get().strip()
        table_label = self.table_var.get().strip()
        if user_label not in self.user_label_to_id:
            raise ValueError("Выберите пользователя из списка")
        if table_label not in self.table_label_to_id:
            raise ValueError("Выберите стол из списка")
        try:
            guests_count = int(self.guests_var.get().strip() or "1")
        except ValueError as exc:
            raise ValueError("Число гостей должно быть целым") from exc
        if guests_count <= 0:
            raise ValueError("Число гостей должно быть больше 0")

        return {
            "user_id": self.user_label_to_id[user_label],
            "table_id": self.table_label_to_id[table_label],
            "starts_at": combine_date_time(
                self.starts_date_var.get(), self.starts_time_var.get()
            ),
            "ends_at": combine_date_time(
                self.ends_date_var.get(), self.ends_time_var.get()
            ),
            "guests_count": guests_count,
            "status": self._status_code(self.status_var.get().strip()),
            "comment": self.comment_var.get().strip() or None,
        }

    def check_availability(self) -> None:
        """Проверить пересечение с другими активными бронями того же стола."""
        try:
            table_label = self.table_var.get().strip()
            if table_label not in self.table_label_to_id:
                raise ValueError("Выберите стол из списка")

            starts_at = combine_date_time(
                self.starts_date_var.get(), self.starts_time_var.get()
            )
            ends_at = combine_date_time(
                self.ends_date_var.get(), self.ends_time_var.get()
            )
            if ends_at <= starts_at:
                raise ValueError("Время окончания должно быть позже времени начала")

            table_id = self.table_label_to_id[table_label]
            conflicts = self.app.api.find_conflicting_bookings(
                table_id,
                starts_at,
                ends_at,
                exclude_booking_id=self.booking_id,
            )
        except ValueError as exc:
            messagebox.showwarning("Внимание", str(exc), parent=self)
            return
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return

        if conflicts:
            conflict = conflicts[0]
            messagebox.showerror(
                "Стол недоступен",
                "Стол уже забронирован в это время "
                f"(бронь #{conflict.id}: {fmt_dt(conflict.starts_at)} — "
                f"{fmt_dt(conflict.ends_at)}).\n"
                "Выберите другой стол или другое время.",
                parent=self,
            )
            return

        messagebox.showinfo(
            "Стол доступен",
            "На выбранное время стол свободен — конфликтующих бронирований нет.",
            parent=self,
        )


class UsersTab(EntityTab):
    columns = ("id", "email", "full_name", "phone", "is_active", "created_at")
    headings = {
        "id": "ID",
        "email": "Email",
        "full_name": "ФИО",
        "phone": "Телефон",
        "is_active": "Статус",
        "created_at": "Создан",
    }
    list_title = "Список пользователей"
    manage_title = "Управление пользователями"
    details_title = "Информация о пользователе"
    entity_title = "пользователя"
    add_button_text = "Добавить пользователя"
    filter_label = "Фильтр по статусу:"
    filter_options = ("Все", "Активные", "Неактивные")

    def _build_details(self, parent: ttk.Frame) -> None:
        self._add_detail(parent, "id", "ID")
        self._add_detail(parent, "email", "Email")
        self._add_detail(parent, "full_name", "ФИО")
        self._add_detail(parent, "phone", "Телефон")
        self._add_detail(parent, "is_active", "Статус")
        self._add_detail(parent, "created_at", "Создан")

    def _status_text(self, active: bool) -> str:
        return "активен" if active else "неактивен"

    def _row(self, user: User) -> tuple[Any, ...]:
        return (
            user.id,
            user.email,
            user.full_name,
            user.phone or "",
            self._status_text(user.is_active),
            fmt_dt(user.created_at),
        )

    def show_details_from_values(self, values: tuple[Any, ...] | list[Any]) -> None:
        self.set_details(
            {
                "id": values[0],
                "email": values[1],
                "full_name": values[2],
                "phone": values[3],
                "is_active": values[4],
                "created_at": values[5],
            }
        )

    def render_items(self) -> None:
        mode = self.filter_var.get()
        rows: list[tuple[Any, ...]] = []
        for user in self._items:
            if mode == "Активные" and not user.is_active:
                continue
            if mode == "Неактивные" and user.is_active:
                continue
            rows.append(self._row(user))
        self.fill_tree(rows)
        self.clear_details()

    def refresh(self, *, quiet: bool = False) -> None:
        try:
            self._items = self.app.api.get_users()
        except Exception as exc:
            self.app.set_status(f"Ошибка: {exc}")
            if not quiet:
                messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.render_items()
        if not quiet:
            self.app.set_status("Список пользователей обновлён")

    def open_create(self) -> None:
        dialog = UserDialog(
            self.app,
            on_save=lambda data: self.app.api.create_user(User(**data)),
        )
        if dialog.show() is None:
            return
        self.app.set_status(f"Пользователь создан (id={dialog.saved.id})")
        self.refresh()

    def open_edit(self) -> None:
        user_id = self.require_id()
        if user_id is None:
            return
        user = self.app.run_api(
            lambda: self.app.api.get_user(user_id),
            ok_message=f"Редактирование пользователя {user_id}",
        )
        if user is None:
            if not self.app.status.get().startswith("Ошибка"):
                messagebox.showinfo("Результат", "Пользователь не найден", parent=self)
            return

        dialog = UserDialog(
            self.app,
            user=user,
            on_save=lambda data: self.app.api.update_user(user_id, data),
        )
        if dialog.show() is None:
            return
        self.app.set_status(f"Пользователь {user_id} обновлён")
        self.refresh()

    def delete(self) -> None:
        user_id = self.require_id()
        if user_id is None:
            return
        if not messagebox.askyesno(
            "Подтверждение",
            f"Удалить пользователя #{user_id}?",
            parent=self,
        ):
            return
        deleted = self.app.run_api(
            lambda: self.app.api.delete_user(user_id),
            ok_message=f"Пользователь {user_id} удалён",
        )
        if deleted is None and self.app.status.get().startswith("Ошибка"):
            return
        self.refresh()


class TablesTab(EntityTab):
    columns = ("id", "number", "seats", "zone", "is_active", "created_at")
    headings = {
        "id": "ID",
        "number": "Номер",
        "seats": "Вместимость",
        "zone": "Расположение",
        "is_active": "Статус",
        "created_at": "Создан",
    }
    list_title = "Список столов"
    manage_title = "Управление столами"
    details_title = "Информация о столе"
    entity_title = "стол"
    add_button_text = "Добавить стол"
    filter_label = "Фильтр по статусу:"
    filter_options = ("Все", "Активные", "Неактивные")

    def _build_details(self, parent: ttk.Frame) -> None:
        self._add_detail(parent, "id", "ID")
        self._add_detail(parent, "number", "Номер")
        self._add_detail(parent, "seats", "Вместимость")
        self._add_detail(parent, "zone", "Расположение")
        self._add_detail(parent, "is_active", "Статус")
        self._add_detail(parent, "created_at", "Создан")

    def _status_text(self, active: bool) -> str:
        return "Активен" if active else "Неактивен"

    def _row(self, table: Table) -> tuple[Any, ...]:
        return (
            table.id,
            table.number,
            table.seats,
            table.zone or "",
            self._status_text(table.is_active),
            fmt_dt(table.created_at),
        )

    def show_details_from_values(self, values: tuple[Any, ...] | list[Any]) -> None:
        self.set_details(
            {
                "id": values[0],
                "number": values[1],
                "seats": values[2],
                "zone": values[3],
                "is_active": values[4],
                "created_at": values[5],
            }
        )

    def render_items(self) -> None:
        mode = self.filter_var.get()
        rows: list[tuple[Any, ...]] = []
        for table in self._items:
            if mode == "Активные" and not table.is_active:
                continue
            if mode == "Неактивные" and table.is_active:
                continue
            rows.append(self._row(table))
        self.fill_tree(rows)
        self.clear_details()

    def refresh(self, *, quiet: bool = False) -> None:
        try:
            self._items = self.app.api.get_tables()
        except Exception as exc:
            self.app.set_status(f"Ошибка: {exc}")
            if not quiet:
                messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.render_items()
        if not quiet:
            self.app.set_status("Список столов обновлён")

    def open_create(self) -> None:
        dialog = TableDialog(
            self.app,
            on_save=lambda data: self.app.api.create_table(Table(**data)),
        )
        if dialog.show() is None:
            return
        self.app.set_status(f"Стол создан (id={dialog.saved.id})")
        self.refresh()

    def open_edit(self) -> None:
        table_id = self.require_id()
        if table_id is None:
            return
        table = self.app.run_api(
            lambda: self.app.api.get_table(table_id),
            ok_message=f"Редактирование стола {table_id}",
        )
        if table is None:
            if not self.app.status.get().startswith("Ошибка"):
                messagebox.showinfo("Результат", "Стол не найден", parent=self)
            return

        dialog = TableDialog(
            self.app,
            table=table,
            on_save=lambda data: self.app.api.update_table(table_id, data),
        )
        if dialog.show() is None:
            return
        self.app.set_status(f"Стол {table_id} обновлён")
        self.refresh()

    def delete(self) -> None:
        table_id = self.require_id()
        if table_id is None:
            return
        if not messagebox.askyesno(
            "Подтверждение", f"Удалить стол #{table_id}?", parent=self
        ):
            return
        deleted = self.app.run_api(
            lambda: self.app.api.delete_table(table_id),
            ok_message=f"Стол {table_id} удалён",
        )
        if deleted is None and self.app.status.get().startswith("Ошибка"):
            return
        self.refresh()


class BookingsTab(EntityTab):
    columns = (
        "id",
        "user_id",
        "table_id",
        "starts_at",
        "ends_at",
        "guests_count",
        "status",
        "comment",
    )
    headings = {
        "id": "ID",
        "user_id": "User ID",
        "table_id": "Table ID",
        "starts_at": "Начало",
        "ends_at": "Конец",
        "guests_count": "Гостей",
        "status": "Статус",
        "comment": "Комментарий",
    }
    list_title = "Список бронирований"
    manage_title = "Управление бронированиями"
    details_title = "Информация о бронировании"
    entity_title = "бронирование"
    add_button_text = "Добавить бронирование"
    filter_label = "Фильтр по статусу:"
    filter_options = ("Все", "Подтверждено", "Ожидает", "Отменено")

    def _build_details(self, parent: ttk.Frame) -> None:
        self._add_detail(parent, "id", "ID")
        self._add_detail(parent, "user_id", "Пользователь")
        self._add_detail(parent, "table_id", "Стол")
        self._add_detail(parent, "starts_at", "Начало")
        self._add_detail(parent, "ends_at", "Конец")
        self._add_detail(parent, "guests_count", "Гостей")
        self._add_detail(parent, "status", "Статус")
        self._add_detail(parent, "comment", "Комментарий")

    @staticmethod
    def _status_label(code: str) -> str:
        return BOOKING_STATUS_LABELS.get(code, code)

    def _row(self, booking: Booking) -> tuple[Any, ...]:
        return (
            booking.id,
            booking.user_id,
            booking.table_id,
            fmt_dt(booking.starts_at),
            fmt_dt(booking.ends_at),
            booking.guests_count,
            self._status_label(booking.status),
            booking.comment or "",
        )

    def show_details_from_values(self, values: tuple[Any, ...] | list[Any]) -> None:
        self.set_details(
            {
                "id": values[0],
                "user_id": values[1],
                "table_id": values[2],
                "starts_at": values[3],
                "ends_at": values[4],
                "guests_count": values[5],
                "status": values[6],
                "comment": values[7],
            }
        )

    def render_items(self) -> None:
        mode = self.filter_var.get()
        rows: list[tuple[Any, ...]] = []
        for booking in self._items:
            label = self._status_label(booking.status)
            if mode != "Все" and label != mode:
                continue
            rows.append(self._row(booking))
        self.fill_tree(rows)
        self.clear_details()

    def refresh(self, *, quiet: bool = False) -> None:
        try:
            self._items = self.app.api.get_bookings()
        except Exception as exc:
            self.app.set_status(f"Ошибка: {exc}")
            if not quiet:
                messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.render_items()
        if not quiet:
            self.app.set_status("Список бронирований обновлён")

    def open_create(self) -> None:
        dialog = BookingDialog(
            self.app,
            self.app,
            on_save=lambda data: self.app.api.create_booking(Booking(**data)),
        )
        if dialog.show() is None:
            return
        self.app.set_status(f"Бронирование создано (id={dialog.saved.id})")
        self.refresh()

    def open_edit(self) -> None:
        booking_id = self.require_id()
        if booking_id is None:
            return
        booking = self.app.run_api(
            lambda: self.app.api.get_booking(booking_id),
            ok_message=f"Редактирование бронирования {booking_id}",
        )
        if booking is None:
            if not self.app.status.get().startswith("Ошибка"):
                messagebox.showinfo("Результат", "Бронирование не найдено", parent=self)
            return

        dialog = BookingDialog(
            self.app,
            self.app,
            booking=booking,
            on_save=lambda data: self.app.api.update_booking(booking_id, data),
        )
        if dialog.show() is None:
            return
        self.app.set_status(f"Бронирование {booking_id} обновлено")
        self.refresh()

    def delete(self) -> None:
        booking_id = self.require_id()
        if booking_id is None:
            return
        if not messagebox.askyesno(
            "Подтверждение",
            f"Удалить бронирование #{booking_id}?",
            parent=self,
        ):
            return
        deleted = self.app.run_api(
            lambda: self.app.api.delete_booking(booking_id),
            ok_message=f"Бронирование {booking_id} удалено",
        )
        if deleted is None and self.app.status.get().startswith("Ошибка"):
            return
        self.refresh()


def main() -> None:
    app = BookingApp()
    app.startup()
    app.after(300, app.reload_all)
    app.mainloop()


if __name__ == "__main__":
    main()
