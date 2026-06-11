from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem


class RoiResultTable(QTableWidget):
    HEADERS = ["序号", "ROI 名称", "阈值", "分值", "算法", "状态"]
    ALGORITHM_LABELS = {
        "binary_gray_ratio": "二值化灰度面积比",
        "ssim": "结构相似度",
        "ai_classifier": "AI 分类器",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setShowGrid(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        body_font = QFont(self.font())
        body_font.setPointSize(10)
        self.setFont(body_font)

        header_font = QFont(body_font)
        header_font.setPointSize(10)
        header_font.setBold(True)
        self.horizontalHeader().setFont(header_font)

    def set_roi_items(self, roi_items) -> None:
        self.setRowCount(len(roi_items))
        for row_index, roi in enumerate(roi_items):
            values = [
                str(roi.index),
                roi.name,
                f"{roi.threshold:.2f}",
                "-",
                self.algorithm_label(roi.algorithm),
                "启用" if roi.enabled else "禁用",
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                self._style_item(item, column_index)
                self.setItem(row_index, column_index, item)
        self.resizeColumnsToContents()

    def set_result_items(self, roi_results) -> None:
        self.setRowCount(len(roi_results))
        for row_index, result in enumerate(roi_results):
            primary_algorithm = self.algorithm_label(result.algorithm)
            parallel_algorithm = self.algorithm_label(result.parallel_algorithm)
            values = [
                str(result.index),
                result.roi_name,
                f"{result.threshold:.2f}",
                "-" if result.score is None else f"{result.score:.3f}",
                primary_algorithm if not result.parallel_algorithm else f"{primary_algorithm} | {parallel_algorithm}",
                "OK" if result.passed else "NG",
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if result.enabled and not result.passed:
                    item.setBackground(QColor("#fecaca"))
                elif result.enabled and result.passed:
                    item.setBackground(QColor("#dcfce7"))
                self._style_item(item, column_index)
                self.setItem(row_index, column_index, item)
        self.resizeColumnsToContents()

    def _style_item(self, item: QTableWidgetItem, column_index: int) -> None:
        if column_index in {0, 2, 3, 5}:
            item.setTextAlignment(Qt.AlignCenter)

        item_font = QFont(self.font())
        if column_index in {3, 5}:
            item_font.setBold(True)
        item.setFont(item_font)

    @classmethod
    def algorithm_label(cls, algorithm: str | None) -> str:
        if not algorithm:
            return "-"
        return cls.ALGORITHM_LABELS.get(str(algorithm).strip().lower(), str(algorithm))
