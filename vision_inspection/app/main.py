from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from vision_inspection.app.config import load_app_config
from vision_inspection.utils.logger import setup_logger

# 初始化日志：同时输出到控制台 (stderr) 和配置的日志目录
_project_root = Path(__file__).resolve().parents[1]
_app_config = load_app_config(_project_root)
setup_logger("vision_inspection", log_dir=_app_config.storage.log_root)

from PyQt5.QtWidgets import QApplication

from vision_inspection.app.bootstrap import build_container
from vision_inspection.ui.main_window import MainWindow
from vision_inspection.ui.theme import apply_app_font


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    container = build_container(project_root)

    app = QApplication(sys.argv)
    apply_app_font(app, project_root)
    window = MainWindow(
        container.recipe_controller,
        container.camera_controller,
        container.inspection_controller,
        container.inspection_workflow_controller,
        container.plc_controller,
    )
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
