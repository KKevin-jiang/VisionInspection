from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class HistoryRecordsDialog(QDialog):
    def __init__(self, record_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._record_root = record_root
        self._records: list[dict] = []
        self._current_pixmap: QPixmap | None = None

        self.setWindowTitle("历史记录")
        self.resize(1240, 760)

        self.path_label = QLabel(str(record_root))
        self.path_label.setWordWrap(True)
        self.summary_label = QLabel("-")
        self.summary_label.setWordWrap(True)
        self.preview_label = QLabel("暂无预览")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(420, 320)
        self.preview_label.setStyleSheet("background: #0f172a; color: #cbd5e1; border-radius: 10px;")
        self.error_label = QLabel("-")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b91c1c;")

        self.refresh_button = QPushButton("刷新")
        self.open_folder_button = QPushButton("打开目录")

        self.records_table = QTableWidget(0, 6)
        self.records_table.setHorizontalHeaderLabels(["时间", "结果", "配方", "模板", "触发", "记录ID"])
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.records_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.records_table.setSelectionMode(QTableWidget.SingleSelection)
        self.records_table.setAlternatingRowColors(True)
        self.records_table.horizontalHeader().setStretchLastSection(True)

        self._apply_style()
        self._build_layout()
        self._bind_events()
        self._load_records()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            "QDialog { background: #eef1f5; }"
            "QFrame#Card { background: #ffffff; border: 1px solid #dde5ef; border-radius: 12px; }"
            "QLabel { color: #111827; }"
            "QPushButton { min-height: 32px; padding: 0 12px; border: 1px solid #d4dce7; border-radius: 6px; background: #f9fbfd; }"
            "QPushButton:hover { background: #f0f5fa; }"
            "QTableWidget { border: 1px solid #e2e8f0; border-radius: 8px; background: #ffffff; alternate-background-color: #f8fafc; }"
        )

    def _build_layout(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        header_card = QFrame(self)
        header_card.setObjectName("Card")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.addWidget(QLabel("记录目录："))
        header_layout.addWidget(self.path_label, 1)
        header_layout.addWidget(self.refresh_button)
        header_layout.addWidget(self.open_folder_button)

        splitter = QSplitter(Qt.Horizontal)

        table_card = QFrame(self)
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(12, 12, 12, 12)
        title_label = QLabel("检测记录列表")
        title_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        table_layout.addWidget(title_label)
        table_layout.addWidget(self.records_table)

        detail_card = QFrame(self)
        detail_card.setObjectName("Card")
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(10)
        detail_title = QLabel("记录详情")
        detail_title.setStyleSheet("font-size: 15px; font-weight: 700;")

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(8)
        info_grid.setVerticalSpacing(6)
        info_grid.addWidget(QLabel("摘要"), 0, 0)
        info_grid.addWidget(self.summary_label, 0, 1)
        info_grid.addWidget(QLabel("异常"), 1, 0)
        info_grid.addWidget(self.error_label, 1, 1)

        detail_layout.addWidget(detail_title)
        detail_layout.addLayout(info_grid)
        detail_layout.addWidget(self.preview_label, 1)

        splitter.addWidget(table_card)
        splitter.addWidget(detail_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root_layout.addWidget(header_card)
        root_layout.addWidget(splitter, 1)

    def _bind_events(self) -> None:
        self.refresh_button.clicked.connect(self._load_records)
        self.open_folder_button.clicked.connect(self._open_folder)
        self.records_table.itemSelectionChanged.connect(self._show_selected_record)

    def _load_records(self) -> None:
        self.records_table.setRowCount(0)
        self._records.clear()
        self.summary_label.setText("-")
        self.error_label.setText("-")
        self.preview_label.setText("暂无预览")
        self.preview_label.setPixmap(QPixmap())
        self._current_pixmap = None

        if not self._record_root.exists():
            self.summary_label.setText("记录目录不存在")
            return

        json_files = sorted(self._record_root.rglob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for json_file in json_files:
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if "record_id" not in payload:
                continue

            storage = payload.get("storage") or {}
            raw_path = self._resolve_path(storage.get("raw_image_path"))
            result_path = self._resolve_path(storage.get("result_image_path"))
            self._records.append(
                {
                    "json_path": json_file,
                    "timestamp": payload.get("timestamp", "-"),
                    "overall_result": payload.get("overall_result", "-"),
                    "recipe_name": payload.get("recipe_name", "-"),
                    "template_name": payload.get("template_name", "-"),
                    "trigger_source": payload.get("trigger_source", "-"),
                    "record_id": payload.get("record_id", json_file.stem),
                    "overall_score": payload.get("overall_score"),
                    "error_message": payload.get("error_message") or "-",
                    "raw_image_path": raw_path,
                    "result_image_path": result_path,
                    "status": payload.get("status", "-"),
                }
            )

        self.records_table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            values = [
                str(record["timestamp"]).replace("T", " ")[:19],
                record["overall_result"],
                record["recipe_name"],
                record["template_name"],
                record["trigger_source"],
                record["record_id"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    if record["overall_result"] == "OK":
                        item.setForeground(Qt.darkGreen)
                    elif record["overall_result"] in {"NG", "FAILED"}:
                        item.setForeground(Qt.red)
                self.records_table.setItem(row, column, item)

        if self._records:
            self.records_table.selectRow(0)

    def _show_selected_record(self) -> None:
        row = self.records_table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        record = self._records[row]
        score_text = "-" if record["overall_score"] is None else f"{record['overall_score']:.4f}"
        self.summary_label.setText(
            f"结果 {record['overall_result']} | 状态 {record['status']} | 分值 {score_text} | 触发 {record['trigger_source']}"
        )
        self.error_label.setText(record["error_message"])

        image_path = record["result_image_path"] if record["result_image_path"] and record["result_image_path"].exists() else record["raw_image_path"]
        if image_path is None or not image_path.exists():
            self.preview_label.setText("该记录没有可预览图像")
            self.preview_label.setPixmap(QPixmap())
            self._current_pixmap = None
            return

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.preview_label.setText("图像预览加载失败")
            self.preview_label.setPixmap(QPixmap())
            self._current_pixmap = None
            return

        self._current_pixmap = pixmap
        self._update_preview_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_preview_pixmap()

    def _update_preview_pixmap(self) -> None:
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return
        scaled = self._current_pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)

    def _resolve_path(self, path_text: str | None) -> Path | None:
        if not path_text:
            return None
        path = Path(path_text)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    def _open_folder(self) -> None:
        row = self.records_table.currentRow()
        target = self._record_root
        if 0 <= row < len(self._records):
            target = self._records[row]["json_path"].parent
        if not target.exists():
            QMessageBox.warning(self, "打开失败", "记录目录不存在")
            return
        os.startfile(str(target))