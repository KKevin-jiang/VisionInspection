from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from vision_inspection.application.controllers.plc_controller import PlcController


class PlcListenerWorker(QObject):
    status_changed = pyqtSignal(str)
    trigger_received = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, plc_controller: PlcController, poll_timeout_ms: int = 500) -> None:
        super().__init__()
        self._plc_controller = plc_controller
        self._poll_timeout_ms = poll_timeout_ms
        self._running = True

    @pyqtSlot()
    def run(self) -> None:
        self.status_changed.emit("PLC 监听中")
        try:
            while self._running:
                event = self._plc_controller.wait_for_trigger(timeout_ms=self._poll_timeout_ms)
                if not self._running:
                    break
                if event is not None:
                    self.trigger_received.emit(event.message)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def stop(self) -> None:
        self._running = False
