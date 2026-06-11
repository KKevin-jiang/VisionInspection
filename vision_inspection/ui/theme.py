from __future__ import annotations

from pathlib import Path

from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication


PREFERRED_UI_FONT_FAMILIES = [
    "Alibaba PuHuiTi 3.0",
    "Alibaba PuHuiTi 2.0",
    "Alibaba PuHuiTi",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Segoe UI",
]


def apply_app_font(app: QApplication, project_root: Path) -> None:
    _register_optional_fonts(project_root)

    available_families = {family.casefold(): family for family in QFontDatabase().families()}
    selected_family = next(
        (available_families[family.casefold()] for family in PREFERRED_UI_FONT_FAMILIES if family.casefold() in available_families),
        app.font().family(),
    )

    ui_font = QFont(selected_family)
    ui_font.setPointSize(10)
    ui_font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(ui_font)


def _register_optional_fonts(project_root: Path) -> None:
    candidate_dirs = [
        project_root / "assets" / "fonts",
        project_root.parent / "assets" / "fonts",
    ]

    for fonts_dir in candidate_dirs:
        if not fonts_dir.exists():
            continue

        for suffix in ("*.ttf", "*.otf", "*.ttc"):
            for font_path in fonts_dir.glob(suffix):
                QFontDatabase.addApplicationFont(str(font_path))