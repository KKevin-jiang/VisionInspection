from __future__ import annotations

from vision_inspection.application.services.inspection_workflow_service import InspectionExecutionResult, InspectionWorkflowService, SaveResultSnapshot
from vision_inspection.domain.models.recipe import RecipeDocument


class InspectionWorkflowController:
    def __init__(self, inspection_workflow_service: InspectionWorkflowService) -> None:
        self._inspection_workflow_service = inspection_workflow_service

    def execute_inspection(
        self,
        recipe_document: RecipeDocument,
        trigger_source: str = "manual",
        preferred_device_index: int = 0,
    ) -> InspectionExecutionResult:
        return self._inspection_workflow_service.execute_inspection(
            recipe_document=recipe_document,
            trigger_source=trigger_source,
            preferred_device_index=preferred_device_index,
        )

    def execute_manual_inspection(
        self,
        recipe_document: RecipeDocument,
        preferred_device_index: int = 0,
    ) -> InspectionExecutionResult:
        return self._inspection_workflow_service.execute_manual_inspection(
            recipe_document=recipe_document,
            preferred_device_index=preferred_device_index,
        )

    @property
    def save_health(self) -> dict:
        """返回保存健康状态，供 UI 轮询显示。"""
        return self._inspection_workflow_service.save_health

    def shutdown(self, timeout_seconds: float = 5.0) -> None:
        """等待后台保存完成并关闭线程池。应在应用退出前调用。"""
        self._inspection_workflow_service.shutdown(timeout_seconds)

    def drain_save_results(self) -> list:
        """取出并清空最近的保存结果快照，供 UI 轮询消费。"""
        return self._inspection_workflow_service.drain_save_results()
