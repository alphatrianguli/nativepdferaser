"""Native PDF Eraser v1.0 - bilingual Windows desktop GUI (Tkinter)."""
from __future__ import annotations

import sys
from tempfile import TemporaryDirectory
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pymupdf
from PIL import Image, ImageTk

from engine import EditError, VerificationError, _check_document, _page_coords, inspect_selection, process_pdf
from universal import process_pdf_universal
from text_only import process_pdf_text_only
from smart_mixed import process_pdf_smart_mixed, classify_selections, _character_centers
from image_only import process_pdf_image_only
from match_pages import discover_same_area_matches
from repeat_match import discover_repeated_elements
from image_selection import image_candidates, bbox_to_display, snap_image_selections
from object_recognition import detect_object
from localization import translate, DE_EN

APP_TITLE = "Native PDF Eraser"
VERSION = "1.0"
INK = "#1B2E48"
BLUE = "#1564A7"
LIGHT = "#F1F6FA"
WHITE = "#FFFFFF"
MUTED = "#6B7280"
RED = "#1873B5"
GREEN = "#0F766E"

PAD = 18


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


class LocalizedStringVar(tk.StringVar):
    """Translate dynamic interface text without changing underlying PDF operations."""
    def __init__(self, master, value=""):
        self._raw_text = value
        self._owner = master
        super().__init__(master=master, value=master.tr(value))

    def set(self, value):
        self._raw_text = value
        super().set(self._owner.tr(str(value)))

    def retranslate(self):
        super().set(self._owner.tr(str(self._raw_text)))


class App(tk.Tk):
    def __init__(self, initial_file: str | None = None):
        super().__init__()
        self.title(f"{APP_TITLE}  |  v{VERSION}")
        self.geometry("1270x800")
        self.minsize(980, 650)
        self.configure(bg=LIGHT)
        self.lang = "en"  # Public release default; users can switch anytime.
        self.language_display = tk.StringVar(value="English")
        self.doc: pymupdf.Document | None = None
        self.preview_doc: pymupdf.Document | None = None
        self.source_path: Path | None = None
        self.result = None
        self._workspace: TemporaryDirectory | None = None
        self._history_paths: list[Path] = []
        self._history_results: list = []
        self._active_input_path: Path | None = None
        self.auto_detect = tk.BooleanVar(value=True)
        self.auto_find_pages = tk.BooleanVar(value=True)
        self.page_idx = 0
        self.selections: dict[int, list[pymupdf.Rect]] = {}
        self.undo_stack: list[tuple[int, pymupdf.Rect]] = []
        self.mode = "select"
        self.removal_mode = tk.StringVar(value="intelligent")
        self.preview = False
        self.zoom = 1.0
        self.zoom_fit = True
        self.image_id = None
        self._photo = None
        self._start_pdf: tuple[float, float] | None = None
        self._pending_item = None
        self._pan_active = False
        self._page_width_px = 0
        self._page_height_px = 0
        self._build_ui()
        self.set_language("en")
        self._set_window_icon()
        self._set_status(self.tr("PDF öffnen und Bereiche zum Entfernen markieren."))
        self._fit_initial_job = None
        self._startup_job = self.after(150, lambda: self.open_pdf(initial_file) if initial_file else None)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def tr(self, text: str) -> str:
        return translate(str(text), self.lang)

    def _translate_ui_tree(self, widget):
        """Translate fixed Tk widget labels while retaining widget state."""
        try:
            old = widget.cget("text")
            if not hasattr(widget, "_native_source_text"):
                widget._native_source_text = str(old)
            if widget._native_source_text:
                widget.configure(text=self.tr(widget._native_source_text))
        except (tk.TclError, AttributeError, KeyError):
            pass
        for child in widget.winfo_children():
            self._translate_ui_tree(child)

    def _translate_menu(self, menu):
        try:
            last = menu.index("end")
        except tk.TclError:
            return
        if last is None:
            return
        if not hasattr(menu, "_native_source_labels"):
            menu._native_source_labels = {}
        for pos in range(last + 1):
            kind = menu.type(pos)
            if kind in ("separator", "tearoff"):
                continue
            if pos not in menu._native_source_labels:
                menu._native_source_labels[pos] = str(menu.entrycget(pos, "label"))
            menu.entryconfigure(pos, label=self.tr(menu._native_source_labels[pos]))
            if kind == "cascade":
                target = menu.entrycget(pos, "menu")
                if target:
                    self._translate_menu(self.nametowidget(target))

    def set_language(self, lang: str):
        if lang not in ("en", "de"):
            return
        self.lang = lang
        self.language_display.set("English" if lang == "en" else "Deutsch")
        self._translate_ui_tree(self)
        try:
            self._translate_menu(self.nametowidget(self.cget("menu")))
        except tk.TclError:
            pass
        source_modes = {
            "intelligent": "Intelligent (empfohlen)",
            "text_only": "Nur Text",
            "image_only": "Nur Bilder",
            "universal": "Alles entfernen",
            "precision": "Nur Vektorgrafik",
        }
        if hasattr(self, "mode_combo"):
            self._mode_labels = {key: self.tr(value) for key, value in source_modes.items()}
            self.mode_combo["values"] = list(self._mode_labels.values())
            self.mode_display.set(self._mode_labels.get(self.removal_mode.get(), self._mode_labels["intelligent"]))
        for name in ("status_var", "preview_status", "selection_info", "page_var", "zoom_var"):
            val = getattr(self, name, None)
            if isinstance(val, LocalizedStringVar):
                val.retranslate()

    def change_language(self, event=None):
        self.set_language("de" if self.language_display.get() == "Deutsch" else "en")
        if self.doc is not None:
            self.render_page()

    def _showinfo(self, title, message, **kwargs):
        return messagebox.showinfo(self.tr(title), self.tr(message), **kwargs)

    def _showwarning(self, title, message, **kwargs):
        return messagebox.showwarning(self.tr(title), self.tr(message), **kwargs)

    def _showerror(self, title, message, **kwargs):
        return messagebox.showerror(self.tr(title), self.tr(message), **kwargs)

    def _askyesno(self, title, message, **kwargs):
        return messagebox.askyesno(self.tr(title), self.tr(message), **kwargs)

    def _set_window_icon(self):
        try:
            icon_file = resource_path("assets", "native_pdf_eraser_small.png")
            if icon_file.exists():
                self._icon_photo = tk.PhotoImage(file=str(icon_file))
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _make_button(self, parent, text: str, command, *, accent=False, width=None):
        """All actions are recognizable buttons, including inactive white controls."""
        return tk.Button(
            parent, text=text, command=command, width=width,
            bg=BLUE if accent else "#FFF7F7",
            fg=WHITE if accent else BLUE,
            activebackground="#0C497D" if accent else "#E7F2FA",
            activeforeground=WHITE if accent else BLUE,
            font=("Segoe UI", 10, "bold" if accent else "normal"),
            relief="solid", borderwidth=1, padx=9, pady=7,
            highlightthickness=0, cursor="hand2", disabledforeground="#A3A3A3",
        )

    def _section(self, parent, title: str) -> None:
        tk.Label(parent, text=title.upper(), font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=WHITE).pack(anchor="w", pady=(17, 9))

    def _build_ui(self):
        menu = tk.Menu(self)
        filemenu = tk.Menu(menu, tearoff=0)
        filemenu.add_command(label="PDF öffnen...", accelerator="Ctrl+O", command=self.open_pdf)
        filemenu.add_command(label="Geprüfte PDF speichern unter...", accelerator="Ctrl+S", command=self.save_as)
        filemenu.add_separator()
        filemenu.add_command(label="Beenden", command=self.on_close)
        menu.add_cascade(label="Datei", menu=filemenu)
        editmenu = tk.Menu(menu, tearoff=0)
        editmenu.add_command(label="Letztes Rechteck rückgängig", accelerator="Ctrl+Z", command=self.undo)
        editmenu.add_command(label="Rechtecke auf Seite löschen", command=self.clear_page)
        editmenu.add_command(label="Alle Rechtecke löschen", command=self.clear_all)
        editmenu.add_separator()
        editmenu.add_command(label="Letzte Entfernung rückgängig", accelerator="Ctrl+Shift+Z", command=self.undo_last_removal)
        editmenu.add_command(label="Zum Anfang / Zurücksetzen", accelerator="Ctrl+R", command=self.reset_to_start)
        menu.add_cascade(label="Bearbeiten", menu=editmenu)
        helpmenu = tk.Menu(menu, tearoff=0)
        helpmenu.add_command(label="Über das Programm und Einschränkungen", command=self.about)
        menu.add_cascade(label="Hilfe", menu=helpmenu)
        self.config(menu=menu)
        self.bind_all("<Control-o>", lambda e: self.open_pdf())
        self.bind_all("<Control-s>", lambda e: self.save_as())
        self.bind_all("<Control-z>", lambda e: self.undo())
        self.bind_all("<Control-r>", lambda e: self.reset_to_start())
        self.bind_all("<Control-Shift-Z>", lambda e: self.undo_last_removal())
        self.bind_all("<Escape>", lambda e: self._cancel_drag())

        header = tk.Frame(self, bg=BLUE, height=66)
        header.pack(fill="x")
        header.pack_propagate(False)
        try:
            self._header_icon = tk.PhotoImage(file=str(resource_path("assets", "native_pdf_eraser_small.png"))).subsample(2, 2)
            tk.Label(header, image=self._header_icon, bg=BLUE).pack(side="left", padx=(20, 6))
        except tk.TclError:
            self._header_icon = None
        tk.Label(header, text="Native PDF Eraser", bg=BLUE, fg=WHITE,
                 font=("Segoe UI", 19, "bold")).pack(side="left", padx=(2, 16))
        tk.Label(header, text="Inhalte präzise entfernen", bg=BLUE, fg="#D5EBFA",
                 font=("Segoe UI", 10)).pack(side="left", padx=16)
        self._make_button(header, "PDF öffnen", self.open_pdf).pack(side="right", padx=(6, 20), pady=13)
        self.reset_btn = self._make_button(header, "↶  Zurücksetzen", self.reset_to_start)
        self.reset_btn.pack(side="right", padx=4, pady=13)

        toolbar = tk.Frame(self, bg=WHITE, height=52)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        b = lambda text, fn: self._make_button(toolbar, text, fn).pack(side="left", padx=3, pady=8)
        tk.Frame(toolbar, bg=WHITE, width=18).pack(side="left")
        b("◀", self.previous_page)
        self.page_var = LocalizedStringVar(self, value="Seite – / –")
        tk.Label(toolbar, textvariable=self.page_var, bg=WHITE, fg=INK,
                 font=("Segoe UI", 10, "bold"), width=13).pack(side="left", padx=2)
        b("▶", self.next_page)
        tk.Frame(toolbar, bg="#DCE4EF", width=1, height=26).pack(side="left", padx=18)
        b("−", lambda: self.adjust_zoom(1 / 1.25))
        self.zoom_var = LocalizedStringVar(self, value="Anpassen")
        tk.Label(toolbar, textvariable=self.zoom_var, bg=WHITE, fg=INK, width=7).pack(side="left")
        b("+", lambda: self.adjust_zoom(1.25))
        b("Seite einpassen", self.fit_page)
        tk.Frame(toolbar, bg="#DCE4EF", width=1, height=26).pack(side="left", padx=18)
        self.select_btn = self._make_button(toolbar, "▧  Bereich markieren", lambda: self.set_mode("select"), accent=True)
        self.select_btn.pack(side="left", padx=3, pady=8)
        self.pan_btn = self._make_button(toolbar, "✥  Verschieben", lambda: self.set_mode("pan"))
        self.pan_btn.pack(side="left", padx=3, pady=8)
        language_group = tk.Frame(toolbar, bg=WHITE)
        language_group.pack(side="right", padx=(5, 18), pady=9)
        tk.Label(language_group, text="Language / Sprache", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        self.language_combo = ttk.Combobox(
            language_group, textvariable=self.language_display,
            state="readonly", values=("English", "Deutsch"), width=9,
            font=("Segoe UI", 10))
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self.change_language)

        footer = tk.Frame(self, bg=WHITE, height=32)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.status_var = LocalizedStringVar(self, value="Bereit")
        tk.Label(footer, textvariable=self.status_var, bg=WHITE, fg=MUTED,
                 anchor="w", font=("Segoe UI", 9)).pack(side="left", padx=22)
        tk.Label(footer, text=f"Native PDF Eraser  ·  v{VERSION}  ·  AGPL-3.0", bg=WHITE,
                 fg=RED, font=("Segoe UI", 9, "bold")).pack(side="right", padx=22)


        content = tk.Frame(self, bg=LIGHT)
        content.pack(fill="both", expand=True)
        center = tk.Frame(content, bg="#E6EDF4")
        center.pack(side="left", fill="both", expand=True, padx=(18, 10), pady=16)
        self.canvas = tk.Canvas(center, bg="#D8E4EF", bd=0, highlightthickness=0,
                                cursor="crosshair")
        vscroll = ttk.Scrollbar(center, orient="vertical", command=self.canvas.yview)
        hscroll = ttk.Scrollbar(center, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        vscroll.pack(side="right", fill="y")
        hscroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.canvas_press)
        self.canvas.bind("<B1-Motion>", self.canvas_move)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
        self.canvas.bind("<Control-MouseWheel>", self.ctrl_wheel)
        self.canvas.bind("<MouseWheel>", self.scroll_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.canvas.bind("<Configure>", self.resize_canvas)
        self.canvas.create_text(350, 230, text="PDF öffnen, um zu starten", fill=INK,
                                font=("Segoe UI", 18, "bold"), tags="empty")

        sidebar = tk.Frame(content, bg=WHITE, width=335)
        sidebar.pack(side="right", fill="y", padx=(0, 18), pady=16)
        sidebar.pack_propagate(False)
        # Sticky action area: processing and saving remain visible even when
        # employees scroll through multiple rectangle selections.
        save_footer = tk.Frame(sidebar, bg=WHITE)
        save_footer.pack(side="bottom", fill="x", padx=18, pady=(5, 10))
        tk.Frame(save_footer, height=1, bg="#D7E4ED").pack(fill="x", pady=(0, 7))
        logo_actions = tk.Frame(save_footer, bg=WHITE)
        logo_actions.pack(fill="x", pady=(0, 8))
        for i, (label, action) in enumerate((
            ("Bildlogo erfassen", self.snap_selected_image),
            ("Seiten abgleichen", self.find_same_logo_pages),
        )):
            logo_actions.grid_columnconfigure(i, weight=1, uniform="logo")
            self._make_button(logo_actions, label, action).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 4 if i == 0 else 0)
            )
        tk.Label(save_footer, text="3 · BEARBEITEN", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.process_btn = self._make_button(
            save_footer, "Inhalt entfernen & prüfen", self.process, accent=True)
        self.process_btn.pack(fill="x")
        self.preview_status = LocalizedStringVar(self, value="Noch keine Vorschau.")
        tk.Label(save_footer, textvariable=self.preview_status, bg=WHITE, fg=MUTED,
                 justify="left", wraplength=280, font=("Segoe UI", 9)).pack(
                     anchor="w", pady=(4, 5))
        previews = tk.Frame(save_footer, bg=WHITE)
        previews.pack(fill="x")
        for i, (label, callback) in enumerate((
            ("Original", lambda: self.switch_preview(False)),
            ("Vorschau", lambda: self.switch_preview(True)),
        )):
            previews.grid_columnconfigure(i, weight=1, uniform="previews")
            self._make_button(previews, label, callback).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 4 if i == 0 else 0)
            )
        tk.Frame(save_footer, height=1, bg="#D7E4ED").pack(fill="x", pady=(9, 7))
        tk.Label(save_footer, text="4 · SPEICHERN", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.save_btn = self._make_button(
            save_footer, "Geprüfte PDF speichern unter...", self.save_as, accent=True)
        self.save_btn.pack(fill="x")
        self.save_btn.config(state="disabled")
        tk.Label(save_footer, text="Original-PDF bleibt erhalten.",
                 bg=WHITE, fg=MUTED, justify="left", wraplength=283,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 0))
        # Scrollable inspector: Save As remains accessible on small laptop screens.
        side_canvas = tk.Canvas(sidebar, bg=WHITE, highlightthickness=0, bd=0)
        side_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=side_canvas.yview)
        side_canvas.configure(yscrollcommand=side_scroll.set)
        side_scroll.pack(side="right", fill="y")
        side_canvas.pack(side="left", fill="both", expand=True)
        panel = tk.Frame(side_canvas, bg=WHITE, padx=18, pady=6)
        panel_window = side_canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda e: side_canvas.configure(scrollregion=side_canvas.bbox("all")))
        side_canvas.bind("<Configure>", lambda e: side_canvas.itemconfigure(panel_window, width=e.width))
        def side_wheel(event):
            side_canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")
            return "break"
        sidebar.bind("<Enter>", lambda e: sidebar.bind_all("<MouseWheel>", side_wheel))
        sidebar.bind("<Leave>", lambda e: sidebar.unbind_all("<MouseWheel>"))
        self._section(panel, "1 · Entfernen")
        tk.Label(panel, text="Rechteck um den gewünschten Inhalt ziehen.",
                 bg=WHITE, fg=INK, justify="left", wraplength=285,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))
        tk.Label(panel, text="Modus", bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(1, 4))
        self._mode_labels = {
            "intelligent": "Intelligent (empfohlen)",
            "text_only": "Nur Text",
            "image_only": "Nur Bilder",
            "universal": "Alles entfernen",
            "precision": "Nur Vektorgrafik",
        }
        self.mode_display = tk.StringVar(value=self._mode_labels[self.removal_mode.get()])
        self.mode_combo = ttk.Combobox(
            panel, textvariable=self.mode_display,
            values=list(self._mode_labels.values()), state="readonly",
            font=("Segoe UI", 10), height=6,
        )
        self.mode_combo.pack(fill="x", pady=(0, 7))
        self.mode_combo.bind("<<ComboboxSelected>>", self._mode_selected)
        self.auto_detect_check = tk.Checkbutton(
            panel, text="Objekte automatisch erkennen", variable=self.auto_detect,
            bg=WHITE, fg=INK, activebackground=WHITE, selectcolor=WHITE,
            font=("Segoe UI", 9), anchor="w",
        )
        self.auto_detect_check.pack(fill="x", pady=(0, 1))
        self.auto_find_check = tk.Checkbutton(
            panel, text="Andere Seiten automatisch prüfen", variable=self.auto_find_pages,
            bg=WHITE, fg=INK, activebackground=WHITE, selectcolor=WHITE,
            font=("Segoe UI", 9), anchor="w",
        )
        self.auto_find_check.pack(fill="x", pady=(1, 0))

        self._section(panel, "2 · Markierungen")
        self.rect_list = tk.Listbox(
            panel, bg="#F6FAFD", fg=INK, selectbackground="#CDE5F5",
            selectforeground=INK, activestyle="none", height=4, bd=0,
            highlightthickness=1, highlightbackground="#BCD7E9",
            font=("Segoe UI", 9),
        )
        self.rect_list.pack(fill="x", pady=(0, 8))
        commands = tk.Frame(panel, bg=WHITE)
        commands.pack(fill="x")
        for i, (text, func) in enumerate((
            ("Entfernen", self.remove_selected_rectangle),
            ("Rückgängig", self.undo),
            ("Alle löschen", self.clear_all),
        )):
            commands.grid_columnconfigure(i, weight=1, uniform="actions")
            self._make_button(commands, text, func).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 3, 3 if i < 2 else 0)
            )
        self.selection_info = LocalizedStringVar(self, value="Noch keine Markierung.")
        tk.Label(panel, textvariable=self.selection_info, bg=WHITE, fg=MUTED,
                 justify="left", wraplength=285, font=("Segoe UI", 9)).pack(
                     anchor="w", pady=(7, 6))


    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.update_idletasks()

    def open_pdf(self, file_path: str | None = None):
        if not file_path:
            file_path = filedialog.askopenfilename(title=self.tr("PDF auswählen"), filetypes=[(self.tr("PDF-Dateien"), "*.pdf"), (self.tr("Alle Dateien"), "*.*")])
        if not file_path:
            return
        try:
            newdoc = pymupdf.open(str(file_path))
            _check_document(newdoc)
        except Exception as exc:
            try:
                newdoc.close()
            except (NameError, Exception):
                pass
            self._showerror("PDF kann nicht geöffnet werden", str(exc), parent=self)
            return
        self._close_docs()
        self._cleanup_workspace()
        self._workspace = TemporaryDirectory(prefix="native_pdf_eraser_session_")
        self.doc = newdoc
        self.source_path = Path(file_path)
        self._history_paths = [self.source_path]
        self._history_results = []
        self._active_input_path = self.source_path
        self.page_idx = 0
        self.selections = {}
        self.undo_stack = []
        self.preview = False
        self.result = None
        self.preview_status.set("Noch keine Vorschau.")
        self.save_btn.config(state="disabled")
        self.zoom_fit = True
        self.title(f"{APP_TITLE}  |  {self.source_path.name}")
        if self._fit_initial_job is not None:
            self.after_cancel(self._fit_initial_job)
        self._fit_initial_job = self.after(100, self.fit_page)
        self.render_page()
        self._set_status(f"Geöffnet: {self.source_path.name}  ·  {self.doc.page_count} Seite(n)")

    def _cleanup_workspace(self):
        if self._workspace is not None:
            self._workspace.cleanup()
            self._workspace = None

    def _accept_processed_preview(self):
        """Promote the last verified PDF to the editable working document."""
        if self.preview_doc is None:
            return
        if self.doc is not None:
            self.doc.close()
        self.doc = self.preview_doc
        self.preview_doc = None
        self.preview = False
        self.render_page()

    def undo_last_removal(self):
        """Restore the previous *verified* stage without touching source PDF."""
        if len(self._history_paths) <= 1 or not self.source_path:
            self._showinfo("Keine frühere Entfernung", "Es gibt keinen bearbeiteten Schritt zum Rückgängigmachen.", parent=self)
            return
        if not self._askyesno("Letzte Entfernung rückgängig?",
                                   "Der letzte geprüfte Entfernungsschritt wird verworfen.", parent=self):
            return
        previous = self._history_paths[-2]
        replacement = pymupdf.open(str(previous))
        self._close_docs()
        self.doc = replacement
        self._history_paths.pop()
        self._history_results.pop()
        self._active_input_path = self._history_paths[-1]
        self.result = self._history_results[-1] if self._history_results else None
        self.preview = False
        self.selections.clear()
        self.undo_stack.clear()
        self.render_page()
        self._refresh_save_state()
        self._set_status("Letzte Entfernung rückgängig gemacht.")

    def _refresh_save_state(self):
        """Never save with new, still-unprocessed rectangles pending."""
        pending = any(self.selections.values())
        self.save_btn.config(state="normal" if self.result is not None and not pending else "disabled")
        if pending:
            self.preview_status.set("Neue Markierung: bitte entfernen & prüfen.")
        elif self.result is not None:
            self.preview_status.set(f"✓ Geprüft · {len(self._history_results)} Entfernungsschritt(e) gespeichert")
        else:
            self.preview_status.set("Noch keine Vorschau.")

    def _close_docs(self):
        for handle in (self.preview_doc, self.doc):
            if handle is not None:
                handle.close()
        self.preview_doc = None
        self.doc = None

    def _invalidate_preview(self):
        # Previously this discarded the user's already completed edits. The
        # verified result now survives selection changes and mode switches.
        self._accept_processed_preview()
        self.preview = False
        self._refresh_save_state()

    def _current_doc(self):
        return self.preview_doc if self.preview and self.preview_doc else self.doc

    def render_page(self):
        self.canvas.delete("all")
        if not self.doc:
            self.canvas.create_text(350, 230, text="PDF öffnen, um zu starten", fill=INK,
                                    font=("Segoe UI", 18, "bold"))
            self.page_var.set("Seite – / –")
            self.rect_list.delete(0, "end")
            return
        page = self._current_doc()[self.page_idx]
        render_zoom = max(0.15, min(self.zoom, 5.0))
        # Prevent accidental huge allocations at very high magnification.
        max_side = max(page.rect.width, page.rect.height)
        if max_side * render_zoom > 6500:
            render_zoom = 6500 / max_side
        self.zoom = render_zoom
        try:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(self.zoom, self.zoom),
                                  colorspace=pymupdf.csRGB, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            self._photo = ImageTk.PhotoImage(image)
        except Exception as exc:
            self._showerror("Seite konnte nicht angezeigt werden", str(exc), parent=self)
            return
        self.image_id = self.canvas.create_image(PAD, PAD, anchor="nw", image=self._photo,
                                                  tags="page-image")
        self._page_width_px = pix.width
        self._page_height_px = pix.height
        self.canvas.configure(scrollregion=(0, 0, pix.width + PAD * 2, pix.height + PAD * 2))
        self.page_var.set(f"Seite {self.page_idx + 1} / {self.doc.page_count}")
        self.zoom_var.set(f"{int(self.zoom * 100)}%")
        if not self.preview:
            for i, rect in enumerate(self.selections.get(self.page_idx, [])):
                coords = self._rect_to_canvas(rect)
                self.canvas.create_rectangle(*coords, outline=RED, fill="#C5E7F6",
                                             stipple="gray25", width=2, tags=("selection",))
                self.canvas.create_text(coords[0] + 5, coords[1] + 5, anchor="nw",
                                        text=f"{i+1}", fill=RED, font=("Segoe UI", 10, "bold"),
                                        tags="selection")
        self._update_rect_list()

    def resize_canvas(self, event):
        if self.doc is not None and self.zoom_fit and getattr(self, "_fit_resize_job", None) is None:
            self._fit_resize_job = self.after(130, self._finish_fit_resize)

    def _finish_fit_resize(self):
        self._fit_resize_job = None
        if self.doc and self.zoom_fit:
            self.fit_page()

    def _rect_to_canvas(self, rect: pymupdf.Rect):
        return (PAD + rect.x0*self.zoom, PAD + rect.y0*self.zoom,
                PAD + rect.x1*self.zoom, PAD + rect.y1*self.zoom)

    def _canvas_to_pdf(self, event):
        if not self.doc:
            return None
        x = (self.canvas.canvasx(event.x) - PAD) / self.zoom
        y = (self.canvas.canvasy(event.y) - PAD) / self.zoom
        rect = self.doc[self.page_idx].rect
        if not (0 <= x <= rect.width and 0 <= y <= rect.height):
            return None
        return (x, y)

    def canvas_press(self, event):
        if not self.doc:
            return
        if self.mode == "pan":
            self.canvas.scan_mark(event.x, event.y)
            self._pan_active = True
            return
        # Selecting a new area after processing continues on the VERIFIED PDF.
        # The previously removed items do not reappear.
        if self.preview_doc is not None:
            self._accept_processed_preview()
        self._start_pdf = self._canvas_to_pdf(event)
        if self._start_pdf:
            x = self.canvas.canvasx(event.x)
            y = self.canvas.canvasy(event.y)
            self._pending_item = self.canvas.create_rectangle(x, y, x, y,
                                outline=RED, fill="#C5E7F6", stipple="gray25", width=2)

    def canvas_move(self, event):
        if self._pan_active:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            return
        if self._pending_item is None or self._start_pdf is None:
            return
        end = self._canvas_to_pdf(event)
        if end is None:
            px = min(max((self.canvas.canvasx(event.x) - PAD) / self.zoom, 0), self.doc[self.page_idx].rect.width)
            py = min(max((self.canvas.canvasy(event.y) - PAD) / self.zoom, 0), self.doc[self.page_idx].rect.height)
            end = (px, py)
        a, b = self._start_pdf, end
        self.canvas.coords(self._pending_item,
                           PAD + a[0] * self.zoom, PAD + a[1] * self.zoom,
                           PAD + b[0] * self.zoom, PAD + b[1] * self.zoom)

    def canvas_release(self, event):
        if self._pan_active:
            self._pan_active = False
            return
        if self._start_pdf is None:
            return
        end = self._canvas_to_pdf(event)
        if end is None:
            end = (min(max((self.canvas.canvasx(event.x) - PAD)/self.zoom, 0), self.doc[self.page_idx].rect.width),
                   min(max((self.canvas.canvasy(event.y) - PAD)/self.zoom, 0), self.doc[self.page_idx].rect.height))
        start = self._start_pdf
        self._cancel_drag()
        rect = pymupdf.Rect(min(start[0], end[0]), min(start[1], end[1]),
                            max(start[0], end[0]), max(start[1], end[1]))
        if rect.width < 2 or rect.height < 2:
            self.render_page()
            return
        recognized = detect_object(self.doc[self.page_idx], rect, self.removal_mode.get()) if self.auto_detect.get() else None
        actual = recognized.rect if recognized is not None else rect
        self.selections.setdefault(self.page_idx, []).append(actual)
        self.undo_stack.append((self.page_idx, actual))
        self._invalidate_preview()
        self.render_page()
        stats = inspect_selection(self.doc[self.page_idx], actual)
        names = {"image": "Bildlogo", "image+text": "Bild und Text", "vector": "Vektorgrafik", "text": "Text"}
        detected = self.tr(names.get(recognized.kind, "Manueller Bereich") if recognized is not None else "Manueller Bereich")
        self._set_status(f"{detected} markiert. {stats.eligible_vectors} Vektorpfade, "
                         f"{stats.overlapping_text} Textwörter, {stats.overlapping_images} Bild(er).")
        if self.auto_find_pages.get() and self.doc.page_count > 1:
            self._offer_page_matches(self.page_idx, len(self.selections[self.page_idx])-1, automatic=True)

    def _cancel_drag(self):
        if self._pending_item is not None:
            self.canvas.delete(self._pending_item)
        self._pending_item = None
        self._start_pdf = None
        self._pan_active = False

    def _update_rect_list(self):
        self.rect_list.delete(0, "end")
        rects = self.selections.get(self.page_idx, [])
        for i, rect in enumerate(rects):
            self.rect_list.insert("end", f"{i+1}.  {rect.width:.0f} × {rect.height:.0f} pt   ·   x={rect.x0:.0f}, y={rect.y0:.0f}")
        total = sum(len(vals) for vals in self.selections.values())
        if not self.doc or not rects:
            self.selection_info.set(f"{total} markierte Bereiche" if total else "Noch keine Markierung.")
            return
        inspections = [inspect_selection(self.doc[self.page_idx], r) for r in rects]
        txt = sum(s.overlapping_text for s in inspections)
        imgs = sum(s.overlapping_images for s in inspections)
        self.selection_info.set(f"{total} Bereiche gesamt   ·   Text: {txt}   ·   Bilder: {imgs}")

    def _selected_rectangle_position(self):
        current = self.selections.get(self.page_idx, [])
        if not current:
            self._showinfo("Keine Auswahl", "Bitte zuerst über dem Logo ein Rechteck ziehen.", parent=self)
            return None
        chosen = self.rect_list.curselection()
        if len(current) > 1 and not chosen:
            self._showinfo("Rechteck wählen", "Bitte einen Eintrag in der Liste auswählen.", parent=self)
            return None
        return chosen[0] if chosen else 0

    def snap_selected_image(self):
        """Replace a rough logo box with exact PDF image-object bounds."""
        if not self.doc or self.preview:
            return
        pos = self._selected_rectangle_position()
        if pos is None:
            return
        page = self.doc[self.page_idx]
        rect = self.selections[self.page_idx][pos]
        hits = image_candidates(page, rect)
        if not hits:
            self._showwarning(
                "Kein eindeutig erfasstes Bildlogo",
                "Innerhalb des Rechtecks wurde kein ausreichend markiertes Bildlogo erkannt. "
                "Bitte das Logo zu mindestens etwa 55 % überdecken. "
                "Falls es aus Vektoren oder PDF-Text besteht, einen anderen Entfernungsmodus verwenden.",
                parent=self,
            )
            return
        if len(hits) > 1:
            if not self._askyesno(
                "Mehrere Bilder gefunden",
                f"Es wurden {len(hits)} Bildobjekte erkannt. Alle Bildgrenzen erfassen?",
                parent=self,
            ):
                return
        precise = bbox_to_display(page, hits[0])
        for im in hits[1:]:
            precise |= bbox_to_display(page, im)
        self._invalidate_preview()
        self.selections[self.page_idx][pos] = precise
        self.undo_stack.clear()
        self.render_page()
        self._set_status(f"Markierung auf die exakte Bildgrenze angepasst ({len(hits)} Bildobjekt(e)).")

    def _pick_page_matches(self, matches, automatic: bool):
        """Review matches in a modal with independently selectable page checkboxes.

        None means cancel / don't add. No page is selected without an explicit
        click on the confirmation button.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Gleiche Elemente auf weiteren Seiten")
        dialog.transient(self)
        dialog.configure(bg=WHITE)
        dialog.resizable(False, True)
        self.update_idletasks()
        popup_w, popup_h = 520, 500
        popup_x = max(0, self.winfo_rootx() + (self.winfo_width() - popup_w)//2)
        popup_y = max(0, self.winfo_rooty() + (self.winfo_height() - popup_h)//2)
        dialog.geometry(f"{popup_w}x{popup_h}+{popup_x}+{popup_y}")
        dialog.minsize(480, 440)
        dialog.grab_set()
        tk.Label(dialog, text=self.tr(f"{len(matches)} mögliche Übereinstimmung(en)"), bg=WHITE,
                 fg=INK, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=18, pady=(16, 5))
        tk.Label(dialog, text="Nur bestätigte Seiten werden markiert. Bitte die Treffer prüfen.",
                 bg=WHITE, fg=MUTED, font=("Segoe UI", 9), wraplength=440,
                 justify="left").pack(anchor="w", padx=18, pady=(0, 10))
        frame = tk.Frame(dialog, bg=WHITE)
        frame.pack(fill="both", expand=True, padx=18)
        canvas = tk.Canvas(frame, bg="#F6FAFD", highlightthickness=1,
                           highlightbackground="#BCD7E9")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg="#F6FAFD")
        inner_id = canvas.create_window((0,0),window=inner,anchor="nw")
        inner.bind("<Configure>",lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e: canvas.itemconfigure(inner_id,width=e.width))
        choices=[]
        for match in matches:
            var = tk.BooleanVar(value=True)
            label = self.tr(f"Seite {match.page_index+1}   ·   {match.reason}")
            tk.Checkbutton(inner, text=label, variable=var, bg="#F6FAFD", fg=INK,
                           selectcolor="#FFF8F8", activebackground="#FFF8F8",
                           font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=9, pady=5)
            choices.append(var)
        allrow=tk.Frame(dialog, bg=WHITE)
        allrow.pack(fill="x", padx=18, pady=(7, 5))
        self._make_button(allrow,"Alle wählen",lambda: [v.set(True) for v in choices]).pack(side="left")
        self._make_button(allrow,"Keine wählen",lambda: [v.set(False) for v in choices]).pack(side="left",padx=6)
        result=[None]
        def finish(confirm):
            result[0]=[m for m,v in zip(matches,choices) if v.get()] if confirm else []
            dialog.destroy()
        actions=tk.Frame(dialog,bg=WHITE)
        actions.pack(fill="x", padx=18, pady=(4, 16))
        self._make_button(actions,"Nur diese Seite",lambda: finish(False)).pack(side="left")
        self._make_button(actions,"Auswahl übernehmen",lambda: finish(True),accent=True).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW",lambda: finish(False))
        self._translate_ui_tree(dialog)
        self.wait_window(dialog)
        return result[0] or []

    def _offer_page_matches(self, page_index: int, position: int, *, automatic: bool):
        if not self.doc or self.preview:
            return
        values = self.selections.get(page_index, [])
        if position >= len(values):
            return
        selection = pymupdf.Rect(values[position])
        try:
            matches = discover_repeated_elements(
                self.doc, page_index, selection, removal_mode=self.removal_mode.get())
        except Exception as exc:
            if not automatic:
                self._showwarning("Seitensuche nicht möglich",str(exc),parent=self)
            return
        fresh=[]
        for hit in matches:
            existing=self.selections.get(hit.page_index,[])
            if not any(old.intersects(hit.rect) and
                       ((old & hit.rect).get_area() / max(hit.rect.get_area(), 1)) > 0.90
                       for old in existing):
                fresh.append(hit)
        if not fresh:
            if not automatic:
                self._showinfo("Keine weiteren Treffer",
                    "Keine identischen Inhalte an derselben Position auf anderen Seiten gefunden.",parent=self)
            return
        accepted = self._pick_page_matches(fresh, automatic)
        if not accepted:
            self._set_status("Weitere Seiten nicht markiert; aktuelle Auswahl bleibt erhalten.")
            return
        self._invalidate_preview()
        for hit in accepted:
            rect=pymupdf.Rect(hit.rect)
            self.selections.setdefault(hit.page_index,[]).append(rect)
            self.undo_stack.append((hit.page_index, rect))
        self.render_page()
        pages=", ".join(str(m.page_index+1) for m in accepted)
        self._set_status(f"{len(accepted)} bestätigte Übereinstimmung(en) markiert: Seite(n) {pages}.")

    def find_same_logo_pages(self):
        """Manual re-scan; auto-scan normally runs after drawing a rectangle."""
        if not self.doc or self.preview:
            return
        pos=self._selected_rectangle_position()
        if pos is not None:
            self._offer_page_matches(self.page_idx, pos, automatic=False)

    def _mode_selected(self, event=None):
        selected = self.mode_display.get()
        for internal, label in self._mode_labels.items():
            if selected == label:
                self.removal_mode.set(internal)
                break
        self.on_removal_mode_change()

    def reset_to_start(self):
        """Return to the pristine source, discarding all editing stages."""
        if not self.source_path:
            return
        if self.result or any(self.selections.values()):
            if not self._askyesno(
                "Bearbeitung zurücksetzen?",
                "ALLE bisher vorgenommenen Entfernungen und Markierungen verwerfen?\n"
                "Die Original-PDF bleibt unverändert.", parent=self,
            ):
                return
        fresh = pymupdf.open(str(self.source_path))
        self._cancel_drag()
        self._close_docs()
        self._cleanup_workspace()
        self._workspace = TemporaryDirectory(prefix="native_pdf_eraser_session_")
        self.doc = fresh
        self._history_paths = [self.source_path]
        self._history_results = []
        self._active_input_path = self.source_path
        self.result = None
        self.selections.clear()
        self.undo_stack.clear()
        self.page_idx = 0
        self.preview = False
        self.removal_mode.set("intelligent")
        self.mode_display.set(self._mode_labels["intelligent"])
        self.set_mode("select")
        self.fit_page()
        self._refresh_save_state()
        self._set_status("Zurückgesetzt. Original geöffnet.")

    def on_removal_mode_change(self):
        if hasattr(self, "mode_display"):
            self.mode_display.set(self._mode_labels.get(self.removal_mode.get(), "Intelligent (empfohlen)"))
        self._invalidate_preview()
        if self.doc is not None:
            self.render_page()
        which = {
            "intelligent": "Automatik: Bildlogos an Objektgrenzen erkennen; sonst Text oder Vektorgrafik entfernen.",
            "text_only": "Nur PDF-Text wird entfernt; Tabellen, Linien und Bilder bleiben bestehen.",
            "image_only": "Bildobjekte werden anhand ihrer tatsächlichen Grenzen entfernt.",
            "universal": "Alle unterstützten Inhalte werden entfernt.",
            "precision": "Nur vollständig eingeschlossene Vektoren werden entfernt.",
        }.get(self.removal_mode.get(), "Entfernungsmodus gewählt.")
        self._set_status(which)

    def remove_selected_rectangle(self):
        if self.preview or not self.doc:
            return
        selected = self.rect_list.curselection()
        if not selected:
            return
        rects = self.selections.get(self.page_idx, [])
        if selected[0] < len(rects):
            rects.pop(selected[0])
            self.undo_stack.clear()
            self._invalidate_preview()
            self.render_page()
            self._refresh_save_state()

    def undo(self):
        if not self.doc or self.preview or not self.undo_stack:
            return
        page, rect = self.undo_stack.pop()
        rects = self.selections.get(page, [])
        for pos in range(len(rects)-1, -1, -1):
            if rects[pos] == rect:
                rects.pop(pos)
                break
        self._invalidate_preview()
        self.page_idx = page
        self.render_page()
        self._refresh_save_state()

    def clear_page(self):
        if not self.doc or self.preview:
            return
        self.selections.pop(self.page_idx, None)
        self.undo_stack.clear()
        self._invalidate_preview()
        self.render_page()
        self._refresh_save_state()

    def clear_all(self):
        if not self.doc or self.preview:
            return
        self.selections.clear()
        self.undo_stack.clear()
        self._invalidate_preview()
        self.render_page()
        self._refresh_save_state()

    def set_mode(self, mode: str):
        self.mode = mode
        self.select_btn.config(bg=BLUE if mode == "select" else WHITE,
                               fg=WHITE if mode == "select" else INK)
        self.pan_btn.config(bg=BLUE if mode == "pan" else WHITE,
                            fg=WHITE if mode == "pan" else INK)
        self.canvas.config(cursor="crosshair" if mode == "select" else "fleur")

    def _switch_page(self, index):
        if not self.doc or not (0 <= index < self.doc.page_count):
            return
        self.page_idx = index
        if self.zoom_fit:
            self.fit_page()
        else:
            self.render_page()

    def previous_page(self): self._switch_page(self.page_idx - 1)
    def next_page(self): self._switch_page(self.page_idx + 1)

    def adjust_zoom(self, factor):
        if not self.doc: return
        self.zoom_fit = False
        self.zoom = min(5.0, max(0.15, self.zoom * factor))
        self.render_page()

    def fit_page(self):
        if not self.doc: return
        page = self.doc[self.page_idx]
        w = max(100, self.canvas.winfo_width() - (2 * PAD + 28))
        h = max(100, self.canvas.winfo_height() - (2 * PAD + 28))
        self.zoom = min(w/page.rect.width, h/page.rect.height, 3.0)
        self.zoom_fit = True
        self.render_page()

    def ctrl_wheel(self, event):
        self.adjust_zoom(1.25 if event.delta > 0 else 1/1.25)
        return "break"

    def scroll_wheel(self, event):
        self.canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")
        return "break"

    def switch_preview(self, cleaned: bool):
        if not self.doc:
            return
        if cleaned and self.preview_doc is None:
            self._showinfo("Keine bereinigte Vorschau", "Bitte zuerst auf 'Inhalt entfernen & prüfen' klicken.", parent=self)
            return
        self.preview = cleaned
        self.render_page()
        self._set_status("Bereinigte PDF wird angezeigt" if cleaned else "Original-PDF wird angezeigt")

    def process(self):
        if not self.doc or not self._active_input_path:
            self._showinfo("PDF öffnen", "Bitte zuerst eine PDF öffnen und einen Bereich markieren.", parent=self)
            return
        if not any(self.selections.values()):
            self._showinfo("Keine Markierung", "Bitte zuerst ein Rechteck über dem Logo zeichnen.", parent=self)
            return
        if self.preview_doc is not None:
            # Handles programmatic selection updates as well as mouse drawing:
            # always inspect the latest verified document.
            self._accept_processed_preview()
        mode = self.removal_mode.get()
        # Detect images independently per selection: a text rectangle on the
        # same page must not prevent precise image snapping.
        if mode in ("intelligent", "image_only"):
            expanded_pages = []
            proposed = {idx:[pymupdf.Rect(v) for v in values]
                        for idx, values in self.selections.items()}
            for idx, values in self.selections.items():
                page = self.doc[idx]
                for i, original_rect in enumerate(values):
                    hits = image_candidates(page, original_rect)
                    if not hits:
                        continue
                    image_rect = bbox_to_display(page, hits[0])
                    for item in hits[1:]:
                        image_rect |= bbox_to_display(page, item)
                    # Preserve the full user selection when it also contains
                    # text, so image snapping cannot accidentally omit it.
                    text_present = _character_centers(page, _page_coords(page, pymupdf.Rect(original_rect)))
                    target = (image_rect | pymupdf.Rect(original_rect)) if text_present else image_rect
                    if not pymupdf.Rect(original_rect).contains(target):
                        expanded_pages.append(idx + 1)
                    proposed[idx][i] = target
            if expanded_pages:
                pages = ", ".join(str(n) for n in sorted(set(expanded_pages)))
                if not self._askyesno(
                    "Bildbereich erweitern?",
                    f"Bildgrenzen auf Seite(n) {pages} vollständig übernehmen?\n"
                    "Der gesamte Bildinhalt wird entfernt.", parent=self,
                ):
                    self._set_status("Abgebrochen. Markierungen unverändert.")
                    return
            if proposed != self.selections:
                self._invalidate_preview()
                self.selections = proposed
                self.undo_stack.clear()
                self.render_page()
        self.process_btn.config(state="disabled")
        previous_result = self.result
        try:
            # The active input is the last VERIFIED state, not the original.
            self._set_status("Entfernen und prüfen...")
            mode = self.removal_mode.get()
            if mode == "intelligent":
                self.result = process_pdf_smart_mixed(self._active_input_path, self.selections, progress=self._set_status)
            elif mode == "text_only":
                self.result = process_pdf_text_only(self._active_input_path, self.selections, progress=self._set_status)
            elif mode == "image_only":
                self.result = process_pdf_image_only(self._active_input_path, self.selections, progress=self._set_status)
            elif mode == "universal":
                self.result = process_pdf_universal(self._active_input_path, self.selections, progress=self._set_status)
            else:
                self.result = process_pdf(self._active_input_path, self.selections, progress=self._set_status)
            self.preview_doc = pymupdf.open(stream=self.result.pdf_bytes, filetype="pdf")
            assert self._workspace is not None
            stage = Path(self._workspace.name) / f"stand_{len(self._history_paths):03d}.pdf"
            stage.write_bytes(self.result.pdf_bytes)
            self._history_paths.append(stage)
            self._history_results.append(self.result)
            self._active_input_path = stage
            self.preview = True
            # One completed selection batch = one step. The next rectangle
            # starts a new stage; the completed changes remain in the PDF.
            self.selections.clear()
            self.undo_stack.clear()
            method_label = {
                "surgical": "Direkte Vektorentfernung", "native": "Native Vektorentfernung",
                "universal": "Universelle PDF-Inhaltsentfernung",
                "text_only": "Nur Text (Tabellen geschützt)",
                "image_only": "Bildobjekte direkt entfernt (Tabellen geschützt)",
                "intelligent_text": "Intelligent: Text bevorzugt",
                "smart_mixed": "Intelligent: Text und Bilder kombiniert",
            }.get(self.result.method, self.result.method)
            self.preview_status.set(
                f"✓ Schritt {len(self._history_results)} · {self.result.removed_text_chars} Zeichen · "
                f"{self.result.modified_images} Bilder · "
                f"{self.result.removed_vectors} Vektoren"
            )
            self.save_btn.config(state="normal")
            self.render_page()
            self._set_status("GEPRÜFT. Sie können sofort den nächsten Bereich markieren oder speichern.")
        except (EditError, VerificationError) as exc:
            self.result = previous_result
            self._set_status("Keine Ausgabe erzeugt — Auswahl oder Prüfung fehlgeschlagen.")
            self.preview_status.set("Prüfung nicht bestanden. Es wurde keine Ausgabe gespeichert.")
            self._showwarning("Entfernung konnte nicht verifiziert werden", str(exc), parent=self)
        except Exception as exc:
            self.result = previous_result
            self._set_status("Verarbeitung fehlgeschlagen. Es wurde keine Ausgabe gespeichert.")
            self._showerror("Verarbeitungsfehler", f"Das Dokument wurde nicht gespeichert.\n\n{exc}", parent=self)
        finally:
            self.process_btn.config(state="normal")

    def save_as(self):
        if any(self.selections.values()):
            self._showwarning(
                "Ungeprüfte Markierungen",
                "Bitte die neuen Markierungen zuerst mit 'Inhalt entfernen & prüfen' bearbeiten "
                "oder die Markierungen löschen, bevor Sie speichern.", parent=self,
            )
            return
        if not self.result or not self.source_path:
            self._showinfo("Nichts zu speichern", "Bitte zuerst entfernen und prüfen.", parent=self)
            return
        destination = filedialog.asksaveasfilename(
            title=self.tr("Geprüfte PDF speichern unter"), defaultextension=".pdf",
            initialfile=self.source_path.stem + "_bereinigt.pdf",
            initialdir=str(self.source_path.parent), filetypes=[(self.tr("PDF-Dateien"), "*.pdf")]
        )
        if not destination:
            return
        target = Path(destination)
        try:
            if target.resolve() == self.source_path.resolve():
                raise ValueError("Bitte einen NEUEN Dateinamen wählen: Die Original-PDF muss unverändert bleiben.")
            target.write_bytes(self.result.pdf_bytes)
            # Read-back verification of exactly the generated bytes.
            if target.read_bytes() != self.result.pdf_bytes:
                raise OSError("Die gespeicherte PDF stimmt nicht mit den verifizierten Daten überein.")
        except Exception as exc:
            self._showerror("Speichern fehlgeschlagen", str(exc), parent=self)
            return
        self._set_status(f"Geprüfte Kopie gespeichert: {target}")
        self._showinfo("PDF gespeichert", f"Gespeichert:\n{target}\n\nDie Original-PDF bleibt unverändert.", parent=self)

    def about(self):
        de = (
            "Native PDF Eraser entfernt markierte PDF-Inhalte direkt aus dem Dokument.\n\n"
            "Unterstützt PDF-Text, eingebettete Bilder und Vektorgrafiken. "
            "Wiederholte Elemente auf anderen Seiten werden zur Bestätigung vorgeschlagen.\n\n"
            "Jede Änderung wird geprüft; das Original bleibt unverändert. "
            "Bearbeitungen, bei denen sich andere Inhalte verändern könnten, werden abgelehnt.\n\n"
            "Hinweis: Nicht jede PDF-Struktur wird unterstützt. Versteckte Inhalte, "
            "Anhänge und Metadaten müssen vor der Weitergabe gesondert geprüft werden.\n\n"
            "Quellcode und Lizenzhinweise: README.md / LICENSING.md (AGPL-3.0)."
        )
        en = (
            "Native PDF Eraser removes selected PDF content directly from the document.\n\n"
            "Supports native text, embedded images and vector graphics. "
            "Repeated elements on other pages are suggested for review.\n\n"
            "Every edit is verified; the original stays untouched. Edits that risk "
            "changing other content are rejected.\n\n"
            "Important: Not every PDF structure is supported. Hidden content, "
            "attachments and metadata must be checked separately before sharing.\n\n"
            "Source and licensing: README.md / LICENSING.md (AGPL-3.0)."
        )
        messagebox.showinfo(f"{APP_TITLE} {VERSION}", en if self.lang == "en" else de, parent=self)

    def on_close(self):
        # Cancel scheduled widget callbacks before Tk destroys their commands.
        for job in (getattr(self, '_startup_job', None),
                    getattr(self, '_fit_initial_job', None),
                    getattr(self, '_fit_resize_job', None)):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self._close_docs()
        self._cleanup_workspace()
        self.destroy()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    app = App(path)
    app.mainloop()


if __name__ == "__main__":
    main()
