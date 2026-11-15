#!/usr/bin/env python3
"""Codeflow Desktop: офлайн-приложение для Windows на стандартном Tkinter.

Не открывает браузер и не загружает внешние ресурсы. Тексты курсов и справочника
читаются из соседних JSON-файлов, прогресс сохраняется в профиле пользователя.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from functools import lru_cache
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

APP_DIR = Path(__file__).resolve().parent
COURSE_DATA_PATH = APP_DIR / "desktop-course-data.json"
REFERENCE_DATA_PATH = APP_DIR / "desktop-reference-data.json"

COLORS = {
    "background": "#f8f3f5",
    "surface": "#fffdfd",
    "surface_alt": "#fbf6f8",
    "sidebar": "#f3e9ee",
    "accent": "#a65e7e",
    "accent_dark": "#81435f",
    "accent_light": "#f5e3eb",
    "border": "#e8dce2",
    "text": "#382f35",
    "muted": "#756a71",
    "success": "#36765b",
    "success_bg": "#eaf5ee",
    "error": "#9e4651",
    "error_bg": "#fbebed",
    "code": "#f7f3f5",
    "white": "#ffffff",
}

DEFAULT_STATE: dict[str, Any] = {
    "version": 1,
    "xp": 0,
    "completed": [],
    "quizzes": [],
    "quiz_answers": {},
    "drafts": {},
    "failures": {},
    "python_warning_seen": False,
}


# --- Local files, progress, and data-driven code validation ---
def progress_path() -> Path:
    """Keep progress outside the extracted program folder where possible."""

    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return root / "Codeflow" / "desktop-progress.json"
    return Path.home() / ".codeflow-desktop" / "progress.json"


def read_json(path: Path) -> Any:
    """Read one UTF-8 JSON file without hiding file or parse errors."""
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


@lru_cache(maxsize=1200)
def _compiled_pattern(source: str, flags: str) -> re.Pattern[str]:
    python_flags = re.IGNORECASE if "i" in flags else 0
    return re.compile(source, python_flags)


def check_validation(
    rule: dict[str, Any], regex_patterns: list[dict[str, str]], source_code: str
) -> bool:
    """Evaluate the data-only validator tree exported with the web lessons."""
    rule_type = rule["type"]
    if rule_type == "pattern":
        pattern = regex_patterns[rule["index"]]
        return _compiled_pattern(pattern["source"], pattern["flags"]).search(source_code) is not None
    if rule_type == "count":
        pattern = regex_patterns[rule["index"]]
        match_count = sum(
            1 for _ in _compiled_pattern(pattern["source"], pattern["flags"]).finditer(source_code)
        )
        return match_count >= rule["min"]
    if rule_type == "not":
        return not check_validation(rule["value"], regex_patterns, source_code)
    if rule_type == "and":
        return check_validation(rule["left"], regex_patterns, source_code) and check_validation(
            rule["right"], regex_patterns, source_code
        )
    if rule_type == "or":
        return check_validation(rule["left"], regex_patterns, source_code) or check_validation(
            rule["right"], regex_patterns, source_code
        )
    raise ValueError(f"Unknown validation rule: {rule_type}")


# --- Reusable scrolling container ---
class ScrollArea(tk.Frame):
    """A lightweight scrollable frame using only Tkinter."""

    def __init__(self, parent: tk.Misc, *, background: str = COLORS["background"]) -> None:
        super().__init__(parent, bg=background)
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=background)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.bind("<MouseWheel>", self._mousewheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(1, "units"))

    def _update_scroll_region(self, _event: tk.Event[Any]) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_inner(self, event: tk.Event[Any]) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)

    def _mousewheel(self, event: tk.Event[Any]) -> None:
        step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step * max(1, abs(event.delta) // 120), "units")

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)


class CodeflowDesktop:
    """Own the desktop UI, learner state, and offline course interactions."""

    def __init__(self, root: tk.Tk) -> None:
        """Load local course data, restore progress, and build the main window."""
        self.root = root
        self.root.title("Codeflow — офлайн-приложение")
        self.root.geometry("1280x820")
        self.root.minsize(1020, 680)
        self.root.configure(bg=COLORS["background"])
        self._set_window_icon()
        self._configure_styles()

        try:
            raw_courses = read_json(COURSE_DATA_PATH)
            self.courses: list[dict[str, Any]] = raw_courses["courses"]
            self.references: list[dict[str, Any]] = read_json(REFERENCE_DATA_PATH)
        except (OSError, json.JSONDecodeError, KeyError) as error:
            messagebox.showerror(
                "Не удалось загрузить Codeflow",
                "Рядом с программой должны лежать desktop-course-data.json и "
                f"desktop-reference-data.json.\n\nПодробности: {error}",
            )
            raise

        self.courses_by_id = {course["id"]: course for course in self.courses}
        self.state_file = progress_path()
        self.state = self._load_state()
        self.completed = set(self.state.get("completed", []))
        self.quizzes = set(self.state.get("quizzes", []))
        self.current_course: dict[str, Any] | None = None
        self.current_lesson_index = 0
        self.current_lesson: dict[str, Any] | None = None
        self.current_editor: tk.Text | None = None
        self.current_lesson_list: tk.Listbox | None = None
        self.current_progressbar: ttk.Progressbar | None = None
        self.current_progress_label: tk.Label | None = None
        self.code_feedback: tk.Label | None = None
        self.hint_frame: tk.Frame | None = None
        self.hint_visible = False
        self.quiz_choice = tk.IntVar(value=-1)
        self.practice: dict[str, Any] | None = None
        self.practice_choice = tk.IntVar(value=-1)
        self.practice_answered = False
        self.filtered_references: list[dict[str, Any]] = []
        self._draft_after: str | None = None

        self._build_shell()
        self.root.bind("<Control-s>", lambda _event: self.save_progress())
        self.root.bind("<Control-Return>", lambda _event: self.check_code())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_home()

    # --- Window setup, persisted state, and the shared application shell ---
    def _set_window_icon(self) -> None:
        ico = APP_DIR / "codeflow.ico"
        png = APP_DIR / "icons" / "codeflow-192.png"
        try:
            if os.name == "nt" and ico.exists():
                self.root.iconbitmap(str(ico))
            elif png.exists():
                image = tk.PhotoImage(file=str(png))
                self.root.iconphoto(True, image)
                self._icon_image = image
        except tk.TclError:
            pass

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLORS["background"])
        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure(
            "TProgressbar",
            troughcolor=COLORS["accent_light"],
            background=COLORS["accent"],
            bordercolor=COLORS["accent_light"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent"],
        )
        style.configure(
            "Treeview",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["surface"],
            rowheight=28,
            font=("Segoe UI", 10),
        )
        style.map("Treeview", background=[("selected", COLORS["accent_light"])], foreground=[("selected", COLORS["text"])])

    def _load_state(self) -> dict[str, Any]:
        state = deepcopy(DEFAULT_STATE)
        try:
            if self.state_file.exists():
                saved = read_json(self.state_file)
                if isinstance(saved, dict):
                    state.update(saved)
        except (OSError, json.JSONDecodeError):
            pass
        return state

    def save_progress(self) -> None:
        self._save_current_draft()
        self.state["completed"] = sorted(self.completed)
        self.state["quizzes"] = sorted(self.quizzes)
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.state_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.state_file)
            self._set_status("Прогресс сохранён на этом компьютере.")
        except OSError as error:
            messagebox.showerror("Не удалось сохранить прогресс", str(error))

    def _save_current_draft(self) -> None:
        if self.current_course is None or self.current_editor is None:
            return
        key = self._lesson_key(self.current_course["id"], self.current_lesson_index)
        self.state.setdefault("drafts", {})[key] = self.current_editor.get("1.0", "end-1c")

    @staticmethod
    def _lesson_key(course_id: str, index: int) -> str:
        return f"{course_id}:{index}"

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def _build_shell(self) -> None:
        header = tk.Frame(self.root, bg=COLORS["accent_dark"], height=68)
        header.pack(fill="x")
        header.pack_propagate(False)
        brand = tk.Frame(header, bg=COLORS["accent_dark"])
        brand.pack(side="left", padx=(22, 28), fill="y")
        tk.Label(
            brand,
            text="🌸 Codeflow",
            bg=COLORS["accent_dark"],
            fg=COLORS["white"],
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w", pady=(10, 0))
        tk.Label(
            brand,
            text="ОФЛАЙН · ОТДЕЛЬНОЕ ОКНО · БЕЗ БРАУЗЕРА",
            bg=COLORS["accent_dark"],
            fg="#f7e8ee",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")

        nav = tk.Frame(header, bg=COLORS["accent_dark"])
        nav.pack(side="right", padx=16, fill="y")
        self.nav_buttons: dict[str, tk.Button] = {}
        for key, title, action in [
            ("courses", "Курсы", self.show_home),
            ("reference", "Справочник", self.show_reference),
            ("practice", "Тренировка", self.show_practice),
            ("progress", "Прогресс", self.show_progress),
        ]:
            button = tk.Button(
                nav,
                text=title,
                command=action,
                bg=COLORS["accent_dark"],
                fg=COLORS["white"],
                activebackground=COLORS["accent"],
                activeforeground=COLORS["white"],
                relief="flat",
                bd=0,
                padx=13,
                pady=10,
                cursor="hand2",
                font=("Segoe UI", 10, "bold"),
            )
            button.pack(side="left", padx=3, pady=12)
            self.nav_buttons[key] = button

        body = tk.Frame(self.root, bg=COLORS["background"])
        body.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(body, bg=COLORS["sidebar"], width=245)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(
            self.sidebar,
            text="МОЯ ТРАЕКТОРИЯ",
            bg=COLORS["sidebar"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=18, pady=(20, 8))
        self.course_nav = tk.Frame(self.sidebar, bg=COLORS["sidebar"])
        self.course_nav.pack(fill="x", padx=10)
        self.course_nav_buttons: dict[str, tk.Button] = {}
        for course in self.courses:
            button = tk.Button(
                self.course_nav,
                text=f"{course['icon']}  {course['name']}",
                command=lambda course_id=course["id"]: self.show_course(course_id),
                anchor="w",
                bg=COLORS["sidebar"],
                fg=COLORS["text"],
                activebackground=COLORS["accent_light"],
                activeforeground=COLORS["accent_dark"],
                relief="flat",
                bd=0,
                padx=10,
                pady=7,
                cursor="hand2",
                font=("Segoe UI", 10),
            )
            button.pack(fill="x", pady=1)
            self.course_nav_buttons[course["id"]] = button

        tk.Frame(self.sidebar, bg=COLORS["border"], height=1).pack(fill="x", padx=16, pady=14)
        tk.Label(
            self.sidebar,
            text="Сеть не нужна.\nКурсы и справочник\nзагружаются из файлов\nэтого комплекта.",
            justify="left",
            bg=COLORS["sidebar"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=18)

        self.page = tk.Frame(body, bg=COLORS["background"])
        self.page.pack(side="left", fill="both", expand=True)
        footer = tk.Frame(self.root, bg=COLORS["surface"], height=28)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.status_label = tk.Label(
            footer,
            text="Готово к работе офлайн.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            anchor="w",
            padx=16,
            font=("Segoe UI", 9),
        )
        self.status_label.pack(fill="both", expand=True)

    # --- Shared navigation and reusable widget helpers ---
    def _highlight_nav(self, active: str) -> None:
        for key, button in self.nav_buttons.items():
            button.configure(bg=COLORS["accent"] if key == active else COLORS["accent_dark"])

    def _highlight_course(self, active: str | None) -> None:
        for course_id, button in self.course_nav_buttons.items():
            selected = course_id == active
            button.configure(
                bg=COLORS["accent_light"] if selected else COLORS["sidebar"],
                fg=COLORS["accent_dark"] if selected else COLORS["text"],
                font=("Segoe UI", 10, "bold" if selected else "normal"),
            )

    def _clear_page(self) -> None:
        self._save_current_draft()
        self.save_progress()
        for child in self.page.winfo_children():
            child.destroy()
        self.current_editor = None
        self.current_lesson_list = None
        self.current_progressbar = None
        self.current_progress_label = None
        self.code_feedback = None
        self.hint_frame = None

    @staticmethod
    def _make_button(
        parent: tk.Misc,
        text: str,
        command: Any,
        *,
        primary: bool = False,
        small: bool = False,
    ) -> tk.Button:
        bg = COLORS["accent"] if primary else COLORS["surface"]
        fg = COLORS["white"] if primary else COLORS["accent_dark"]
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=COLORS["accent_dark"] if primary else COLORS["accent_light"],
            activeforeground=COLORS["white"] if primary else COLORS["accent_dark"],
            relief="flat",
            bd=0,
            padx=12 if not small else 9,
            pady=8 if not small else 5,
            cursor="hand2",
            font=("Segoe UI", 9 if small else 10, "bold" if primary else "normal"),
        )

    @staticmethod
    def _label(
        parent: tk.Misc,
        text: str,
        *,
        size: int = 10,
        bold: bool = False,
        color: str | None = None,
        background: str | None = None,
        wrap: int = 760,
        **kwargs: Any,
    ) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=background or COLORS["background"],
            fg=color or COLORS["text"],
            font=("Segoe UI", size, "bold" if bold else "normal"),
            justify="left",
            anchor="w",
            wraplength=wrap,
            **kwargs,
        )

    def _card(self, parent: tk.Misc, *, padding: int = 16) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            bd=0,
            padx=padding,
            pady=padding,
        )
        return card

    # --- Course navigation and lesson selection ---
    def show_home(self) -> None:
        self._clear_page()
        self.current_course = None
        self._highlight_nav("courses")
        self._highlight_course(None)
        scroll = ScrollArea(self.page)
        scroll.pack(fill="both", expand=True)
        inner = scroll.inner
        self._label(inner, "Codeflow — учись без интернета", size=23, bold=True, wrap=900).pack(
            anchor="w", padx=28, pady=(26, 4)
        )
        self._label(
            inner,
            "Отдельное Windows-окно, локальные уроки и справочник. Обычный браузер не открывается; прогресс остаётся на этом компьютере.",
            size=11,
            color=COLORS["muted"],
            wrap=950,
        ).pack(anchor="w", padx=28, pady=(0, 18))
        summary = self._card(inner)
        summary.pack(fill="x", padx=28, pady=(0, 20))
        tk.Label(
            summary,
            text=(
                f"{len(self.courses)} курсов   ·   "
                f"{sum(len(course['lessons']) for course in self.courses)} уроков   ·   "
                f"{len(self.references)} карточек справочника"
            ),
            bg=COLORS["surface"],
            fg=COLORS["accent_dark"],
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        grid = tk.Frame(inner, bg=COLORS["background"])
        grid.pack(fill="x", padx=24, pady=(0, 28))
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1, uniform="course")
        for index, course in enumerate(self.courses):
            done = self._course_completed_count(course["id"])
            total = len(course["lessons"])
            card = self._card(grid, padding=15)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=5, pady=5)
            top = tk.Frame(card, bg=COLORS["surface"])
            top.pack(fill="x")
            tk.Label(top, text=course["icon"], bg=COLORS["surface"], fg=COLORS["accent"], font=("Segoe UI Emoji", 19)).pack(side="left", padx=(0, 10))
            tk.Label(top, text=course["name"], bg=COLORS["surface"], fg=COLORS["text"], font=("Segoe UI", 14, "bold")).pack(side="left")
            self._label(
                card,
                course.get("description", ""),
                size=9,
                color=COLORS["muted"],
                background=COLORS["surface"],
                wrap=420,
            ).pack(anchor="w", pady=(9, 7))
            ttk.Progressbar(card, maximum=total, value=done).pack(fill="x", pady=(1, 4))
            tk.Label(
                card,
                text=f"{done} из {total} уроков · {round(done * 100 / max(total, 1))}%",
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")
            self._make_button(
                card,
                "Открыть курс →",
                lambda course_id=course["id"]: self.show_course(course_id),
                primary=True,
                small=True,
            ).pack(anchor="e", pady=(10, 0))

    def _course_completed_count(self, course_id: str) -> int:
        prefix = course_id + ":"
        return sum(1 for key in self.completed if key.startswith(prefix))

    def show_course(self, course_id: str, lesson_index: int = 0) -> None:
        self._clear_page()
        course = self.courses_by_id.get(course_id)
        if not course:
            self.show_home()
            return
        self.current_course = course
        lesson_index = max(0, min(lesson_index, len(course["lessons"]) - 1))
        self.current_lesson_index = lesson_index
        self._highlight_nav("courses")
        self._highlight_course(course_id)

        heading = tk.Frame(self.page, bg=COLORS["background"])
        heading.pack(fill="x", padx=20, pady=(15, 9))
        title_line = tk.Frame(heading, bg=COLORS["background"])
        title_line.pack(fill="x")
        self._label(title_line, f"{course['icon']}  {course['name']}", size=20, bold=True, wrap=780).pack(side="left", anchor="w")
        self.current_progress_label = tk.Label(title_line, text="", bg=COLORS["background"], fg=COLORS["muted"], font=("Segoe UI", 9))
        self.current_progress_label.pack(side="right")
        done = self._course_completed_count(course_id)
        self.current_progress_label.configure(text=f"{done}/{len(course['lessons'])} уроков")
        self.current_progressbar = ttk.Progressbar(heading, maximum=len(course["lessons"]), value=done)
        self.current_progressbar.pack(fill="x", pady=(7, 0))

        split = tk.Frame(self.page, bg=COLORS["background"])
        split.pack(fill="both", expand=True, padx=15, pady=(0, 12))
        left = tk.Frame(split, bg=COLORS["surface"], width=285, highlightbackground=COLORS["border"], highlightthickness=1)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        self._label(left, "УРОКИ", size=9, bold=True, color=COLORS["muted"], background=COLORS["surface"]).pack(anchor="w", padx=12, pady=(12, 7))
        list_frame = tk.Frame(left, bg=COLORS["surface"])
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical")
        self.current_lesson_list = tk.Listbox(
            list_frame,
            activestyle="none",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent_light"],
            selectforeground=COLORS["accent_dark"],
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
            yscrollcommand=list_scroll.set,
        )
        list_scroll.configure(command=self.current_lesson_list.yview)
        list_scroll.pack(side="right", fill="y")
        self.current_lesson_list.pack(side="left", fill="both", expand=True)
        for index, lesson in enumerate(course["lessons"]):
            key = self._lesson_key(course_id, index)
            mark = "✓" if key in self.completed else "·"
            self.current_lesson_list.insert("end", f"{mark}  {index + 1:02d}. {lesson['title']}")
        self.current_lesson_list.bind("<<ListboxSelect>>", self._lesson_selected)

        self.lesson_area = ScrollArea(split)
        self.lesson_area.pack(side="left", fill="both", expand=True)
        self.render_lesson(lesson_index)
        self.current_lesson_list.selection_clear(0, "end")
        self.current_lesson_list.selection_set(lesson_index)
        self.current_lesson_list.see(lesson_index)

    def _lesson_selected(self, _event: tk.Event[Any]) -> None:
        if self.current_lesson_list is None:
            return
        selection = self.current_lesson_list.curselection()
        if selection:
            self._save_current_draft()
            self.current_lesson_index = int(selection[0])
            self.render_lesson(self.current_lesson_index)

    def render_lesson(self, index: int) -> None:
        if self.current_course is None:
            return
        lessons = self.current_course["lessons"]
        if not 0 <= index < len(lessons):
            return
        self.current_lesson_index = index
        self.current_lesson = lessons[index]
        inner = self.lesson_area.inner
        for child in inner.winfo_children():
            child.destroy()
        lesson = self.current_lesson
        self.hint_visible = False
        course_id = self.current_course["id"]
        key = self._lesson_key(course_id, index)
        inner.columnconfigure(0, weight=1)

        heading = tk.Frame(inner, bg=COLORS["background"])
        heading.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 5))
        self._label(
            heading,
            f"МОДУЛЬ {index // 8 + 1}  ·  УРОК {index + 1}/{len(lessons)}  ·  {lesson.get('duration', '')}",
            size=8,
            bold=True,
            color=COLORS["accent_dark"],
            wrap=820,
        ).pack(anchor="w")
        self._label(heading, lesson["title"], size=18, bold=True, wrap=820).pack(anchor="w", pady=(4, 4))
        self._label(heading, f"Файл: {lesson.get('file') or self.current_course['file']}", size=9, color=COLORS["muted"], wrap=820).pack(anchor="w")

        intro = self._card(inner)
        intro.grid(row=1, column=0, sticky="ew", padx=18, pady=6)
        self._label(intro, "Коротко о главном", size=11, bold=True, background=COLORS["surface"]).pack(anchor="w")
        self._label(intro, lesson.get("intro", ""), size=10, background=COLORS["surface"], wrap=820).pack(anchor="w", pady=(7, 0))

        example = self._card(inner)
        example.grid(row=2, column=0, sticky="ew", padx=18, pady=6)
        self._label(example, "Пример кода", size=11, bold=True, background=COLORS["surface"]).pack(anchor="w", pady=(0, 8))
        self._code_view(example, lesson.get("example", ""), height=9)

        tip = tk.Frame(inner, bg=COLORS["accent_light"], padx=14, pady=10)
        tip.grid(row=3, column=0, sticky="ew", padx=18, pady=6)
        self._label(tip, "На заметку: " + lesson.get("tip", ""), size=9, background=COLORS["accent_light"], wrap=820).pack(anchor="w")

        quiz_card = self._card(inner)
        quiz_card.grid(row=4, column=0, sticky="ew", padx=18, pady=6)
        quiz = lesson.get("quiz") or {}
        self._label(quiz_card, "Проверка понимания", size=11, bold=True, background=COLORS["surface"]).pack(anchor="w")
        self._label(quiz_card, quiz.get("question", ""), size=10, bold=True, background=COLORS["surface"], wrap=820).pack(anchor="w", pady=(7, 5))
        saved_choice = self.state.get("quiz_answers", {}).get(key, -1)
        self.quiz_choice = tk.IntVar(value=int(saved_choice) if isinstance(saved_choice, int) else -1)
        for option_index, option in enumerate(quiz.get("options", [])):
            tk.Radiobutton(
                quiz_card,
                text=str(option),
                value=option_index,
                variable=self.quiz_choice,
                bg=COLORS["surface"],
                fg=COLORS["text"],
                activebackground=COLORS["surface"],
                selectcolor=COLORS["accent_light"],
                anchor="w",
                justify="left",
                wraplength=780,
                font=("Segoe UI", 9),
            ).pack(anchor="w", fill="x", pady=1)
        quiz_actions = tk.Frame(quiz_card, bg=COLORS["surface"])
        quiz_actions.pack(fill="x", pady=(7, 0))
        self._make_button(quiz_actions, "Проверить ответ", lambda k=key, q=quiz: self.check_quiz(k, q), primary=True, small=True).pack(side="left")
        self.quiz_feedback = self._label(quiz_actions, "", size=9, background=COLORS["surface"], wrap=620)
        self.quiz_feedback.pack(side="left", padx=10)
        if key in self.quizzes:
            self.quiz_feedback.configure(text="Ответ уже зачтён. " + quiz.get("explain", ""), fg=COLORS["success"])

        task_card = self._card(inner)
        task_card.grid(row=5, column=0, sticky="ew", padx=18, pady=6)
        self._label(task_card, "Твоя задача", size=11, bold=True, background=COLORS["surface"]).pack(anchor="w")
        self._label(task_card, lesson.get("task", ""), size=10, background=COLORS["surface"], wrap=820).pack(anchor="w", pady=(7, 8))
        hint_row = tk.Frame(task_card, bg=COLORS["surface"])
        hint_row.pack(fill="x")
        self.hint_button = self._make_button(hint_row, "Показать подсказку", self.toggle_hint, small=True)
        self.hint_button.pack(side="left")
        self._make_button(hint_row, "Вставить шаблон", self.insert_template, small=True).pack(side="left", padx=6)
        self.hint_frame = tk.Frame(task_card, bg=COLORS["accent_light"], padx=10, pady=8)
        self.hint_frame.pack(fill="x", pady=(8, 0))
        self._label(self.hint_frame, lesson.get("hint", ""), size=9, background=COLORS["accent_light"], wrap=800).pack(anchor="w")
        if not self.hint_visible:
            self.hint_frame.pack_forget()

        editor_card = self._card(inner)
        editor_card.grid(row=6, column=0, sticky="ew", padx=18, pady=6)
        self._label(editor_card, "Редактор задания", size=11, bold=True, background=COLORS["surface"]).pack(anchor="w")
        self._label(
            editor_card,
            "Проверка использует те же критерии, что и курс. Черновики сохраняются локально.",
            size=9,
            color=COLORS["muted"],
            background=COLORS["surface"],
            wrap=820,
        ).pack(anchor="w", pady=(4, 8))
        editor_wrap = tk.Frame(editor_card, bg=COLORS["border"], padx=1, pady=1)
        editor_wrap.pack(fill="x")
        self.current_editor = tk.Text(
            editor_wrap,
            height=11,
            wrap="none",
            undo=True,
            bg=COLORS["code"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent_dark"],
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=9,
            font=("Consolas", 10),
        )
        self.current_editor.pack(fill="both", expand=True)
        draft = self.state.get("drafts", {}).get(key, "")
        if draft:
            self.current_editor.insert("1.0", draft)
        self.current_editor.bind("<KeyRelease>", self._schedule_draft_save)
        action_row = tk.Frame(editor_card, bg=COLORS["surface"])
        action_row.pack(fill="x", pady=(9, 0))
        self._make_button(action_row, "Проверить код", self.check_code, primary=True, small=True).pack(side="left")
        if course_id == "python":
            self._make_button(action_row, "Запустить Python…", self.run_python, small=True).pack(side="left", padx=6)
        self.code_feedback = self._label(action_row, "", size=9, background=COLORS["surface"], wrap=520)
        self.code_feedback.pack(side="left", padx=9)
        if key in self.completed:
            self.code_feedback.configure(text="✓ Урок уже отмечен как пройденный.", fg=COLORS["success"])
        self.run_output_label = self._label(editor_card, "", size=9, bold=True, background=COLORS["surface"], wrap=820)
        self.run_output_text = tk.Text(
            editor_card,
            height=7,
            wrap="word",
            bg=COLORS["code"],
            fg=COLORS["text"],
            relief="flat",
            borderwidth=0,
            padx=9,
            pady=7,
            font=("Consolas", 9),
        )
        self.run_output_text.configure(state="disabled")
        self._make_button(editor_card, "Сохранить черновик", self.save_progress, small=True).pack(anchor="e", pady=(7, 0))

        self.lesson_area.scroll_to_top()

    @staticmethod
    def _code_view(parent: tk.Misc, code: str, *, height: int = 8) -> None:
        lines = max(3, min(height, code.count("\n") + 2))
        text = tk.Text(
            parent,
            height=lines,
            wrap="none",
            bg=COLORS["code"],
            fg=COLORS["text"],
            relief="flat",
            borderwidth=0,
            padx=9,
            pady=7,
            font=("Consolas", 9),
        )
        text.insert("1.0", code)
        text.configure(state="disabled")
        text.pack(fill="x")

    # --- Lesson interaction, validation, and the local Python runner ---
    def toggle_hint(self) -> None:
        if self.hint_frame is None:
            return
        self.hint_visible = not self.hint_visible
        if self.hint_visible:
            self.hint_frame.pack(fill="x", pady=(8, 0))
            self.hint_button.configure(text="Скрыть подсказку")
        else:
            self.hint_frame.pack_forget()
            self.hint_button.configure(text="Показать подсказку")

    def insert_template(self) -> None:
        if not self.current_editor or not self.current_lesson:
            return
        self.current_editor.delete("1.0", "end")
        self.current_editor.insert("1.0", self.current_lesson.get("placeholder", ""))
        self.current_editor.focus_set()
        self._schedule_draft_save()

    def _persist_draft(self) -> None:
        self._save_current_draft()
        self.save_progress()
        self._draft_after = None

    def _schedule_draft_save(self, _event: tk.Event[Any] | None = None) -> None:
        if self._draft_after:
            try:
                self.root.after_cancel(self._draft_after)
            except tk.TclError:
                pass
        self._draft_after = self.root.after(700, self._persist_draft)

    def check_quiz(self, key: str, quiz: dict[str, Any]) -> None:
        choice = self.quiz_choice.get()
        if choice < 0:
            self.quiz_feedback.configure(text="Выбери вариант ответа.", fg=COLORS["muted"])
            return
        self.state.setdefault("quiz_answers", {})[key] = choice
        if choice == quiz.get("correct"):
            if key not in self.quizzes:
                self.quizzes.add(key)
                self.state["xp"] = int(self.state.get("xp", 0)) + 5
            self.quiz_feedback.configure(text="Верно! " + quiz.get("explain", ""), fg=COLORS["success"])
            self._set_status("Ответ засчитан: +5 XP.")
        else:
            self.quiz_feedback.configure(text="Пока нет. " + quiz.get("explain", ""), fg=COLORS["error"])
        self.save_progress()

    def check_code(self) -> None:
        if not self.current_course or not self.current_lesson or not self.current_editor:
            return
        self._save_current_draft()
        code = self.current_editor.get("1.0", "end-1c")
        key = self._lesson_key(self.current_course["id"], self.current_lesson_index)
        if not code.strip():
            self.code_feedback.configure(text="Сначала введи решение в редактор.", fg=COLORS["muted"])
            return
        try:
            valid = check_validation(
                self.current_lesson["validation"]["ast"],
                self.current_lesson["validation"]["patterns"],
                code,
            )
        except (KeyError, IndexError, re.error, ValueError) as error:
            self.code_feedback.configure(text=f"Не удалось проверить код: {error}", fg=COLORS["error"])
            return
        if valid:
            if key not in self.completed:
                self.completed.add(key)
                self.state["xp"] = int(self.state.get("xp", 0)) + 25
            self.state.setdefault("failures", {})[key] = 0
            self.code_feedback.configure(text="✓ Критерии выполнены. Урок засчитан.", fg=COLORS["success"])
            self._set_status("Решение принято: +25 XP.")
            if self.current_lesson_list:
                self.current_lesson_list.delete(self.current_lesson_index)
                self.current_lesson_list.insert(
                    self.current_lesson_index,
                    f"✓  {self.current_lesson_index + 1:02d}. {self.current_lesson['title']}",
                )
                self.current_lesson_list.selection_set(self.current_lesson_index)
            if self.current_progressbar and self.current_course:
                self.current_progressbar.configure(value=self._course_completed_count(self.current_course["id"]))
            if self.current_progress_label and self.current_course:
                self.current_progress_label.configure(
                    text=f"{self._course_completed_count(self.current_course['id'])}/{len(self.current_course['lessons'])} уроков"
                )
        else:
            failures = int(self.state.setdefault("failures", {}).get(key, 0)) + 1
            self.state["failures"][key] = failures
            self.code_feedback.configure(
                text="Пока не совпали все критерии. Открой подсказку и проверь обязательные части задания.",
                fg=COLORS["error"],
            )
            self._set_status(f"Проверка не пройдена (попытка {failures}). Черновик сохранён локально.")
        self.save_progress()

    def run_python(self) -> None:
        if not self.current_course or self.current_course["id"] != "python" or not self.current_editor:
            return
        code = self.current_editor.get("1.0", "end-1c")
        if not code.strip():
            self.code_feedback.configure(text="Сначала введи Python-код.", fg=COLORS["muted"])
            return
        if not self.state.get("python_warning_seen"):
            ok = messagebox.askyesno(
                "Запуск кода на компьютере",
                (
                    "Python-код выполняется с правами текущего пользователя. Это не песочница: "
                    "код может обращаться к файлам и сети. Запускай только код, которому доверяешь."
                    "\n\nПродолжить?"
                ),
                icon="warning",
            )
            if not ok:
                return
            self.state["python_warning_seen"] = True
        python_exe = self._python_executable()
        if not python_exe:
            messagebox.showerror("Python не найден", "Установи Python 3, затем запусти приложение снова.")
            return
        try:
            with tempfile.TemporaryDirectory(prefix="codeflow-run-") as temp_dir:
                script = Path(temp_dir) / "lesson.py"
                script.write_text(code, encoding="utf-8")
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                result = subprocess.run(
                    [python_exe, "-I", str(script)],
                    cwd=temp_dir,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    creationflags=flags,
                    check=False,
                )
                output = result.stdout or "(программа ничего не вывела)"
                output = output[:12000]
                if result.returncode:
                    output = f"Код завершения: {result.returncode}\n\n" + output
                self._show_run_output(output)
        except subprocess.TimeoutExpired:
            self._show_run_output("Время выполнения превысило 5 секунд. Процесс остановлен.")
        except OSError as error:
            self._show_run_output(f"Не удалось запустить Python: {error}")

    @staticmethod
    def _python_executable() -> str | None:
        running = Path(sys.executable)
        if running.name.lower() == "pythonw.exe":
            console = running.with_name("python.exe")
            if console.exists():
                return str(console)
        found = shutil.which("python") or shutil.which("python3")
        if found:
            return found
        return str(running) if running.exists() else None

    def _show_run_output(self, output: str) -> None:
        if not hasattr(self, "run_output_label") or not self.run_output_label.winfo_exists():
            return
        self.run_output_label.configure(text="Результат запуска")
        if not self.run_output_label.winfo_manager():
            self.run_output_label.pack(anchor="w", pady=(10, 5))
        if not self.run_output_text.winfo_manager():
            self.run_output_text.pack(fill="x")
        self.run_output_text.configure(state="normal")
        self.run_output_text.delete("1.0", "end")
        self.run_output_text.insert("1.0", output)
        self.run_output_text.configure(state="disabled")
        self._set_status("Локальный запуск завершён. Результат показан в уроке.")

    # --- Offline reference search and detail cards ---
    def show_reference(self) -> None:
        self._clear_page()
        self.current_course = None
        self._highlight_nav("reference")
        self._highlight_course(None)
        top = tk.Frame(self.page, bg=COLORS["background"])
        top.pack(fill="x", padx=20, pady=(17, 10))
        self._label(top, "Справочник", size=21, bold=True, wrap=900).pack(anchor="w")
        self._label(
            top,
            f"{len(self.references)} карточек: синтаксис, примеры, применение и частые ошибки.",
            size=10,
            color=COLORS["muted"],
            wrap=900,
        ).pack(anchor="w", pady=(3, 10))
        controls = tk.Frame(top, bg=COLORS["background"])
        controls.pack(fill="x")
        self.reference_search = tk.StringVar()
        search = tk.Entry(controls, textvariable=self.reference_search, font=("Segoe UI", 10), relief="solid", bd=1)
        search.pack(side="left", fill="x", expand=True, ipady=7)
        search.insert(0, "Искать по названию, синтаксису и объяснению…")
        self.reference_search.trace_add("write", self._refresh_reference_list)
        self.reference_course_filter = tk.StringVar(value="Все темы")
        course_names = ["Все темы"] + [course["name"] for course in self.courses]
        filter_box = ttk.Combobox(controls, textvariable=self.reference_course_filter, values=course_names, state="readonly", width=24)
        filter_box.pack(side="left", padx=(9, 0), ipady=4)
        filter_box.bind("<<ComboboxSelected>>", self._refresh_reference_list)
        self._ref_search_placeholder = "Искать по названию, синтаксису и объяснению…"
        search.bind("<FocusIn>", self._clear_search_placeholder)
        split = tk.Frame(self.page, bg=COLORS["background"])
        split.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        left = tk.Frame(split, bg=COLORS["surface"], width=310, highlightbackground=COLORS["border"], highlightthickness=1)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        self._label(left, "КАРТОЧКИ", size=9, bold=True, color=COLORS["muted"], background=COLORS["surface"]).pack(anchor="w", padx=10, pady=10)
        listbox_frame = tk.Frame(left, bg=COLORS["surface"])
        listbox_frame.pack(fill="both", expand=True, padx=7, pady=(0, 7))
        list_scroll = ttk.Scrollbar(listbox_frame, orient="vertical")
        self.reference_list = tk.Listbox(
            listbox_frame,
            activestyle="none",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent_light"],
            selectforeground=COLORS["accent_dark"],
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
            yscrollcommand=list_scroll.set,
        )
        list_scroll.configure(command=self.reference_list.yview)
        list_scroll.pack(side="right", fill="y")
        self.reference_list.pack(side="left", fill="both", expand=True)
        self.reference_list.bind("<<ListboxSelect>>", self._show_selected_reference)
        self.reference_detail = ScrollArea(split)
        self.reference_detail.pack(side="left", fill="both", expand=True)
        self._refresh_reference_list()
        self.reference_detail.inner.update_idletasks()

    def _clear_search_placeholder(self, _event: tk.Event[Any]) -> None:
        if self.reference_search.get() == getattr(self, "_ref_search_placeholder", ""):
            self.reference_search.set("")

    def _refresh_reference_list(self, *_args: Any) -> None:
        if not hasattr(self, "reference_list") or not self.reference_list.winfo_exists():
            return
        query = self.reference_search.get().strip().casefold()
        if query == getattr(self, "_ref_search_placeholder", "").casefold():
            query = ""
        selected_name = self.reference_course_filter.get() if hasattr(self, "reference_course_filter") else "Все темы"
        selected_ids = {
            course["id"] for course in self.courses if course["name"] == selected_name
        } if selected_name != "Все темы" else None
        self.filtered_references = []
        for card in self.references:
            if selected_ids is not None and card.get("course") not in selected_ids:
                continue
            searchable_fields = (
                "category",
                "name",
                "syntax",
                "description",
                "example",
                "note",
                "usage",
                "mistakes",
            )
            haystack = " ".join(str(card.get(field, "")) for field in searchable_fields).casefold()
            if query and query not in haystack:
                continue
            self.filtered_references.append(card)
        self.reference_list.delete(0, "end")
        for card in self.filtered_references:
            self.reference_list.insert("end", f"{card.get('name', 'Карточка')}  ·  {card.get('category', '')}")
        if self.filtered_references:
            self.reference_list.selection_set(0)
            self.reference_list.event_generate("<<ListboxSelect>>")
        else:
            self._render_reference(None)

    def _show_selected_reference(self, _event: tk.Event[Any]) -> None:
        selection = self.reference_list.curselection()
        if selection:
            self._render_reference(self.filtered_references[int(selection[0])])

    def _render_reference(self, card: dict[str, Any] | None) -> None:
        if not hasattr(self, "reference_detail") or not self.reference_detail.winfo_exists():
            return
        inner = self.reference_detail.inner
        for child in inner.winfo_children():
            child.destroy()
        if card is None:
            self._label(
                inner,
                "Ничего не найдено. Попробуй изменить запрос.",
                size=12,
                color=COLORS["muted"],
                wrap=700,
            ).pack(anchor="w", padx=22, pady=22)
            return
        content = self._card(inner)
        content.pack(fill="x", padx=18, pady=18)
        course = self.courses_by_id.get(card.get("course", ""), {})
        course_title = course.get("name", card.get("course", ""))
        self._label(
            content,
            f"{course_title}  ·  {card.get('category', '')}",
            size=9,
            bold=True,
            color=COLORS["accent_dark"],
            background=COLORS["surface"],
            wrap=760,
        ).pack(anchor="w")
        self._label(content, card.get("name", ""), size=19, bold=True, background=COLORS["surface"], wrap=760).pack(anchor="w", pady=(4, 12))
        for title, key, code in [
            ("Синтаксис", "syntax", True),
            ("Что делает", "description", False),
            ("Пример", "example", True),
            ("Нюанс", "note", False),
            ("Где применять", "usage", False),
            ("Типичные ошибки", "mistakes", False),
        ]:
            value = card.get(key, "")
            if not value:
                continue
            self._label(content, title, size=10, bold=True, background=COLORS["surface"]).pack(anchor="w", pady=(10, 4))
            if code:
                self._code_view(content, value, height=8)
            else:
                self._label(content, value, size=10, background=COLORS["surface"], wrap=780).pack(anchor="w")
        self.reference_detail.scroll_to_top()

    # --- Practice questions, progress, and backup/restore ---
    def show_practice(self) -> None:
        self._clear_page()
        self.current_course = None
        self._highlight_nav("practice")
        self._highlight_course(None)
        scroll = ScrollArea(self.page)
        scroll.pack(fill="both", expand=True)
        self.practice_area = scroll.inner
        self._render_practice(new_question=True)

    def _render_practice(self, *, new_question: bool) -> None:
        for child in self.practice_area.winfo_children():
            child.destroy()
        if new_question or self.practice is None:
            course = random.choice(self.courses)
            index = random.randrange(len(course["lessons"]))
            self.practice = {"course": course, "index": index, "lesson": course["lessons"][index]}
            self.practice_answered = False
            self.practice_choice = tk.IntVar(value=-1)
        course = self.practice["course"]
        lesson = self.practice["lesson"]
        card = self._card(self.practice_area, padding=22)
        card.pack(fill="x", padx=28, pady=28)
        self._label(card, "Быстрая тренировка", size=22, bold=True, background=COLORS["surface"]).pack(anchor="w")
        self._label(
            card,
            "Один вопрос из локальных курсов — без аккаунта и сети.",
            size=10,
            color=COLORS["muted"],
            background=COLORS["surface"],
        ).pack(anchor="w", pady=(3, 20))
        self._label(
            card,
            f"{course['icon']}  {course['name']}  ·  {lesson['title']}",
            size=11,
            bold=True,
            color=COLORS["accent_dark"],
            background=COLORS["surface"],
        ).pack(anchor="w", pady=(0, 8))
        quiz = lesson.get("quiz") or {}
        self._label(card, quiz.get("question", ""), size=14, bold=True, background=COLORS["surface"], wrap=850).pack(anchor="w", pady=(0, 10))
        for option_index, option in enumerate(quiz.get("options", [])):
            tk.Radiobutton(
                card,
                text=str(option),
                value=option_index,
                variable=self.practice_choice,
                bg=COLORS["surface"],
                fg=COLORS["text"],
                activebackground=COLORS["surface"],
                selectcolor=COLORS["accent_light"],
                anchor="w",
                justify="left",
                wraplength=820,
                font=("Segoe UI", 10),
            ).pack(anchor="w", fill="x", pady=2)
        actions = tk.Frame(card, bg=COLORS["surface"])
        actions.pack(fill="x", pady=(14, 5))
        self.practice_feedback = self._label(actions, "", size=10, background=COLORS["surface"], wrap=600)
        self.practice_feedback.pack(side="left", padx=(0, 10))
        self._make_button(actions, "Проверить", self.check_practice, primary=True, small=True).pack(side="left")
        self._make_button(actions, "Другой вопрос", lambda: self._render_practice(new_question=True), small=True).pack(side="left", padx=6)
        self._label(
            card,
            f"За верный ответ — +3 XP. Сейчас: {int(self.state.get('xp', 0))} XP.",
            size=9,
            color=COLORS["muted"],
            background=COLORS["surface"],
        ).pack(anchor="w", pady=(10, 0))

    def check_practice(self) -> None:
        if not self.practice:
            return
        quiz = self.practice["lesson"].get("quiz") or {}
        if self.practice_choice.get() < 0:
            self.practice_feedback.configure(text="Сначала выбери ответ.", fg=COLORS["muted"])
            return
        if self.practice_choice.get() == quiz.get("correct"):
            if not self.practice_answered:
                self.state["xp"] = int(self.state.get("xp", 0)) + 3
                self.practice_answered = True
            self.practice_feedback.configure(text="Верно! " + quiz.get("explain", ""), fg=COLORS["success"])
            self._set_status("Тренировка засчитана: +3 XP.")
        else:
            self.practice_feedback.configure(text="Пока нет. " + quiz.get("explain", ""), fg=COLORS["error"])
        self.save_progress()

    def show_progress(self) -> None:
        self._clear_page()
        self.current_course = None
        self._highlight_nav("progress")
        self._highlight_course(None)
        scroll = ScrollArea(self.page)
        scroll.pack(fill="both", expand=True)
        inner = scroll.inner
        total = sum(len(course["lessons"]) for course in self.courses)
        done = len(self.completed)
        self._label(inner, "Твой прогресс", size=22, bold=True, wrap=900).pack(anchor="w", padx=28, pady=(24, 8))
        summary = self._card(inner, padding=20)
        summary.pack(fill="x", padx=28, pady=(0, 18))
        tk.Label(
            summary,
            text=f"{done} / {total} уроков",
            bg=COLORS["surface"],
            fg=COLORS["accent_dark"],
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Progressbar(summary, maximum=total, value=done).pack(fill="x", pady=(9, 5))
        tk.Label(
            summary,
            text=f"{int(self.state.get('xp', 0))} XP  ·  {len(self.quizzes)} ответов в проверках понимания",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        for course in self.courses:
            card = self._card(inner, padding=13)
            card.pack(fill="x", padx=28, pady=4)
            completed = self._course_completed_count(course["id"])
            top = tk.Frame(card, bg=COLORS["surface"])
            top.pack(fill="x")
            tk.Label(
                top,
                text=f"{course['icon']}  {course['name']}",
                bg=COLORS["surface"],
                fg=COLORS["text"],
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left")
            tk.Label(
                top,
                text=f"{completed}/{len(course['lessons'])}",
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
            ).pack(side="right")
            ttk.Progressbar(card, maximum=len(course["lessons"]), value=completed).pack(fill="x", pady=(8, 0))
        backup = tk.Frame(inner, bg=COLORS["background"])
        backup.pack(fill="x", padx=28, pady=16)
        self._make_button(backup, "Экспортировать прогресс…", self.export_progress, primary=True, small=True).pack(side="left")
        self._make_button(backup, "Импортировать прогресс…", self.import_progress, small=True).pack(side="left", padx=8)

    def export_progress(self) -> None:
        self.save_progress()
        target = filedialog.asksaveasfilename(
            title="Сохранить резервную копию прогресса",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="codeflow-progress.json",
        )
        if not target:
            return
        try:
            Path(target).write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
            messagebox.showinfo("Готово", "Резервная копия прогресса сохранена.")
        except OSError as error:
            messagebox.showerror("Ошибка экспорта", str(error))

    def import_progress(self) -> None:
        source = filedialog.askopenfilename(title="Выбрать резервную копию", filetypes=[("JSON", "*.json")])
        if not source:
            return
        try:
            saved = read_json(Path(source))
            if not isinstance(saved, dict) or not isinstance(saved.get("completed", []), list):
                raise ValueError("Файл не похож на резервную копию Codeflow.")
            self.state.update(saved)
            self.completed = set(saved.get("completed", []))
            self.quizzes = set(saved.get("quizzes", []))
            self.save_progress()
            self.show_progress()
            messagebox.showinfo("Готово", "Прогресс импортирован.")
        except (OSError, json.JSONDecodeError, ValueError) as error:
            messagebox.showerror("Ошибка импорта", str(error))

    def close(self) -> None:
        self._save_current_draft()
        self.save_progress()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    CodeflowDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
