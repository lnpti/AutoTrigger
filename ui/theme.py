"""
Tema "console de broadcast" — tokens de design + folha QSS global.

Uso:
    from ui.theme import apply_theme, COLORS, FONTS
    apply_theme(app)
"""
from __future__ import annotations

# ── Tokens de cor ───────────────────────────────────────────────────────────────
COLORS = {
    "bg0":     "#07070d",   # fundo da aplicação
    "bg1":     "#0e0e1a",   # painéis
    "bg2":     "#161626",   # superfícies elevadas / hover
    "bg3":     "#1e1e32",   # inputs / cards selecionados
    "border":  "#232338",
    "border2": "#33334d",
    "text_hi": "#e8e8f5",
    "text_md": "#9a9ab5",
    "text_dim":"#5a5a78",
    "cyan":    "#00e5ff",   # acento primário
    "cyan_dk": "#0091a7",
    "green":   "#00e676",   # rodando / ok
    "green_dk":"#00a152",
    "warn":    "#ffb300",
    "error":   "#ff5370",
    "magenta": "#d264ff",
}

FONTS = {
    "ui":   "Segoe UI",
    "mono": "Cascadia Code, Consolas, monospace",
}

# Cores de estado (compatível com os nomes usados no engine/runner)
STATE_COLORS = {
    "idle":      COLORS["text_dim"],
    "running":   COLORS["green"],
    "done":      COLORS["cyan"],
    "error":     COLORS["error"],
    "cancelled": COLORS["warn"],
}

LEVEL_COLORS = {
    "info":    COLORS["text_hi"],
    "success": COLORS["green"],
    "warn":    COLORS["warn"],
    "error":   COLORS["error"],
}

# Ícones por tipo de etapa (emoji — renderizam bem no Windows 11)
STEP_ICONS = {
    "mute":          "🔇",
    "unmute":        "🔊",
    "open_channel":  "📻",
    "close_channel": "🔕",
    "hotkey":        "⌨",
    "play_audio":    "🎵",
    "stream":        "📡",
    "wait_time":     "⏳",
    "wait_keyword":  "🔍",
}


def _qss() -> str:
    c = COLORS
    return f"""
* {{
    font-family: "{FONTS['ui']}";
    font-size: 13px;
    color: {c['text_hi']};
    outline: none;
}}

QMainWindow, QWidget#root {{
    background-color: {c['bg0']};
}}

/* ── Painéis / cards ─────────────────────────────────────────────── */
QFrame#panel {{
    background-color: {c['bg1']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
QFrame#raised {{
    background-color: {c['bg2']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
QFrame#topbar {{
    background-color: {c['bg1']};
    border: none;
    border-bottom: 1px solid {c['border']};
}}
QFrame#sidebar {{
    background-color: {c['bg1']};
    border: none;
    border-right: 1px solid {c['border']};
}}

/* ── Labels utilitárias ──────────────────────────────────────────── */
QLabel#h1 {{ font-size: 18px; font-weight: 700; color: {c['cyan']}; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; color: {c['text_hi']}; }}
QLabel#section {{ font-size: 11px; font-weight: 700; color: {c['text_dim']};
                  letter-spacing: 1px; }}
QLabel#muted {{ color: {c['text_md']}; }}
QLabel#dim   {{ color: {c['text_dim']}; font-size: 11px; }}

/* ── Botões ──────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {c['bg2']};
    border: 1px solid {c['border2']};
    border-radius: 8px;
    padding: 7px 14px;
    color: {c['text_hi']};
}}
QPushButton:hover  {{ background-color: {c['bg3']}; border-color: {c['cyan_dk']}; }}
QPushButton:pressed{{ background-color: {c['border']}; }}
QPushButton:disabled {{ color: {c['text_dim']}; border-color: {c['border']}; }}

QPushButton#primary {{
    background-color: {c['cyan_dk']};
    border: 1px solid {c['cyan']};
    color: #03121a; font-weight: 700;
}}
QPushButton#primary:hover {{ background-color: {c['cyan']}; }}

QPushButton#success {{
    background-color: {c['green_dk']};
    border: 1px solid {c['green']};
    color: #02140a; font-weight: 700;
}}
QPushButton#success:hover {{ background-color: {c['green']}; }}

QPushButton#danger {{
    background-color: #5a1020;
    border: 1px solid {c['error']};
    color: {c['text_hi']};
}}
QPushButton#danger:hover {{ background-color: #7a1530; }}

QPushButton#ghost {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {c['text_md']};
    padding: 5px 8px;
}}
QPushButton#ghost:hover {{ color: {c['text_hi']}; border-color: {c['border2']}; }}

QPushButton#icon {{
    background-color: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 4px; min-width: 26px; max-width: 34px;
}}
QPushButton#icon:hover {{ background-color: {c['bg3']}; border-color: {c['border2']}; }}

QPushButton#icon_danger {{
    background-color: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 4px; min-width: 26px; max-width: 34px;
    color: {c['error']};
}}
QPushButton#icon_danger:hover {{ background-color: #5a1020; border-color: {c['error']}; }}

/* ── Inputs ──────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QDateEdit {{
    background-color: {c['bg0']};
    border: 1px solid {c['border2']};
    border-radius: 8px;
    padding: 6px 9px;
    color: {c['text_hi']};
    selection-background-color: {c['cyan_dk']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus,
QDateEdit:focus {{
    border: 1px solid {c['cyan']};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {c['bg2']};
    border: 1px solid {c['border2']};
    selection-background-color: {c['cyan_dk']};
    outline: none;
}}

/* ── Checkbox / radio ────────────────────────────────────────────── */
QCheckBox, QRadioButton {{ spacing: 7px; color: {c['text_md']}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {c['border2']};
    background: {c['bg0']};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {c['cyan']}; border-color: {c['cyan']};
}}

/* ── ScrollArea / scrollbars ─────────────────────────────────────── */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {c['border2']}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['text_dim']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {c['border2']}; border-radius: 5px; min-width: 30px;
}}

/* ── Log mono ────────────────────────────────────────────────────── */
QPlainTextEdit#log {{
    font-family: "{FONTS['mono']}"; font-size: 12px;
    background-color: {c['bg0']};
    border: 1px solid {c['border']};
}}

/* ── Tooltip ─────────────────────────────────────────────────────── */
QToolTip {{
    background: {c['bg2']}; color: {c['text_hi']};
    border: 1px solid {c['cyan_dk']}; padding: 4px 6px;
}}
"""


def _apply_dark_palette(app):
    """
    Paleta dark base (estilo Fusion) — garante que TODO widget tenha fundo escuro,
    inclusive containers genéricos que o QSS '*' não cobre. O QSS por cima adiciona
    os acentos neon.
    """
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtCore import Qt

    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    c = COLORS
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg0"]))
    pal.setColor(QPalette.WindowText, QColor(c["text_hi"]))
    pal.setColor(QPalette.Base, QColor(c["bg0"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["bg1"]))
    pal.setColor(QPalette.Text, QColor(c["text_hi"]))
    pal.setColor(QPalette.Button, QColor(c["bg2"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text_hi"]))
    pal.setColor(QPalette.ToolTipBase, QColor(c["bg2"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text_hi"]))
    pal.setColor(QPalette.Highlight, QColor(c["cyan_dk"]))
    pal.setColor(QPalette.HighlightedText, QColor("#03121a"))
    pal.setColor(QPalette.PlaceholderText, QColor(c["text_dim"]))
    pal.setColor(QPalette.Link, QColor(c["cyan"]))
    # estados desabilitados
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(c["text_dim"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(c["text_dim"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["text_dim"]))
    app.setPalette(pal)


def apply_theme(app):
    """Aplica paleta dark (Fusion) + folha QSS global."""
    _apply_dark_palette(app)
    app.setStyleSheet(_qss())
