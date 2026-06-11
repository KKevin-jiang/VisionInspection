from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from vision_inspection.application.controllers.inspection_workflow_controller import InspectionWorkflowController
from vision_inspection.application.services.inspection_workflow_service import (
    InspectionExecutionResult,
    InspectionWorkflowTriggerTimeoutError,
)
from vision_inspection.domain.models.recipe import RecipeDocument


class InspectionWorker(QObject):
    started = pyqtSignal(str)
    finished = pyqtSignal(object)
    timed_out = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        workflow_controller: InspectionWorkflowController,
        recipe_document: RecipeDocument,
        trigger_source: str = "manual",
        preferred_device_index: int = 0,
    ) -> None:
        super().__init__()
        self._workflow_controller = workflow_controller
        self._recipe_document = recipe_document
        self._trigger_source = trigger_source
        self._preferred_device_index = preferred_device_index

    @pyqtSlot()
    def run(self) -> None:
        if self._trigger_source == "plc":
            self.started.emit("正在执行 PLC 触发采图与检测...")
        elif self._trigger_source == "io":
            self.started.emit("正在等待相机 Line0 外部触发...")
        else:
            self.started.emit("正在执行手动采图与检测...")
        try:
            result = self._workflow_controller.execute_inspection(
                recipe_document=self._recipe_document,
                trigger_source=self._trigger_source,
                preferred_device_index=self._preferred_device_index,
            )
        except InspectionWorkflowTriggerTimeoutError as exc:
            self.timed_out.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
