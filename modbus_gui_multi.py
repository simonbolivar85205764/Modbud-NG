#!/usr/bin/env python3
"""
Modbus Multi-Session GUI Client — Industrial Control System Interface
Cross-platform (Windows & Linux) — requires: pip install pymodbus

Supports unlimited simultaneous connections to different ICS endpoints,
each with independent polling, logging, and read/write state.
"""

import sys
import threading
import queue
import uuid
import collections
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List

import os
import subprocess

PYMODBUS_AVAILABLE = False
PYMODBUS_IMPORT_ERROR = ""
_PYMODBUS_VERSION = ""

def _try_import_pymodbus():
    """
    Try to import pymodbus. If it fails, attempt to locate it via pip
    and inject its site-packages path into sys.path (Windows multi-Python fix).
    Returns True on success.
    """
    global PYMODBUS_AVAILABLE, PYMODBUS_IMPORT_ERROR, _PYMODBUS_VERSION
    try:
        from pymodbus.client import ModbusTcpClient, ModbusSerialClient  # noqa: F401
        from pymodbus.exceptions import ModbusException                   # noqa: F401
        import pymodbus
        _PYMODBUS_VERSION = getattr(pymodbus, "__version__", "unknown")
        PYMODBUS_AVAILABLE = True
        return True
    except ImportError as first_err:
        PYMODBUS_IMPORT_ERROR = str(first_err)

    # ── Fallback: ask pip where pymodbus lives and add that path ──────────────
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "pymodbus"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if line.lower().startswith("location:"):
                site_path = line.split(":", 1)[1].strip()
                # Security: reject paths with traversal sequences or non-directory entries
                site_path = os.path.normpath(site_path)
                if not os.path.isdir(site_path):
                    PYMODBUS_IMPORT_ERROR = f"pip reported invalid location: {site_path!r}"
                    break
                if site_path not in sys.path:
                    sys.path.insert(0, site_path)
                try:
                    from pymodbus.client import ModbusTcpClient, ModbusSerialClient  # noqa: F401
                    from pymodbus.exceptions import ModbusException                   # noqa: F401
                    import pymodbus
                    _PYMODBUS_VERSION = getattr(pymodbus, "__version__", "unknown")
                    PYMODBUS_AVAILABLE = True
                    PYMODBUS_IMPORT_ERROR = ""
                    return True
                except ImportError as second_err:
                    PYMODBUS_IMPORT_ERROR = str(second_err)
    except Exception as probe_err:
        PYMODBUS_IMPORT_ERROR = f"{first_err} | pip probe failed: {probe_err}"

    return False

_try_import_pymodbus()

# Re-import at module level so the rest of the code can use them normally
if PYMODBUS_AVAILABLE:
    from pymodbus.client import ModbusTcpClient, ModbusSerialClient
    from pymodbus.exceptions import ModbusException
else:
    # Stub classes so the rest of the file parses without errors
    class ModbusTcpClient:    pass   # noqa: E701
    class ModbusSerialClient: pass   # noqa: E701
    class ModbusException(Exception): pass  # noqa: E701

# ─── Palette ───────────────────────────────────────────────────────────────────
BG_DEEP     = "#0b0e0d"
BG_SIDEBAR  = "#0f1412"
BG_PANEL    = "#131816"
BG_CARD     = "#191e1c"
BG_INPUT    = "#0e1210"
BG_ROW_ALT  = "#161b19"
BG_SEL      = "#1e2a27"
BG_SEL_BD   = "#2a3f38"

AMBER       = "#e8a020"
AMBER_DIM   = "#6b4a0e"
AMBER_GLOW  = "#ffb830"
AMBER_PALE  = "#a07018"
GREEN_OK    = "#3ddc84"
GREEN_DIM   = "#1a5c38"
RED_ERR     = "#ff5555"
RED_DIM     = "#5c1a1a"
BLUE_INFO   = "#5ba3f5"
YELLOW_WARN = "#f0c040"
GRAY_MID    = "#4a5550"
GRAY_DIM    = "#232b28"
GRAY_BORDER = "#1e2824"
TEXT_MAIN   = "#cdd5d0"
TEXT_DIM    = "#5e706a"
TEXT_HEAD   = "#e0d8cc"

WIN = sys.platform == "win32"
FONT_MONO    = ("Courier New", 10)      if WIN else ("DejaVu Sans Mono", 10)
FONT_MONO_SM = ("Courier New", 9)       if WIN else ("DejaVu Sans Mono", 9)
FONT_MONO_XS = ("Courier New", 8)       if WIN else ("DejaVu Sans Mono", 8)
FONT_UI      = ("Segoe UI", 10)         if WIN else ("Sans", 10)
FONT_UI_B    = ("Segoe UI", 10, "bold") if WIN else ("Sans", 10, "bold")
FONT_LABEL   = ("Segoe UI", 9)          if WIN else ("Sans", 9)
FONT_LABEL_B = ("Segoe UI", 9, "bold")  if WIN else ("Sans", 9, "bold")
FONT_HEAD    = ("Segoe UI", 12, "bold") if WIN else ("Sans", 12, "bold")
FONT_MONO_LG = ("Courier New", 12)      if WIN else ("DejaVu Sans Mono", 12)

# Connection states
ST_DISCONNECTED = "disconnected"
ST_CONNECTING   = "connecting"
ST_CONNECTED    = "connected"
ST_ERROR        = "error"

STATE_COLOR = {
    ST_DISCONNECTED: TEXT_DIM,
    ST_CONNECTING:   YELLOW_WARN,
    ST_CONNECTED:    GREEN_OK,
    ST_ERROR:        RED_ERR,
}
STATE_DOT = {
    ST_DISCONNECTED: "○",
    ST_CONNECTING:   "◌",
    ST_CONNECTED:    "●",
    ST_ERROR:        "●",
}


# ─── Connection Session Data Model ─────────────────────────────────────────────
@dataclass
class ConnectionSession:
    sid: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = "New Connection"

    # Config
    mode: str = "TCP"            # "TCP" or "RTU"
    host: str = "192.168.1.1"
    port: int = 502
    timeout: int = 5
    serial_port: str = "COM1" if WIN else "/dev/ttyUSB0"
    baudrate: int = 9600
    parity: str = "N"
    stopbits: int = 1
    bytesize: int = 8
    default_unit: int = 1

    # State
    state: str = ST_DISCONNECTED
    client: object = None
    error_msg: str = ""

    # Per-connection read/write last-used values
    read_type: str = "Holding Registers"
    read_addr: int = 0
    read_count: int = 10
    read_unit: int = 1
    write_type: str = "Holding Register"
    write_addr: int = 0
    write_unit: int = 1
    write_value: str = "0"
    confirm_write: bool = True

    # Read polling
    polling: bool = False
    poll_interval: float = 1.0
    poll_stop: threading.Event = field(default_factory=threading.Event)
    poll_thread: Optional[threading.Thread] = None
    last_poll_ts: str = ""

    # Continuous write
    write_polling: bool = False
    write_poll_interval: float = 1.0
    write_poll_stop: threading.Event = field(default_factory=threading.Event)
    write_poll_thread: Optional[threading.Thread] = None
    last_write_poll_ts: str = ""

    # Register labels: key = "RegisterType:address" e.g. "Holding Registers:100"
    reg_labels: Dict[str, str] = field(default_factory=dict)

    # Per-connection log — deque for O(1) bounded append
    log_entries: object = field(default_factory=lambda: collections.deque(maxlen=500))

    def endpoint_str(self) -> str:
        if self.mode == "TCP":
            return f"{self.host}:{self.port}"
        return f"{self.serial_port}@{self.baudrate}"

    def status_color(self) -> str:
        return STATE_COLOR[self.state]

    def status_dot(self) -> str:
        return STATE_DOT[self.state]


# ─── Main Application ──────────────────────────────────────────────────────────
class ModbusMultiClient:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Modbus Multi-Session Client")
        self.root.configure(bg=BG_DEEP)
        self.root.minsize(1100, 700)
        self.root.geometry("1280x820")

        self.sessions: Dict[str, ConnectionSession] = {}
        self.session_order: List[str] = []
        self.active_sid: Optional[str] = None

        # UI widget refs for the active session's op panel
        self._op_widgets = {}
        self._sidebar_rows: Dict[str, dict] = {}

        self._global_log_queue = queue.Queue()

        self._setup_styles()
        self._build_ui()
        self._pump_queues()

        if not PYMODBUS_AVAILABLE:
            py = sys.executable
            self._global_log("━━━ pymodbus NOT FOUND ━━━", "error")
            self._global_log(f"Python running: {py}", "warn")
            self._global_log("Fix: run the following command in a terminal:", "warn")
            self._global_log(f'  "{py}" -m pip install pymodbus', "info")
            self._global_log("Then restart this application.", "warn")
            if PYMODBUS_IMPORT_ERROR:
                self._global_log(f"Import error detail: {PYMODBUS_IMPORT_ERROR}", "error")
        else:
            self._global_log(f"pymodbus {_PYMODBUS_VERSION} ready  |  Python: {sys.executable}", "ok")

    # ─── Styles ────────────────────────────────────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")

        s.configure(".", background=BG_PANEL, foreground=TEXT_MAIN,
                    fieldbackground=BG_INPUT, font=FONT_UI,
                    bordercolor=GRAY_DIM, relief="flat")

        for name, bg in [("TFrame", BG_PANEL), ("Card.TFrame", BG_CARD),
                          ("Deep.TFrame", BG_DEEP), ("Sidebar.TFrame", BG_SIDEBAR),
                          ("Sel.TFrame", BG_SEL)]:
            s.configure(name, background=bg)

        s.configure("TLabel", background=BG_PANEL, foreground=TEXT_MAIN, font=FONT_UI)
        s.configure("Card.TLabel",    background=BG_CARD,    foreground=TEXT_MAIN)
        s.configure("Dim.TLabel",     background=BG_CARD,    foreground=TEXT_DIM,  font=FONT_LABEL)
        s.configure("Sidebar.TLabel", background=BG_SIDEBAR, foreground=TEXT_MAIN)
        s.configure("Deep.TLabel",    background=BG_DEEP,    foreground=TEXT_DIM,  font=FONT_LABEL)
        s.configure("Amber.TLabel",   background=BG_DEEP,    foreground=AMBER,     font=FONT_HEAD)

        s.configure("TEntry", fieldbackground=BG_INPUT, foreground=TEXT_MAIN,
                    insertcolor=AMBER, relief="flat", borderwidth=1, bordercolor=GRAY_DIM)
        s.map("TEntry", bordercolor=[("focus", AMBER_DIM)],
              fieldbackground=[("focus", "#0c1110")])

        s.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT,
                    foreground=TEXT_MAIN, selectbackground=AMBER_DIM,
                    selectforeground=AMBER_GLOW, arrowcolor=AMBER,
                    relief="flat", borderwidth=1)
        s.map("TCombobox", fieldbackground=[("focus", "#0c1110")],
              bordercolor=[("focus", AMBER_DIM)])

        s.configure("TNotebook", background=BG_DEEP, borderwidth=0, tabmargins=0)
        s.configure("TNotebook.Tab", background=BG_PANEL, foreground=TEXT_DIM,
                    padding=[14, 7], font=FONT_UI, borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", BG_CARD)],
              foreground=[("selected", AMBER)])

        s.configure("TLabelframe", background=BG_CARD, foreground=AMBER,
                    bordercolor=GRAY_DIM, relief="flat", borderwidth=1)
        s.configure("TLabelframe.Label", background=BG_CARD,
                    foreground=AMBER, font=FONT_LABEL)

        s.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_MAIN,
                    indicatorcolor=BG_INPUT, indicatorrelief="flat")
        s.map("TCheckbutton", indicatorcolor=[("selected", AMBER)])

        s.configure("Treeview", background=BG_INPUT, fieldbackground=BG_INPUT,
                    foreground=TEXT_MAIN, borderwidth=0, rowheight=22, font=FONT_MONO_SM)
        s.configure("Treeview.Heading", background=BG_PANEL, foreground=AMBER,
                    font=FONT_LABEL, relief="flat", borderwidth=0)
        s.map("Treeview", background=[("selected", AMBER_DIM)],
              foreground=[("selected", AMBER_GLOW)])

        s.configure("Vertical.TScrollbar", background=BG_PANEL, troughcolor=BG_INPUT,
                    arrowcolor=GRAY_MID, relief="flat", borderwidth=0)
        s.configure("Horizontal.TScrollbar", background=BG_PANEL, troughcolor=BG_INPUT,
                    arrowcolor=GRAY_MID, relief="flat", borderwidth=0)

        s.configure("TSeparator", background=GRAY_DIM)

    # ─── UI Layout ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ─────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG_DEEP, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        mono = "Courier New" if WIN else "Monospace"
        tk.Label(hdr, text="◈ MODBUS", bg=BG_DEEP, fg=AMBER,
                 font=(mono, 16, "bold")).pack(side="left", padx=18, pady=10)
        tk.Label(hdr, text="MULTI-SESSION INDUSTRIAL CLIENT", bg=BG_DEEP,
                 fg=TEXT_DIM, font=FONT_LABEL).pack(side="left", pady=10)

        self._hdr_count = tk.Label(hdr, text="0 connections", bg=BG_DEEP,
                                   fg=TEXT_DIM, font=FONT_MONO_SM)
        self._hdr_count.pack(side="right", padx=18)

        tk.Frame(self.root, bg=AMBER_DIM, height=1).pack(fill="x")

        # ── Body ───────────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG_DEEP)
        body.pack(fill="both", expand=True)

        # Sidebar
        self._sidebar = tk.Frame(body, bg=BG_SIDEBAR, width=245)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        tk.Frame(body, bg=GRAY_DIM, width=1).pack(side="left", fill="y")

        # Workspace
        self._workspace = tk.Frame(body, bg=BG_DEEP)
        self._workspace.pack(side="left", fill="both", expand=True)
        self._build_workspace()

    # ─── Sidebar ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        # Title bar
        title_bar = tk.Frame(self._sidebar, bg=BG_SIDEBAR, height=38)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        tk.Label(title_bar, text="CONNECTIONS", bg=BG_SIDEBAR, fg=AMBER,
                 font=FONT_LABEL_B).pack(side="left", padx=10, pady=10)

        add_btn = tk.Button(title_bar, text="+", bg=AMBER_DIM, fg=AMBER_GLOW,
                            activebackground=AMBER, activeforeground=BG_DEEP,
                            font=FONT_UI_B, relief="flat", width=3,
                            cursor="hand2", command=self._add_connection, bd=0)
        add_btn.pack(side="right", padx=8, pady=6)

        tk.Frame(self._sidebar, bg=GRAY_DIM, height=1).pack(fill="x")

        # Scrollable session list
        list_container = tk.Frame(self._sidebar, bg=BG_SIDEBAR)
        list_container.pack(fill="both", expand=True)

        vsb = ttk.Scrollbar(list_container, orient="vertical")
        vsb.pack(side="right", fill="y")

        self._list_canvas = tk.Canvas(list_container, bg=BG_SIDEBAR,
                                       highlightthickness=0, yscrollcommand=vsb.set)
        self._list_canvas.pack(fill="both", expand=True)
        vsb.config(command=self._list_canvas.yview)

        self._session_list_frame = tk.Frame(self._list_canvas, bg=BG_SIDEBAR)
        self._canvas_window = self._list_canvas.create_window(
            (0, 0), window=self._session_list_frame, anchor="nw")

        self._session_list_frame.bind("<Configure>", self._on_list_resize)
        self._list_canvas.bind("<Configure>", self._on_canvas_resize)

        # Bottom controls
        tk.Frame(self._sidebar, bg=GRAY_DIM, height=1).pack(fill="x")
        bottom = tk.Frame(self._sidebar, bg=BG_SIDEBAR, height=38)
        bottom.pack(fill="x")
        bottom.pack_propagate(False)

        for text, cmd, fg in [
            ("Connect All",    self._connect_all,    GREEN_OK),
            ("Disconnect All", self._disconnect_all, RED_ERR),
        ]:
            tk.Button(bottom, text=text, bg=BG_SIDEBAR, fg=fg,
                      activebackground=GRAY_DIM, activeforeground=fg,
                      font=FONT_MONO_XS, relief="flat", cursor="hand2",
                      command=cmd, bd=0).pack(side="left", padx=6, pady=8)

    def _on_list_resize(self, e):
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))

    def _on_canvas_resize(self, e):
        self._list_canvas.itemconfig(self._canvas_window, width=e.width)

    def _add_sidebar_row(self, sess: ConnectionSession):
        """Add a clickable row for a session in the sidebar list."""
        row_frame = tk.Frame(self._session_list_frame, bg=BG_SIDEBAR, cursor="hand2")
        row_frame.pack(fill="x", pady=(0, 1))

        dot = tk.Label(row_frame, text=sess.status_dot(), bg=BG_SIDEBAR,
                        fg=sess.status_color(), font=("Courier New", 12))
        dot.pack(side="left", padx=(10, 4), pady=8)

        info_frame = tk.Frame(row_frame, bg=BG_SIDEBAR)
        info_frame.pack(side="left", fill="x", expand=True, pady=6)

        name_lbl = tk.Label(info_frame, text=sess.label, bg=BG_SIDEBAR,
                             fg=TEXT_MAIN, font=FONT_LABEL_B, anchor="w")
        name_lbl.pack(fill="x")

        ep_lbl = tk.Label(info_frame, text=sess.endpoint_str(), bg=BG_SIDEBAR,
                           fg=TEXT_DIM, font=FONT_MONO_XS, anchor="w")
        ep_lbl.pack(fill="x")

        # Remove button
        rm_btn = tk.Button(row_frame, text="✕", bg=BG_SIDEBAR, fg=TEXT_DIM,
                           activebackground=RED_DIM, activeforeground=RED_ERR,
                           font=FONT_MONO_SM, relief="flat", cursor="hand2",
                           command=lambda: self._remove_session(sess.sid), bd=0)
        rm_btn.pack(side="right", padx=6)

        # Click to select
        for w in [row_frame, dot, info_frame, name_lbl, ep_lbl]:
            w.bind("<Button-1>", lambda e, sid=sess.sid: self._select_session(sid))

        # Context menu
        ctx = tk.Menu(self.root, tearoff=0, bg=BG_CARD, fg=TEXT_MAIN,
                      activebackground=AMBER_DIM, activeforeground=AMBER,
                      font=FONT_LABEL, borderwidth=0)
        ctx.add_command(label="Connect",    command=lambda: self._session_connect(sess.sid))
        ctx.add_command(label="Disconnect", command=lambda: self._session_disconnect(sess.sid))
        ctx.add_separator()
        ctx.add_command(label="Rename",     command=lambda: self._rename_session(sess.sid))
        ctx.add_separator()
        ctx.add_command(label="Remove",     command=lambda: self._remove_session(sess.sid))

        for w in [row_frame, dot, info_frame, name_lbl, ep_lbl]:
            w.bind("<Button-3>", lambda e, m=ctx: m.tk_popup(e.x_root, e.y_root))

        self._sidebar_rows[sess.sid] = {
            "frame": row_frame,
            "dot": dot,
            "name": name_lbl,
            "ep": ep_lbl,
        }

    def _update_sidebar_row(self, sid: str):
        if sid not in self._sidebar_rows or sid not in self.sessions:
            return
        sess = self.sessions[sid]
        row = self._sidebar_rows[sid]
        row["dot"].config(text=sess.status_dot(), fg=sess.status_color())
        row["name"].config(text=sess.label)
        row["ep"].config(text=sess.endpoint_str())

        is_active = (sid == self.active_sid)
        bg = BG_SEL if is_active else BG_SIDEBAR
        for w in [row["frame"], row["dot"], row["name"], row["ep"]]:
            try:
                w.config(bg=bg)
            except Exception:
                pass

    def _highlight_active(self):
        for sid in self._sidebar_rows:
            self._update_sidebar_row(sid)

    # ─── Workspace ─────────────────────────────────────────────────────────────
    def _build_workspace(self):
        # Vertical PanedWindow: top = ops+results, bottom = logs
        self._paned = tk.PanedWindow(self._workspace, orient=tk.VERTICAL,
                                     bg=GRAY_DIM, sashwidth=5,
                                     sashrelief="flat", bd=0)
        self._paned.pack(fill="both", expand=True, padx=10, pady=10)

        # ── Top pane: session header + notebook (read/write/poll) ──────────────
        self._ops_frame = tk.Frame(self._paned, bg=BG_DEEP)
        self._paned.add(self._ops_frame, stretch="always", minsize=320)

        # ── Bottom pane: session log | global log ──────────────────────────────
        log_area = tk.Frame(self._paned, bg=BG_DEEP)
        self._paned.add(log_area, stretch="never", minsize=80)

        self._build_session_log(log_area)
        tk.Frame(log_area, bg=GRAY_DIM, width=1).pack(side="right", fill="y", padx=(4, 0))
        self._build_global_log(log_area)

        self._show_empty_state()

        # Set initial sash position after window is drawn
        self._workspace.after(50, self._set_initial_sash)

    def _set_initial_sash(self):
        total = self._paned.winfo_height()
        if total > 200:
            self._paned.sash_place(0, 0, max(total - 140, total * 3 // 4))

    def _show_empty_state(self):
        for w in self._ops_frame.winfo_children():
            w.destroy()

        empty = tk.Frame(self._ops_frame, bg=BG_DEEP)
        empty.pack(fill="both", expand=True, pady=40)
        tk.Label(empty, text="◈", bg=BG_DEEP, fg=AMBER_DIM,
                 font=("Courier New" if WIN else "Monospace", 36)).pack()
        tk.Label(empty, text="No session selected", bg=BG_DEEP,
                 fg=TEXT_DIM, font=FONT_HEAD).pack(pady=(8, 4))
        tk.Label(empty, text="Press  +  to add a connection, or select one from the sidebar.",
                 bg=BG_DEEP, fg=TEXT_DIM, font=FONT_LABEL).pack()

    # ─── Global Activity Log ────────────────────────────────────────────────────
    def _build_global_log(self, parent):
        lf = tk.LabelFrame(parent, text=" GLOBAL LOG ", bg=BG_CARD,
                            fg=AMBER, font=FONT_LABEL, bd=1, relief="flat",
                            highlightbackground=GRAY_DIM)
        lf.pack(side="left", fill="both", pady=0, padx=(0, 4), ipadx=4, ipady=4)
        lf.pack_propagate(True)

        ctrl = tk.Frame(lf, bg=BG_CARD)
        ctrl.pack(fill="x")
        tk.Button(ctrl, text="Clear", bg=BG_CARD, fg=TEXT_DIM,
                  activebackground=GRAY_DIM, activeforeground=TEXT_MAIN,
                  font=FONT_LABEL, relief="flat", padx=8, pady=2,
                  cursor="hand2", command=lambda: self._clear_log(self._global_log_text),
                  bd=0).pack(side="right")

        self._global_log_text = tk.Text(lf, bg=BG_DEEP, fg=TEXT_MAIN, font=FONT_MONO_XS,
                                         relief="flat", wrap="word", width=30,
                                         insertbackground=AMBER,
                                         selectbackground=AMBER_DIM, borderwidth=0,
                                         pady=4, padx=6)
        self._global_log_text.pack(fill="both", expand=True)
        self._setup_log_tags(self._global_log_text)
        self._global_log_text.config(state="disabled")

    def _setup_log_tags(self, widget):
        widget.tag_configure("ok",    foreground=GREEN_OK)
        widget.tag_configure("error", foreground=RED_ERR)
        widget.tag_configure("warn",  foreground=YELLOW_WARN)
        widget.tag_configure("info",  foreground=BLUE_INFO)
        widget.tag_configure("data",  foreground=TEXT_MAIN)
        widget.tag_configure("ts",    foreground=TEXT_DIM)
        widget.tag_configure("src",   foreground=AMBER_PALE)

    # ─── Per-Session Log ────────────────────────────────────────────────────────
    def _build_session_log(self, parent):
        lf = tk.LabelFrame(parent, text=" SESSION LOG ", bg=BG_CARD,
                            fg=AMBER, font=FONT_LABEL, bd=1, relief="flat",
                            highlightbackground=GRAY_DIM)
        lf.pack(side="right", fill="both", expand=True, pady=0, ipadx=4, ipady=4)

        ctrl = tk.Frame(lf, bg=BG_CARD)
        ctrl.pack(fill="x")
        tk.Button(ctrl, text="Clear", bg=BG_CARD, fg=TEXT_DIM,
                  activebackground=GRAY_DIM, activeforeground=TEXT_MAIN,
                  font=FONT_LABEL, relief="flat", padx=8, pady=2,
                  cursor="hand2", command=lambda: self._clear_log(self._session_log_text),
                  bd=0).pack(side="right")
        self._session_log_label = tk.Label(ctrl, text="No session", bg=BG_CARD,
                                            fg=TEXT_DIM, font=FONT_LABEL)
        self._session_log_label.pack(side="left", padx=6)

        self._session_log_text = tk.Text(lf, bg=BG_DEEP, fg=TEXT_MAIN, font=FONT_MONO_SM,
                                          relief="flat", wrap="word",
                                          insertbackground=AMBER,
                                          selectbackground=AMBER_DIM, borderwidth=0,
                                          pady=4, padx=8)
        self._session_log_text.pack(fill="both", expand=True)
        self._setup_log_tags(self._session_log_text)
        self._session_log_text.config(state="disabled")

    def _clear_log(self, widget):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.config(state="disabled")

    def _append_to_log(self, widget, ts, msg, tag, src=None):
        widget.config(state="normal")
        widget.insert("end", f"[{ts}] ", "ts")
        if src:
            widget.insert("end", f"[{src}] ", "src")
        widget.insert("end", msg + "\n", tag)
        widget.see("end")
        widget.config(state="disabled")

    def _global_log(self, msg: str, tag: str = "data", src: str = None):
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_to_log(self._global_log_text, ts, msg, tag, src)

    def _session_log(self, sess: ConnectionSession, msg: str, tag: str = "data"):
        """Append a log entry for a session; display it if the session is active."""
        ts = datetime.now().strftime("%H:%M:%S")
        sess.log_entries.append((ts, msg, tag))   # deque auto-trims at maxlen=500
        # Mirror to global log
        self._global_log_queue.put((ts, f"[{sess.label}] {msg}", tag, sess.label))
        # If active, push to session log widget on the main thread
        if sess.sid == self.active_sid:
            self.root.after(0, self._append_to_log,
                            self._session_log_text, ts, msg, tag, None)

    # ─── Queue Pump ────────────────────────────────────────────────────────────
    def _pump_queues(self):
        try:
            while True:
                ts, msg, tag, src = self._global_log_queue.get_nowait()
                self._append_to_log(self._global_log_text, ts, msg, tag, src=None)
        except queue.Empty:
            pass
        self.root.after(100, self._pump_queues)

    # ─── Session Management ─────────────────────────────────────────────────────
    def _add_connection(self):
        dlg = NewConnectionDialog(self.root)
        self.root.wait_window(dlg.dialog)
        if not dlg.result:
            return
        sess = dlg.result
        self.sessions[sess.sid] = sess
        self.session_order.append(sess.sid)
        self._add_sidebar_row(sess)
        self._update_header_count()
        self._select_session(sess.sid)
        self._global_log(f"Session '{sess.label}' added ({sess.endpoint_str()})", "info")

    def _remove_session(self, sid: str):
        if sid not in self.sessions:
            return
        sess = self.sessions[sid]
        if sess.state == ST_CONNECTED:
            if not messagebox.askyesno("Remove Session",
                f"'{sess.label}' is connected.\nDisconnect and remove?",
                parent=self.root):
                return
            self._session_disconnect(sid, quiet=True)

        # Remove sidebar row
        row = self._sidebar_rows.pop(sid, None)
        if row:
            row["frame"].destroy()

        del self.sessions[sid]
        self.session_order.remove(sid)
        self._update_header_count()

        if self.active_sid == sid:
            self.active_sid = None
            if self.session_order:
                self._select_session(self.session_order[-1])
            else:
                self._show_empty_state()
                self._session_log_label.config(text="No session")

        self._global_log(f"Session '{sess.label}' removed.", "warn")

    def _rename_session(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess:
            return
        new_name = simpledialog.askstring("Rename Session", "New label:",
                                          initialvalue=sess.label, parent=self.root)
        if new_name and new_name.strip():
            sess.label = new_name.strip()
            self._update_sidebar_row(sid)
            if self.active_sid == sid:
                self._session_log_label.config(text=sess.label)

    def _select_session(self, sid: str):
        if sid not in self.sessions:
            return
        # Save ops panel state from previous session (if any)
        if self.active_sid and self.active_sid in self.sessions:
            self._save_ops_state(self.active_sid)

        self.active_sid = sid
        sess = self.sessions[sid]

        self._highlight_active()
        self._build_ops_panel(sess)
        self._load_session_log(sess)
        self._session_log_label.config(text=f"{sess.label}  ·  {sess.endpoint_str()}")

    def _load_session_log(self, sess: ConnectionSession):
        """Populate session log widget with stored entries."""
        self._session_log_text.config(state="normal")
        self._session_log_text.delete("1.0", "end")
        for ts, msg, tag in sess.log_entries:
            self._session_log_text.insert("end", f"[{ts}] ", "ts")
            self._session_log_text.insert("end", msg + "\n", tag)
        self._session_log_text.see("end")
        self._session_log_text.config(state="disabled")

    def _update_header_count(self):
        total = len(self.sessions)
        connected = sum(1 for s in self.sessions.values() if s.state == ST_CONNECTED)
        self._hdr_count.config(
            text=f"{connected}/{total} connected",
            fg=GREEN_OK if connected else TEXT_DIM)

    # ─── Operations Panel (per session) ────────────────────────────────────────
    def _build_ops_panel(self, sess: ConnectionSession):
        for w in self._ops_frame.winfo_children():
            w.destroy()
        self._op_widgets = {}

        # ── Row 0: Session header + connect button ─────────────────────────────
        hdr = tk.Frame(self._ops_frame, bg=BG_DEEP)
        hdr.pack(fill="x", pady=(0, 6))

        dot = tk.Label(hdr, text=sess.status_dot(), bg=BG_DEEP,
                        fg=sess.status_color(), font=("Courier New", 14))
        dot.pack(side="left", padx=(0, 6))
        self._op_widgets["hdr_dot"] = dot

        name = tk.Label(hdr, text=sess.label, bg=BG_DEEP, fg=TEXT_HEAD, font=FONT_HEAD)
        name.pack(side="left")
        self._op_widgets["hdr_name"] = name

        ep = tk.Label(hdr, text=f"  {sess.endpoint_str()}", bg=BG_DEEP,
                       fg=TEXT_DIM, font=FONT_MONO_SM)
        ep.pack(side="left")

        # Connect/disconnect button
        conn_btn = tk.Button(hdr, text="", relief="flat", font=FONT_UI_B,
                              pady=4, padx=16, cursor="hand2", bd=0)
        conn_btn.pack(side="right")
        self._op_widgets["conn_btn"] = conn_btn
        self._update_conn_btn(sess)
        conn_btn.config(command=lambda: self._toggle_session_connection(sess.sid))

        # Edit config button
        tk.Button(hdr, text="⚙ Edit", bg=BG_PANEL, fg=TEXT_DIM,
                  activebackground=GRAY_DIM, activeforeground=TEXT_MAIN,
                  font=FONT_LABEL, relief="flat", padx=10, pady=4,
                  cursor="hand2", bd=0,
                  command=lambda: self._edit_session_config(sess.sid)
                  ).pack(side="right", padx=6)

        tk.Frame(self._ops_frame, bg=GRAY_DIM, height=1).pack(fill="x", pady=(0, 6))

        # ── Ops Notebook ───────────────────────────────────────────────────────
        nb = ttk.Notebook(self._ops_frame)
        nb.pack(fill="both", expand=True)
        self._op_widgets["notebook"] = nb

        self._build_read_tab(nb, sess)
        self._build_write_tab(nb, sess)
        self._build_poll_tab(nb, sess)

    def _update_conn_btn(self, sess: ConnectionSession):
        btn = self._op_widgets.get("conn_btn")
        if not btn:
            return
        if sess.state == ST_CONNECTED:
            btn.config(text="■ DISCONNECT", bg=RED_DIM, fg=RED_ERR,
                        activebackground="#4a1010")
        elif sess.state == ST_CONNECTING:
            btn.config(text="◌ CONNECTING…", bg=GRAY_DIM, fg=YELLOW_WARN,
                        activebackground=GRAY_DIM)
        else:
            btn.config(text="▶ CONNECT", bg=AMBER_DIM, fg=AMBER_GLOW,
                        activebackground=AMBER)

        dot = self._op_widgets.get("hdr_dot")
        if dot:
            dot.config(text=sess.status_dot(), fg=sess.status_color())

    def _save_ops_state(self, sid: str):
        """Read current op widget values back into the session."""
        sess = self.sessions.get(sid)
        if not sess:
            return
        w = self._op_widgets
        try:
            if "read_type" in w:    sess.read_type   = w["read_type"].get()
            if "read_addr" in w:    sess.read_addr   = int(w["read_addr"].get(), 0)
            if "read_count" in w:   sess.read_count  = int(w["read_count"].get())
            if "read_unit" in w:    sess.read_unit   = int(w["read_unit"].get())
            if "write_type" in w:   sess.write_type  = w["write_type"].get()
            if "write_addr" in w:   sess.write_addr  = int(w["write_addr"].get(), 0)
            if "write_unit" in w:   sess.write_unit  = int(w["write_unit"].get())
            if "write_value" in w:  sess.write_value = w["write_value"].get()
            if "confirm_wr" in w:   sess.confirm_write = w["confirm_wr"].get()
            if "poll_ivl" in w:     sess.poll_interval = float(w["poll_ivl"].get())
            if "write_ivl" in w:    sess.write_poll_interval = float(w["write_ivl"].get())
        except (ValueError, AttributeError):
            pass

    # ─── Read Tab ──────────────────────────────────────────────────────────────
    def _build_read_tab(self, nb, sess: ConnectionSession):
        tab = ttk.Frame(nb, style="Card.TFrame", padding=10)
        nb.add(tab, text=" ↓  READ ")

        ctrl_row = ttk.Frame(tab, style="Card.TFrame")
        ctrl_row.pack(fill="x", pady=(0, 6))

        lbl = lambda t, w=9: ttk.Label(ctrl_row, text=t, style="Card.TLabel", width=w)

        lbl("Type").pack(side="left")
        rt_var = tk.StringVar(value=sess.read_type)
        rt_cb = ttk.Combobox(ctrl_row, textvariable=rt_var, width=18, state="readonly",
                              values=["Holding Registers", "Input Registers",
                                      "Coils", "Discrete Inputs"])
        rt_cb.pack(side="left", padx=(0, 10))
        self._op_widgets["read_type"] = rt_var

        lbl("Address", 8).pack(side="left")
        ra_var = tk.StringVar(value=str(sess.read_addr))
        ttk.Entry(ctrl_row, textvariable=ra_var, width=7).pack(side="left", padx=(0, 10))
        self._op_widgets["read_addr"] = ra_var

        lbl("Count", 6).pack(side="left")
        rc_var = tk.StringVar(value=str(sess.read_count))
        ttk.Entry(ctrl_row, textvariable=rc_var, width=5).pack(side="left", padx=(0, 10))
        self._op_widgets["read_count"] = rc_var

        lbl("Unit", 4).pack(side="left")
        ru_var = tk.StringVar(value=str(sess.read_unit))
        ttk.Entry(ctrl_row, textvariable=ru_var, width=4).pack(side="left", padx=(0, 10))
        self._op_widgets["read_unit"] = ru_var

        tk.Button(ctrl_row, text="READ", bg=BLUE_INFO, fg=BG_DEEP,
                  activebackground="#3a85d0", activeforeground=BG_DEEP,
                  font=FONT_UI_B, relief="flat", padx=14, pady=3,
                  cursor="hand2", bd=0,
                  command=lambda: self._do_read(sess.sid)).pack(side="left")

        ttk.Label(ctrl_row, text="  Double-click row to label it",
                  style="Dim.TLabel", font=FONT_MONO_XS).pack(side="right")

        # ── Results table ──────────────────────────────────────────────────────
        tf = ttk.Frame(tab, style="Card.TFrame")
        tf.pack(fill="both", expand=True)

        vsb = ttk.Scrollbar(tf, orient="vertical")
        vsb.pack(side="right", fill="y")
        hsb = ttk.Scrollbar(tf, orient="horizontal")
        hsb.pack(side="bottom", fill="x")

        cols = ("Label", "Address", "Dec", "Hex", "Bin", "State")
        tree = ttk.Treeview(tf, columns=cols, show="headings",
                             yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)

        col_cfg = [("Label", 140, "w"), ("Address", 80, "center"),
                   ("Dec", 90, "center"),  ("Hex", 90, "center"),
                   ("Bin", 150, "center"), ("State", 60, "center")]
        for col, w, anc in col_cfg:
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor=anc, minwidth=w)

        tree.tag_configure("odd",     background=BG_ROW_ALT)
        tree.tag_configure("even",    background=BG_INPUT)
        tree.tag_configure("labeled", foreground=AMBER_GLOW)
        tree.pack(fill="both", expand=True)
        self._op_widgets["read_tree"] = tree

        # Double-click → label editor
        def _on_double_click(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            vals = tree.item(item, "values")
            if not vals:
                return
            addr_str = vals[1]   # Address column
            rtype = self._op_widgets.get("read_type")
            rtype_val = rtype.get() if rtype else "Holding Registers"
            label_key = f"{rtype_val}:{addr_str}"
            current_label = sess.reg_labels.get(label_key, "")
            new_label = simpledialog.askstring(
                "Label Register",
                "Label for " + rtype_val + " addr " + addr_str + "\n(leave blank to clear)",
                initialvalue=current_label,
                parent=self.root)
            if new_label is None:
                return   # cancelled
            new_label = new_label.strip()
            if new_label:
                sess.reg_labels[label_key] = new_label
            elif label_key in sess.reg_labels:
                del sess.reg_labels[label_key]
            # Refresh just this row
            rtype_now = self._op_widgets.get("read_type")
            rt = rtype_now.get() if rtype_now else rtype_val
            tag = tree.item(item, "tags")[0] if tree.item(item, "tags") else "even"
            new_vals = list(vals)
            new_vals[0] = new_label
            tags = (tag, "labeled") if new_label else (tag,)
            tree.item(item, values=new_vals, tags=tags)

        tree.bind("<Double-1>", _on_double_click)

    # ─── Write Tab ─────────────────────────────────────────────────────────────
    def _build_write_tab(self, nb, sess: ConnectionSession):
        tab = ttk.Frame(nb, style="Card.TFrame", padding=10)
        nb.add(tab, text=" ↑  WRITE ")

        # ── Target row ──────────────────────────────────────────────────────────
        row = ttk.Frame(tab, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 6))

        lbl = lambda t, w=9: ttk.Label(row, text=t, style="Card.TLabel", width=w)

        lbl("Type").pack(side="left")
        wt_var = tk.StringVar(value=sess.write_type)
        ttk.Combobox(row, textvariable=wt_var, width=18, state="readonly",
                     values=["Holding Register", "Multiple Registers",
                              "Coil", "Multiple Coils"]).pack(side="left", padx=(0, 10))
        self._op_widgets["write_type"] = wt_var

        lbl("Address", 8).pack(side="left")
        wa_var = tk.StringVar(value=str(sess.write_addr))
        ttk.Entry(row, textvariable=wa_var, width=7).pack(side="left", padx=(0, 10))
        self._op_widgets["write_addr"] = wa_var

        lbl("Unit", 4).pack(side="left")
        wu_var = tk.StringVar(value=str(sess.write_unit))
        ttk.Entry(row, textvariable=wu_var, width=4).pack(side="left")
        self._op_widgets["write_unit"] = wu_var

        # ── Value row ───────────────────────────────────────────────────────────
        row2 = ttk.Frame(tab, style="Card.TFrame")
        row2.pack(fill="x", pady=(0, 6))

        ttk.Label(row2, text="Value(s)", style="Card.TLabel", width=9).pack(side="left")
        wv_var = tk.StringVar(value=sess.write_value)
        ttk.Entry(row2, textvariable=wv_var, width=36).pack(side="left", padx=(0, 10))
        self._op_widgets["write_value"] = wv_var
        ttk.Label(row2, text="Comma-separated for multiple",
                  style="Dim.TLabel", font=FONT_MONO_SM).pack(side="left")

        # ── Actions row ─────────────────────────────────────────────────────────
        row3 = ttk.Frame(tab, style="Card.TFrame")
        row3.pack(fill="x", pady=(0, 6))

        cw_var = tk.BooleanVar(value=sess.confirm_write)
        ttk.Checkbutton(row3, text="Confirm before write",
                        variable=cw_var).pack(side="left", padx=(0, 20))
        self._op_widgets["confirm_wr"] = cw_var

        tk.Button(row3, text="⚡ WRITE ONCE", bg=RED_DIM, fg="#ff9999",
                  activebackground=RED_ERR, activeforeground=BG_DEEP,
                  font=FONT_UI_B, relief="flat", padx=14, pady=4,
                  cursor="hand2", bd=0,
                  command=lambda: self._do_write(sess.sid)).pack(side="left")

        # ── Continuous write ─────────────────────────────────────────────────────
        cw_frame = ttk.LabelFrame(tab, text=" Continuous Write ", padding=8)
        cw_frame.pack(fill="x", pady=(6, 4))

        cwrow = ttk.Frame(cw_frame, style="Card.TFrame")
        cwrow.pack(fill="x")

        ttk.Label(cwrow, text="Interval (s)", style="Card.TLabel", width=12).pack(side="left")
        wivl_var = tk.StringVar(value=str(sess.write_poll_interval))
        ttk.Entry(cwrow, textvariable=wivl_var, width=8).pack(side="left", padx=(0, 16))
        self._op_widgets["write_ivl"] = wivl_var

        self._op_widgets["write_poll_last"] = ttk.Label(
            cwrow,
            text="Last: " + (sess.last_write_poll_ts or "—"),
            style="Dim.TLabel", font=FONT_MONO_SM)
        self._op_widgets["write_poll_last"].pack(side="left")

        wpoll_btn = tk.Button(cw_frame, font=FONT_UI_B, relief="flat", pady=5,
                              cursor="hand2", bd=0)
        wpoll_btn.pack(fill="x", pady=(6, 0))
        self._op_widgets["write_poll_btn"] = wpoll_btn
        self._update_write_poll_btn(sess)
        wpoll_btn.config(command=lambda: self._toggle_write_poll(sess.sid))

        ttk.Label(cw_frame,
                  text="Repeats the write above at the given interval. Confirm dialog is suppressed.",
                  style="Dim.TLabel", font=FONT_MONO_XS).pack(anchor="w", pady=(4, 0))

        # ── Format converter ────────────────────────────────────────────────────
        fmt = ttk.LabelFrame(tab, text=" Format Converter ", padding=8)
        fmt.pack(fill="x", pady=(4, 0))
        frow = ttk.Frame(fmt, style="Card.TFrame")
        frow.pack(fill="x")
        ttk.Label(frow, text="Value:", style="Card.TLabel").pack(side="left", padx=(0, 6))
        ci_var = tk.StringVar(value="0")
        ttk.Entry(frow, textvariable=ci_var, width=12).pack(side="left", padx=(0, 6))
        self._op_widgets["conv_in"] = ci_var

        fr_lbl = ttk.Label(fmt, text="", style="Card.TLabel", font=FONT_MONO)
        fr_lbl.pack(anchor="w", pady=(4, 0))
        self._op_widgets["conv_result"] = fr_lbl

        for lbl_txt, fmt_key in [("→ Hex", "hex"), ("→ Dec", "dec"), ("→ Bin", "bin")]:
            tk.Button(frow, text=lbl_txt, bg=BG_PANEL, fg=TEXT_DIM,
                      activebackground=GRAY_DIM, activeforeground=TEXT_MAIN,
                      font=FONT_LABEL, relief="flat", padx=8, pady=3,
                      cursor="hand2", bd=0,
                      command=lambda f=fmt_key: self._do_fmt(f)).pack(side="left", padx=2)

    # ─── Poll Tab ──────────────────────────────────────────────────────────────
    def _build_poll_tab(self, nb, sess: ConnectionSession):
        tab = ttk.Frame(nb, style="Card.TFrame", padding=10)
        nb.add(tab, text=" ⟳  POLL ")

        # ── Read polling ────────────────────────────────────────────────────────
        rp = ttk.LabelFrame(tab, text=" Continuous Read ", padding=8)
        rp.pack(fill="x", pady=(0, 8))

        rrow = ttk.Frame(rp, style="Card.TFrame")
        rrow.pack(fill="x", pady=(0, 6))

        ttk.Label(rrow, text="Interval (s)", style="Card.TLabel", width=12).pack(side="left")
        ivl_var = tk.StringVar(value=str(sess.poll_interval))
        ttk.Entry(rrow, textvariable=ivl_var, width=8).pack(side="left", padx=(0, 16))
        self._op_widgets["poll_ivl"] = ivl_var

        last_r = ttk.Label(rrow, text="Last: " + (sess.last_poll_ts or "—"),
                           style="Dim.TLabel", font=FONT_MONO_SM)
        last_r.pack(side="left")
        self._op_widgets["poll_last"] = last_r

        poll_btn = tk.Button(rp, font=FONT_UI_B, relief="flat", pady=5,
                             cursor="hand2", bd=0)
        poll_btn.pack(fill="x")
        self._op_widgets["poll_btn"] = poll_btn
        self._update_poll_btn(sess)
        poll_btn.config(command=lambda: self._toggle_poll(sess.sid))

        ttk.Label(rp, text="Uses the Read tab settings (type, address, count, unit).",
                  style="Dim.TLabel", font=FONT_MONO_XS).pack(anchor="w", pady=(4, 0))

        # ── Write polling ───────────────────────────────────────────────────────
        wp = ttk.LabelFrame(tab, text=" Continuous Write ", padding=8)
        wp.pack(fill="x", pady=(0, 4))

        wrow = ttk.Frame(wp, style="Card.TFrame")
        wrow.pack(fill="x", pady=(0, 6))

        ttk.Label(wrow, text="Interval (s)", style="Card.TLabel", width=12).pack(side="left")
        wivl_var2 = tk.StringVar(value=str(sess.write_poll_interval))
        ttk.Entry(wrow, textvariable=wivl_var2, width=8).pack(side="left", padx=(0, 16))
        self._op_widgets["write_ivl"] = wivl_var2

        last_w = ttk.Label(wrow, text="Last: " + (sess.last_write_poll_ts or "—"),
                           style="Dim.TLabel", font=FONT_MONO_SM)
        last_w.pack(side="left")
        self._op_widgets["write_poll_last"] = last_w

        wpoll_btn = tk.Button(wp, font=FONT_UI_B, relief="flat", pady=5,
                              cursor="hand2", bd=0)
        wpoll_btn.pack(fill="x")
        self._op_widgets["write_poll_btn"] = wpoll_btn
        self._update_write_poll_btn(sess)
        wpoll_btn.config(command=lambda: self._toggle_write_poll(sess.sid))

        ttk.Label(wp, text="Uses the Write tab settings. Confirm dialog is suppressed.",
                  style="Dim.TLabel", font=FONT_MONO_XS).pack(anchor="w", pady=(4, 0))

    def _update_poll_btn(self, sess: ConnectionSession):
        btn = self._op_widgets.get("poll_btn")
        if not btn:
            return
        if sess.polling:
            btn.config(text="■  STOP READ POLLING", bg=RED_DIM, fg=RED_ERR,
                       activebackground="#3a1010")
        else:
            btn.config(text="▶  START READ POLLING", bg=GREEN_DIM, fg=GREEN_OK,
                       activebackground="#1a4030")

    def _update_write_poll_btn(self, sess: ConnectionSession):
        btn = self._op_widgets.get("write_poll_btn")
        if not btn:
            return
        if sess.write_polling:
            btn.config(text="■  STOP WRITE POLLING", bg=RED_DIM, fg=RED_ERR,
                       activebackground="#3a1010")
        else:
            btn.config(text="▶  START WRITE POLLING", bg="#3a2000", fg=AMBER_GLOW,
                       activebackground=AMBER_DIM)

    # ─── Connection Actions ─────────────────────────────────────────────────────
    def _toggle_session_connection(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess:
            return
        if sess.state == ST_CONNECTED:
            self._session_disconnect(sid)
        elif sess.state == ST_CONNECTING:
            self._session_log(sess, "Already connecting — please wait.", "warn")
        else:
            threading.Thread(target=self._session_connect, args=(sid,), daemon=True).start()

    def _session_connect(self, sid: str, quiet: bool = False):
        sess = self.sessions.get(sid)
        if not sess:
            return
        if not PYMODBUS_AVAILABLE:
            self._session_log(sess,
                f"pymodbus unavailable. Run:  \"{sys.executable}\" -m pip install pymodbus", "error")
            sess.state = ST_ERROR
            self.root.after(0, self._update_conn_btn, sess)
            self.root.after(0, self._update_sidebar_row, sid)
            return

        sess.state = ST_CONNECTING
        self.root.after(0, self._update_conn_btn, sess)
        self.root.after(0, self._update_sidebar_row, sid)

        try:
            if sess.mode == "TCP":
                self._session_log(sess, f"Connecting to {sess.host}:{sess.port} …", "info")
                c = ModbusTcpClient(sess.host, port=sess.port, timeout=sess.timeout)
            else:
                self._session_log(sess, f"Connecting to {sess.serial_port} @ {sess.baudrate} baud …", "info")
                c = ModbusSerialClient(port=sess.serial_port, baudrate=sess.baudrate,
                                        parity=sess.parity, stopbits=sess.stopbits,
                                        bytesize=sess.bytesize, timeout=sess.timeout)
            ok = c.connect()
        except Exception as ex:
            sess.state = ST_ERROR
            sess.error_msg = str(ex)
            self._session_log(sess, f"Connection error: {ex}", "error")
            self.root.after(0, self._update_conn_btn, sess)
            self.root.after(0, self._update_sidebar_row, sid)
            self.root.after(0, self._update_header_count)
            return

        if ok:
            sess.client = c
            sess.state = ST_CONNECTED
            self._session_log(sess, "Connected.", "ok")
        else:
            sess.state = ST_ERROR
            sess.error_msg = "Connection refused"
            self._session_log(sess, "Connection refused or timed out.", "error")

        self.root.after(0, self._update_conn_btn, sess)
        self.root.after(0, self._update_sidebar_row, sid)
        self.root.after(0, self._update_header_count)

    def _session_disconnect(self, sid: str, quiet: bool = False):
        sess = self.sessions.get(sid)
        if not sess:
            return
        if sess.polling:
            self._stop_poll(sid)
        if sess.write_polling:
            self._stop_write_poll(sid)
        if sess.client:
            try:
                sess.client.close()
            except Exception:
                pass
            sess.client = None
        sess.state = ST_DISCONNECTED
        if not quiet:
            self._session_log(sess, "Disconnected.", "warn")
        self.root.after(0, self._update_conn_btn, sess)
        self.root.after(0, self._update_sidebar_row, sid)
        self.root.after(0, self._update_header_count)

    def _connect_all(self):
        for sid in list(self.session_order):
            sess = self.sessions.get(sid)
            if sess and sess.state != ST_CONNECTED:
                threading.Thread(target=self._session_connect, args=(sid,), daemon=True).start()

    def _disconnect_all(self):
        for sid in list(self.session_order):
            self._session_disconnect(sid, quiet=True)
        self._global_log("All sessions disconnected.", "warn")

    def _edit_session_config(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess:
            return
        if sess.state == ST_CONNECTED:
            if not messagebox.askyesno("Edit Config",
                "Disconnect before editing configuration?", parent=self.root):
                return
            self._session_disconnect(sid, quiet=True)

        dlg = NewConnectionDialog(self.root, existing=sess)
        self.root.wait_window(dlg.dialog)
        if dlg.result:
            # Copy updated fields back
            updated = dlg.result
            for attr in ["label", "mode", "host", "port", "timeout",
                          "serial_port", "baudrate", "parity", "stopbits",
                          "bytesize", "default_unit"]:
                setattr(sess, attr, getattr(updated, attr))
            self._update_sidebar_row(sid)
            if self.active_sid == sid:
                self._select_session(sid)

    # ─── Read / Write Operations ────────────────────────────────────────────────
    def _do_read(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess or sess.state != ST_CONNECTED:
            if sess:
                self._session_log(sess, "Not connected.", "error")
            return

        # If this is the active session, sync current widget values into the session
        # first so the poll uses whatever the user has typed.
        # For non-active sessions, use the saved session values directly —
        # we must NOT touch self._op_widgets, which belongs to the active session.
        if sid == self.active_sid:
            w = self._op_widgets
            try:
                rtype = w["read_type"].get()
                addr  = int(w["read_addr"].get(), 0)
                count = int(w["read_count"].get())
                unit  = int(w["read_unit"].get())
                # Persist back so poll loop picks up live edits
                sess.read_type  = rtype
                sess.read_addr  = addr
                sess.read_count = count
                sess.read_unit  = unit
            except (KeyError, ValueError) as e:
                self._session_log(sess, f"Invalid read params: {e}", "error")
                return
        else:
            rtype = sess.read_type
            addr  = sess.read_addr
            count = sess.read_count
            unit  = sess.read_unit

        # Input validation (Modbus protocol limits)
        if not (0 <= addr <= 65535):
            self._session_log(sess, f"Address {addr} out of range (0–65535).", "error")
            return
        is_bit_type = rtype in ("Coils", "Discrete Inputs")
        max_count = 2000 if is_bit_type else 125
        if not (1 <= count <= max_count):
            self._session_log(sess, f"Count {count} out of range (1–{max_count} for {rtype}).", "error")
            return
        if not (1 <= unit <= 247):
            self._session_log(sess, f"Unit ID {unit} out of range (1–247).", "error")
            return

        threading.Thread(target=self._read_worker,
                         args=(sess, rtype, addr, count, unit), daemon=True).start()

    def _read_worker(self, sess: ConnectionSession, rtype, addr, count, unit):
        self._session_log(sess, f"READ {rtype} addr={addr} count={count} unit={unit}", "info")
        c = sess.client  # snapshot — disconnect may null sess.client at any point
        if c is None:
            self._session_log(sess, "Client disconnected before read completed.", "error")
            return
        try:
            if rtype == "Holding Registers":
                result = c.read_holding_registers(addr, count=count, slave=unit)
            elif rtype == "Input Registers":
                result = c.read_input_registers(addr, count=count, slave=unit)
            elif rtype == "Coils":
                result = c.read_coils(addr, count=count, slave=unit)
            else:
                result = c.read_discrete_inputs(addr, count=count, slave=unit)

            if result.isError():
                self._session_log(sess, f"Modbus error: {result}", "error")
                return

            self.root.after(0, self._populate_tree, sess.sid, result, addr, rtype, count)
            self._session_log(sess, f"✓ {count} value(s) from addr {addr}", "ok")
        except Exception as e:
            self._session_log(sess, f"Read exception: {e}", "error")

    def _populate_tree(self, sid: str, result, base_addr, rtype, count):
        if sid != self.active_sid:
            return
        tree = self._op_widgets.get("read_tree")
        if not tree:
            return
        sess = self.sessions.get(sid)
        reg_labels = sess.reg_labels if sess else {}

        for row in tree.get_children():
            tree.delete(row)

        is_bit = rtype in ("Coils", "Discrete Inputs")
        values = list(result.bits[:count]) if is_bit else result.registers

        for i, val in enumerate(values):
            addr = base_addr + i
            label_key = f"{rtype}:{addr}"
            row_label = reg_labels.get(label_key, "")
            tag = "odd" if i % 2 else "even"
            tags = (tag, "labeled") if row_label else (tag,)
            if is_bit:
                iv = int(val)
                tree.insert("", "end", tags=tags,
                             values=(row_label, addr, iv, "—",
                                     f"{iv:08b}", "ON" if val else "OFF"))
            else:
                tree.insert("", "end", tags=tags,
                             values=(row_label, addr, val, f"0x{val:04X}",
                                     f"{val:016b}", ""))

    def _do_write(self, sid: str, suppress_confirm: bool = False):
        sess = self.sessions.get(sid)
        if not sess or sess.state != ST_CONNECTED:
            if sess:
                self._session_log(sess, "Not connected.", "error")
            return
        # For non-active sessions (e.g. write poll loop), read params from session object
        if sid == self.active_sid:
            w = self._op_widgets
            try:
                wtype = w["write_type"].get()
                addr  = int(w["write_addr"].get(), 0)
                unit  = int(w["write_unit"].get())
                raw   = w["write_value"].get().strip()
                confirm = w["confirm_wr"].get() and not suppress_confirm
                sess.write_type  = wtype
                sess.write_addr  = addr
                sess.write_unit  = unit
                sess.write_value = raw
            except (KeyError, ValueError) as e:
                self._session_log(sess, f"Invalid write params: {e}", "error")
                return
        else:
            wtype   = sess.write_type
            addr    = sess.write_addr
            unit    = sess.write_unit
            raw     = sess.write_value
            confirm = False   # always suppress for background sessions
        try:
            values = ([int(v.strip(), 0) for v in raw.split(",") if v.strip()]
                      if "," in raw else [int(raw, 0)])
        except ValueError:
            self._session_log(sess, f"Cannot parse value(s): {raw!r}", "error")
            return

        # Input validation (Modbus protocol limits)
        if not (0 <= addr <= 65535):
            self._session_log(sess, f"Address {addr} out of range (0–65535).", "error")
            return
        if not (1 <= unit <= 247):
            self._session_log(sess, f"Unit ID {unit} out of range (1–247).", "error")
            return
        is_coil_type = "Coil" in wtype
        if not is_coil_type:
            invalid = [v for v in values if not (0 <= v <= 65535)]
            if invalid:
                self._session_log(sess, f"Register value(s) out of range (0–65535): {invalid}", "error")
                return

        if confirm:
            summary = (f"Session: {sess.label}\nWrite {wtype}\n"
                       f"Address: {addr}\nValue(s): {values}\nUnit: {unit}")
            if not messagebox.askyesno("Confirm Write", summary,
                                        icon="warning", parent=self.root):
                self._session_log(sess, "Write cancelled.", "warn")
                return

        threading.Thread(target=self._write_worker,
                         args=(sess, wtype, addr, values, unit), daemon=True).start()

    def _write_worker(self, sess, wtype, addr, values, unit):
        self._session_log(sess, f"WRITE {wtype} addr={addr} values={values} unit={unit}", "info")
        c = sess.client  # snapshot — disconnect may null sess.client at any point
        if c is None:
            self._session_log(sess, "Client disconnected before write completed.", "error")
            return
        try:
            if wtype == "Holding Register":
                r = c.write_register(addr, value=values[0], slave=unit)
            elif wtype == "Multiple Registers":
                r = c.write_registers(addr, values=values, slave=unit)
            elif wtype == "Coil":
                r = c.write_coil(addr, value=bool(values[0]), slave=unit)
            else:
                r = c.write_coils(addr, values=[bool(v) for v in values], slave=unit)

            if r.isError():
                self._session_log(sess, f"Write error: {r}", "error")
            else:
                self._session_log(sess, f"✓ Write OK — {len(values)} value(s) written.", "ok")
        except Exception as e:
            self._session_log(sess, f"Write exception: {e}", "error")

    # ─── Polling ────────────────────────────────────────────────────────────────
    def _toggle_poll(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess:
            return
        if sess.polling:
            self._stop_poll(sid)
        else:
            self._start_poll(sid)

    def _start_poll(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess or sess.state != ST_CONNECTED:
            if sess:
                self._session_log(sess, "Cannot poll: not connected.", "error")
            return
        try:
            ivl_str = self._op_widgets["poll_ivl"].get() if "poll_ivl" in self._op_widgets else "1.0"
            ivl = float(ivl_str)
        except (ValueError, AttributeError):
            ivl = 1.0
        # Security/stability: enforce a minimum poll interval to prevent spin-lock
        POLL_MIN = 0.1
        if ivl < POLL_MIN:
            self._session_log(sess, f"Poll interval too low — clamped to {POLL_MIN}s.", "warn")
            ivl = POLL_MIN
        sess.poll_interval = ivl
        sess.polling = True
        sess.poll_stop.clear()
        self._session_log(sess, f"Polling started (every {ivl}s).", "info")
        self._update_poll_btn(sess)
        sess.poll_thread = threading.Thread(
            target=self._poll_loop, args=(sid,), daemon=True)
        sess.poll_thread.start()

    def _stop_poll(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess:
            return
        sess.polling = False
        sess.poll_stop.set()
        self._session_log(sess, "Polling stopped.", "warn")
        if self.active_sid == sid:
            self.root.after(0, self._update_poll_btn, sess)

    def _poll_loop(self, sid: str):
        while True:
            sess = self.sessions.get(sid)
            if not sess or not sess.polling:
                break
            if sess.state == ST_CONNECTED:
                self.root.after(0, self._do_read, sid)
                ts = datetime.now().strftime("%H:%M:%S")
                sess.last_poll_ts = ts
                if self.active_sid == sid:
                    lbl = self._op_widgets.get("poll_last")
                    if lbl:
                        self.root.after(0, lbl.config, {"text": f"Last: {ts}"})
            sess.poll_stop.wait(sess.poll_interval)
            sess.poll_stop.clear()

    # ─── Continuous Write ──────────────────────────────────────────────────────
    def _toggle_write_poll(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess:
            return
        if sess.write_polling:
            self._stop_write_poll(sid)
        else:
            self._start_write_poll(sid)

    def _start_write_poll(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess or sess.state != ST_CONNECTED:
            if sess:
                self._session_log(sess, "Cannot start continuous write: not connected.", "error")
            return
        try:
            ivl_str = self._op_widgets["write_ivl"].get() if "write_ivl" in self._op_widgets else "1.0"
            ivl = float(ivl_str)
        except (ValueError, AttributeError):
            ivl = 1.0
        POLL_MIN = 0.1
        if ivl < POLL_MIN:
            self._session_log(sess, f"Write interval too low — clamped to {POLL_MIN}s.", "warn")
            ivl = POLL_MIN
        sess.write_poll_interval = ivl
        sess.write_polling = True
        sess.write_poll_stop.clear()
        self._session_log(sess, f"Continuous write started (every {ivl}s).", "info")
        self._update_write_poll_btn(sess)
        sess.write_poll_thread = threading.Thread(
            target=self._write_poll_loop, args=(sid,), daemon=True)
        sess.write_poll_thread.start()

    def _stop_write_poll(self, sid: str):
        sess = self.sessions.get(sid)
        if not sess:
            return
        sess.write_polling = False
        sess.write_poll_stop.set()
        self._session_log(sess, "Continuous write stopped.", "warn")
        if self.active_sid == sid:
            self.root.after(0, self._update_write_poll_btn, sess)

    def _write_poll_loop(self, sid: str):
        while True:
            sess = self.sessions.get(sid)
            if not sess or not sess.write_polling:
                break
            if sess.state == ST_CONNECTED:
                self.root.after(0, self._do_write, sid, True)   # True = suppress confirm
                ts = datetime.now().strftime("%H:%M:%S")
                sess.last_write_poll_ts = ts
                if self.active_sid == sid:
                    lbl = self._op_widgets.get("write_poll_last")
                    if lbl:
                        self.root.after(0, lbl.config, {"text": f"Last: {ts}"})
            sess.write_poll_stop.wait(sess.write_poll_interval)
            sess.write_poll_stop.clear()

    # ─── Format Converter ───────────────────────────────────────────────────────
    def _do_fmt(self, fmt: str):
        ci = self._op_widgets.get("conv_in")
        cr = self._op_widgets.get("conv_result")
        if not ci or not cr:
            return
        try:
            val = int(ci.get(), 0)
            if fmt == "hex":
                cr.config(text=f"0x{val:04X}  /  0x{val:08X} (32-bit)")
            elif fmt == "dec":
                s = val if val < 32768 else val - 65536
                cr.config(text=f"{val}  (signed: {s})")
            elif fmt == "bin":
                cr.config(text=f"{val:016b}  ({val:08b} 8-bit)")
        except ValueError:
            cr.config(text="Invalid input")

    # ─── Cleanup ────────────────────────────────────────────────────────────────
    def on_close(self):
        for sid in list(self.session_order):
            sess = self.sessions.get(sid)
            if sess and sess.write_polling:
                self._stop_write_poll(sid)
            self._session_disconnect(sid, quiet=True)
        self.root.destroy()


# ─── New / Edit Connection Dialog ──────────────────────────────────────────────
class NewConnectionDialog:
    """
    Modal dialog for adding or editing a Modbus connection session.
    Layout uses grid inside a plain Frame — no canvas, no scrollbar tricks.
    The window auto-sizes to its content after build.
    """

    def __init__(self, parent, existing: ConnectionSession = None):
        self.result: Optional[ConnectionSession] = None
        edit = existing is not None
        sess = existing or ConnectionSession()

        d = tk.Toplevel(parent)
        self.dialog = d
        d.title("Edit Connection" if edit else "New Connection")
        d.configure(bg=BG_DEEP)
        d.resizable(False, False)
        d.grab_set()
        d.transient(parent)

        # ── StringVars ──────────────────────────────────────────────────────────
        lbl_var  = tk.StringVar(value=sess.label)
        mode_var = tk.StringVar(value=sess.mode)
        host_var = tk.StringVar(value=sess.host)
        port_var = tk.StringVar(value=str(sess.port))
        to_var   = tk.StringVar(value=str(sess.timeout))
        sp_var   = tk.StringVar(value=sess.serial_port)
        baud_var = tk.StringVar(value=str(sess.baudrate))
        par_var  = tk.StringVar(value=sess.parity)
        sb_var   = tk.StringVar(value=str(sess.stopbits))
        db_var   = tk.StringVar(value=str(sess.bytesize))
        unit_var = tk.StringVar(value=str(sess.default_unit))

        # ── Header ──────────────────────────────────────────────────────────────
        hdr = tk.Frame(d, bg=BG_DEEP)
        hdr.pack(fill="x", padx=24, pady=(18, 0))
        tk.Label(hdr, text="Edit Connection" if edit else "New Connection",
                 bg=BG_DEEP, fg=AMBER, font=FONT_HEAD).pack(anchor="w")
        tk.Label(hdr, text="Configure endpoint and connection parameters.",
                 bg=BG_DEEP, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w")
        tk.Frame(d, bg=GRAY_DIM, height=1).pack(fill="x", pady=(12, 0))

        # ── Body ────────────────────────────────────────────────────────────────
        body = tk.Frame(d, bg=BG_CARD, padx=20, pady=14)
        body.pack(fill="both", expand=True, padx=20, pady=8)

        def row(parent, label, var, col_width=20):
            """One label + entry pair using grid."""
            r = parent.grid_size()[1]   # next available row
            tk.Label(parent, text=label, bg=BG_CARD, fg=TEXT_DIM,
                     font=FONT_LABEL, anchor="w", width=16
                     ).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 8))
            e = ttk.Entry(parent, textvariable=var, width=col_width)
            e.grid(row=r, column=1, sticky="ew", pady=4)
            parent.columnconfigure(1, weight=1)
            return e

        def combo_row(parent, label, var, values):
            r = parent.grid_size()[1]
            tk.Label(parent, text=label, bg=BG_CARD, fg=TEXT_DIM,
                     font=FONT_LABEL, anchor="w", width=16
                     ).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 8))
            cb = ttk.Combobox(parent, textvariable=var, values=values,
                               width=8, state="readonly")
            cb.grid(row=r, column=1, sticky="w", pady=4)

        def radio_row(parent, label, var, options):
            r = parent.grid_size()[1]
            tk.Label(parent, text=label, bg=BG_CARD, fg=TEXT_DIM,
                     font=FONT_LABEL, anchor="w", width=16
                     ).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 8))
            btn_frame = tk.Frame(parent, bg=BG_CARD)
            btn_frame.grid(row=r, column=1, sticky="w", pady=4)
            for val in options:
                tk.Radiobutton(btn_frame, text=val, variable=var, value=val,
                               bg=BG_CARD, fg=TEXT_DIM, selectcolor=BG_CARD,
                               activebackground=BG_CARD, activeforeground=AMBER,
                               indicatoron=0, relief="flat", padx=12, pady=3,
                               font=FONT_UI, cursor="hand2",
                               highlightthickness=0).pack(side="left", padx=(0, 4))

        def section(parent, title):
            """Labelled section frame using grid rows."""
            lf = tk.LabelFrame(parent, text=f" {title} ", bg=BG_CARD, fg=AMBER,
                                font=FONT_LABEL, bd=1, relief="groove",
                                highlightbackground=GRAY_DIM, padx=10, pady=6)
            r = parent.grid_size()[1]
            lf.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 2))
            parent.columnconfigure(0, weight=1)
            lf.columnconfigure(1, weight=1)
            return lf

        # Session label
        row(body, "Label", lbl_var)

        # Mode toggle
        radio_row(body, "Mode", mode_var, ["TCP", "RTU"])

        # ── TCP section ─────────────────────────────────────────────────────────
        tcp_sec = section(body, "TCP Settings")
        first_tcp = row(tcp_sec, "Host / IP", host_var)
        row(tcp_sec, "Port", port_var)
        row(tcp_sec, "Timeout (s)", to_var)

        # ── RTU section ─────────────────────────────────────────────────────────
        rtu_sec = section(body, "RTU / Serial Settings")
        row(rtu_sec, "Serial Port", sp_var)
        row(rtu_sec, "Baud Rate", baud_var)
        combo_row(rtu_sec, "Parity", par_var, ["N", "E", "O"])
        row(rtu_sec, "Stop Bits", sb_var)
        row(rtu_sec, "Byte Size", db_var)

        # Default unit (always shown)
        row(body, "Default Unit ID", unit_var)

        # ── Show/hide TCP vs RTU sections ────────────────────────────────────────
        def apply_mode(*_):
            if mode_var.get() == "TCP":
                tcp_sec.grid()
                rtu_sec.grid_remove()
                first_tcp.focus_set()
            else:
                rtu_sec.grid()
                tcp_sec.grid_remove()

        mode_var.trace_add("write", apply_mode)
        apply_mode()   # set initial state

        # ── Separator + Buttons ──────────────────────────────────────────────────
        tk.Frame(d, bg=GRAY_DIM, height=1).pack(fill="x", pady=(4, 0))

        btn_bar = tk.Frame(d, bg=BG_DEEP)
        btn_bar.pack(fill="x", padx=20, pady=14)

        def on_ok():
            new = ConnectionSession() if not edit else sess
            new.label = lbl_var.get().strip() or "Unnamed"
            new.mode  = mode_var.get()
            try:
                new.host         = host_var.get().strip()
                new.port         = int(port_var.get())
                new.timeout      = int(to_var.get())
                new.serial_port  = sp_var.get().strip()
                new.baudrate     = int(baud_var.get())
                new.parity       = par_var.get()
                new.stopbits     = int(sb_var.get())
                new.bytesize     = int(db_var.get())
                new.default_unit = int(unit_var.get())
            except ValueError as e:
                messagebox.showerror("Invalid Input", f"Please check your values:\n{e}", parent=d)
                return

            errors = []
            if new.mode == "TCP":
                if not new.host:
                    errors.append("Host / IP cannot be empty.")
                if not (1 <= new.port <= 65535):
                    errors.append(f"Port {new.port} out of range (1–65535).")
                if not (1 <= new.timeout <= 300):
                    errors.append(f"Timeout {new.timeout} out of range (1–300 s).")
            else:
                if not new.serial_port:
                    errors.append("Serial port cannot be empty.")
                if new.baudrate <= 0:
                    errors.append("Baud rate must be a positive integer.")
                if new.stopbits not in (1, 2):
                    errors.append("Stop bits must be 1 or 2.")
                if new.bytesize not in (5, 6, 7, 8):
                    errors.append("Byte size must be 5, 6, 7, or 8.")
                if new.parity not in ("N", "E", "O"):
                    errors.append("Parity must be N, E, or O.")
            if not (1 <= new.default_unit <= 247):
                errors.append(f"Unit ID {new.default_unit} out of range (1–247).")
            if errors:
                messagebox.showerror("Validation Error", "\n".join(errors), parent=d)
                return

            self.result = new
            d.destroy()

        tk.Button(btn_bar, text="Cancel",
                  bg=BG_PANEL, fg=TEXT_DIM,
                  activebackground=GRAY_DIM, activeforeground=TEXT_MAIN,
                  font=FONT_UI, relief="flat", padx=20, pady=7,
                  cursor="hand2", bd=0, command=d.destroy
                  ).pack(side="right", padx=(8, 0))

        tk.Button(btn_bar, text="Save" if edit else "Add Connection",
                  bg=AMBER_DIM, fg=AMBER_GLOW,
                  activebackground=AMBER, activeforeground=BG_DEEP,
                  font=FONT_UI_B, relief="flat", padx=20, pady=7,
                  cursor="hand2", bd=0, command=on_ok
                  ).pack(side="right")

        d.bind("<Return>", lambda e: on_ok())
        d.bind("<Escape>", lambda e: d.destroy())

        # ── Size and centre ──────────────────────────────────────────────────────
        d.update_idletasks()
        w = d.winfo_reqwidth()
        h = d.winfo_reqheight()
        px = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        d.geometry(f"{w}x{h}+{px}+{py}")


# ─── Entry Point ───────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.configure(bg=BG_DEEP)
    try:
        root.iconbitmap("")
    except Exception:
        pass

    app = ModbusMultiClient(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
