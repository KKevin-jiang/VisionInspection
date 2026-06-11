from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QLabel, QToolTip


class ImageCanvas(QLabel):
    roi_rects_changed = pyqtSignal(list)
    roi_selected = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._roi_rects = []
        self._pixmap = None
        self._image_array = None
        self._image_width = 0
        self._image_height = 0
        self._editable = False
        self._selected_roi_index = -1
        self._drawing = False
        self._draw_start = None
        self._draw_current = None
        self._fit_to_window = True
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self._dragging_view = False
        self._drag_last_pos = QPoint()
        self._hovered_roi_index = -1
        self._placeholder_text = "图像显示区\n点击手动测试后显示采集图像"
        self.setMinimumSize(640, 480)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #1f2937; color: #d1d5db; border: 1px solid #374151;")

    def set_image_array(self, image: np.ndarray) -> None:
        self._image_array = image.copy()
        if image.ndim == 2:
            height, width = image.shape
            qimage = QImage(image.data, width, height, image.strides[0], QImage.Format_Grayscale8).copy()
        elif image.ndim == 3 and image.shape[2] == 3:
            height, width, _ = image.shape
            rgb_image = image[:, :, ::-1].copy()
            qimage = QImage(rgb_image.data, width, height, rgb_image.strides[0], QImage.Format_RGB888).copy()
        else:
            raise ValueError("unsupported image format for display")

        self._pixmap = QPixmap.fromImage(qimage)
        self._image_width = qimage.width()
        self._image_height = qimage.height()
        self._fit_to_window = True
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self.update()

    def clear_image(self) -> None:
        self._pixmap = None
        self._image_array = None
        self._image_width = 0
        self._image_height = 0
        self._selected_roi_index = -1
        self._hovered_roi_index = -1
        self._pan_offset = QPoint(0, 0)
        self.update()

    def set_roi_rects(self, roi_rects) -> None:
        self._roi_rects = list(roi_rects)
        if self._selected_roi_index >= len(self._roi_rects):
            self._selected_roi_index = -1
        self.update()

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self.setCursor(Qt.CrossCursor if editable else Qt.ArrowCursor)

    def set_placeholder_text(self, text: str) -> None:
        self._placeholder_text = text
        self.update()

    def set_selected_roi_index(self, index: int) -> None:
        self._selected_roi_index = index if 0 <= index < len(self._roi_rects) else -1
        self.update()

    def remove_selected_roi(self) -> None:
        if 0 <= self._selected_roi_index < len(self._roi_rects):
            del self._roi_rects[self._selected_roi_index]
            self._selected_roi_index = -1
            self.roi_rects_changed.emit(list(self._roi_rects))
            self.update()

    def get_image_array(self):
        return None if self._image_array is None else self._image_array.copy()

    def get_roi_rects(self):
        return [dict(item) for item in self._roi_rects]

    def fit_to_window(self) -> None:
        self._fit_to_window = True
        self._pan_offset = QPoint(0, 0)
        self.update()

    def show_original_size(self) -> None:
        self._fit_to_window = False
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self.update()

    def zoom_in(self) -> None:
        self._fit_to_window = False
        self._zoom_factor = min(8.0, self._zoom_factor * 1.2)
        self._clamp_pan_offset()
        self.update()

    def zoom_out(self) -> None:
        self._fit_to_window = False
        self._zoom_factor = max(0.2, self._zoom_factor / 1.2)
        self._clamp_pan_offset()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1f2937"))

        target_rect = self._calculate_target_rect()
        if self._pixmap is not None and not self._pixmap.isNull():
            offset_x, offset_y, draw_width, draw_height = target_rect
            painter.drawPixmap(offset_x, offset_y, draw_width, draw_height, self._pixmap)
        else:
            painter.setPen(QColor("#d1d5db"))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder_text)

        if not self._roi_rects or target_rect is None:
            if self._drawing and target_rect is not None:
                self._draw_draft_rect(painter, target_rect)
            return

        painter.setRenderHint(QPainter.Antialiasing)
        offset_x, offset_y, draw_width, draw_height = target_rect
        for index, roi in enumerate(self._roi_rects):
            color = QColor(roi.get("color", "#22c55e"))
            pen_width = 3 if index == self._selected_roi_index else 2
            painter.setPen(QPen(color, pen_width))
            x = int(offset_x + roi["x"] * draw_width / max(1, self._image_width))
            y = int(offset_y + roi["y"] * draw_height / max(1, self._image_height))
            width = int(roi["width"] * draw_width / max(1, self._image_width))
            height = int(roi["height"] * draw_height / max(1, self._image_height))
            painter.drawRect(x, y, width, height)
            painter.drawText(x, max(y - 6, 12), roi["name"])

        if self._drawing:
            self._draw_draft_rect(painter, target_rect)

    def mousePressEvent(self, event) -> None:
        if not self._editable and event.button() == Qt.LeftButton and self._pixmap is not None and not self._fit_to_window:
            self._dragging_view = True
            self._drag_last_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if not self._editable or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        image_pos = self._widget_to_image_pos(event.pos())
        if image_pos is None:
            return

        hit_index = self._find_roi_at(image_pos)
        if hit_index >= 0:
            self._selected_roi_index = hit_index
            self.roi_selected.emit(hit_index)
            self.update()
            return

        self._drawing = True
        self._draw_start = image_pos
        self._draw_current = image_pos
        self._selected_roi_index = -1
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging_view and not self._editable:
            delta = event.pos() - self._drag_last_pos
            self._drag_last_pos = event.pos()
            self._pan_offset += delta
            self._clamp_pan_offset()
            self.update()
            return

        if not self._editable:
            self._update_hover_tooltip(event.pos(), event.globalPos())
            return super().mouseMoveEvent(event)

        if not self._drawing:
            return super().mouseMoveEvent(event)

        image_pos = self._widget_to_image_pos(event.pos())
        if image_pos is None:
            return
        self._draw_current = image_pos
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging_view and event.button() == Qt.LeftButton:
            self._dragging_view = False
            self.setCursor(Qt.ArrowCursor)
            return

        if not self._editable or event.button() != Qt.LeftButton or not self._drawing:
            return super().mouseReleaseEvent(event)

        image_pos = self._widget_to_image_pos(event.pos())
        if image_pos is not None:
            self._draw_current = image_pos
        rect = self._normalized_rect(self._draw_start, self._draw_current)
        self._drawing = False
        self._draw_start = None
        self._draw_current = None

        if rect is None:
            self.update()
            return

        if rect["width"] < 5 or rect["height"] < 5:
            self.update()
            return

        roi_index = len(self._roi_rects) + 1
        self._roi_rects.append(
            {
                "name": f"ROI {roi_index}",
                "x": rect["x"],
                "y": rect["y"],
                "width": rect["width"],
                "height": rect["height"],
                "color": "#22c55e",
            }
        )
        self._selected_roi_index = len(self._roi_rects) - 1
        self.roi_rects_changed.emit(list(self._roi_rects))
        self.roi_selected.emit(self._selected_roi_index)
        self.update()

    def wheelEvent(self, event) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return super().wheelEvent(event)

        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()

    def _calculate_target_rect(self):
        if self._pixmap is None or self._pixmap.isNull() or self._image_width <= 0 or self._image_height <= 0:
            return None
        available_width = max(1, self.width() - 20)
        available_height = max(1, self.height() - 20)
        if self._fit_to_window:
            scale = min(available_width / self._image_width, available_height / self._image_height)
        else:
            scale = self._zoom_factor
        draw_width = int(self._image_width * scale)
        draw_height = int(self._image_height * scale)
        offset_x = (self.width() - draw_width) // 2
        offset_y = (self.height() - draw_height) // 2
        if not self._fit_to_window:
            offset_x += self._pan_offset.x()
            offset_y += self._pan_offset.y()
        return (offset_x, offset_y, draw_width, draw_height)

    def _clamp_pan_offset(self) -> None:
        target_rect = self._calculate_target_rect_without_pan()
        if target_rect is None:
            self._pan_offset = QPoint(0, 0)
            return
        _, _, draw_width, draw_height = target_rect
        max_x = max(0, (draw_width - self.width()) // 2 + 10)
        max_y = max(0, (draw_height - self.height()) // 2 + 10)
        self._pan_offset.setX(max(-max_x, min(max_x, self._pan_offset.x())))
        self._pan_offset.setY(max(-max_y, min(max_y, self._pan_offset.y())))

    def _calculate_target_rect_without_pan(self):
        if self._pixmap is None or self._pixmap.isNull() or self._image_width <= 0 or self._image_height <= 0:
            return None
        available_width = max(1, self.width() - 20)
        available_height = max(1, self.height() - 20)
        if self._fit_to_window:
            scale = min(available_width / self._image_width, available_height / self._image_height)
        else:
            scale = self._zoom_factor
        draw_width = int(self._image_width * scale)
        draw_height = int(self._image_height * scale)
        offset_x = (self.width() - draw_width) // 2
        offset_y = (self.height() - draw_height) // 2
        return (offset_x, offset_y, draw_width, draw_height)

    def _update_hover_tooltip(self, widget_pos: QPoint, global_pos: QPoint) -> None:
        image_pos = self._widget_to_image_pos(widget_pos)
        if image_pos is None:
            self._hovered_roi_index = -1
            QToolTip.hideText()
            return

        hit_index = self._find_roi_at(image_pos)
        if hit_index < 0:
            if self._hovered_roi_index != -1:
                QToolTip.hideText()
            self._hovered_roi_index = -1
            return

        if hit_index == self._hovered_roi_index:
            return

        self._hovered_roi_index = hit_index
        roi = self._roi_rects[hit_index]
        tooltip = roi.get("tooltip") or roi.get("name", "ROI")
        QToolTip.showText(global_pos, tooltip, self)

    def _widget_to_image_pos(self, pos: QPoint):
        target_rect = self._calculate_target_rect()
        if target_rect is None:
            return None
        offset_x, offset_y, draw_width, draw_height = target_rect
        if not (offset_x <= pos.x() <= offset_x + draw_width and offset_y <= pos.y() <= offset_y + draw_height):
            return None
        image_x = int((pos.x() - offset_x) * self._image_width / max(1, draw_width))
        image_y = int((pos.y() - offset_y) * self._image_height / max(1, draw_height))
        image_x = max(0, min(self._image_width - 1, image_x))
        image_y = max(0, min(self._image_height - 1, image_y))
        return (image_x, image_y)

    def _normalized_rect(self, start, end):
        if start is None or end is None:
            return None
        x1, y1 = start
        x2, y2 = end
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        return {"x": left, "y": top, "width": right - left, "height": bottom - top}

    def _find_roi_at(self, image_pos) -> int:
        image_x, image_y = image_pos
        for index, roi in enumerate(self._roi_rects):
            if roi["x"] <= image_x <= roi["x"] + roi["width"] and roi["y"] <= image_y <= roi["y"] + roi["height"]:
                return index
        return -1

    def _draw_draft_rect(self, painter: QPainter, target_rect) -> None:
        rect = self._normalized_rect(self._draw_start, self._draw_current)
        if rect is None:
            return
        offset_x, offset_y, draw_width, draw_height = target_rect
        painter.setPen(QPen(QColor("#f59e0b"), 2, Qt.DashLine))
        x = int(offset_x + rect["x"] * draw_width / max(1, self._image_width))
        y = int(offset_y + rect["y"] * draw_height / max(1, self._image_height))
        width = int(rect["width"] * draw_width / max(1, self._image_width))
        height = int(rect["height"] * draw_height / max(1, self._image_height))
        painter.drawRect(x, y, width, height)
