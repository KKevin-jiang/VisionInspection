from __future__ import annotations

import logging
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter

from vision_inspection.application.services.camera_service import (
    CameraCapture,
    CameraService,
    CameraServiceError,
    CameraTriggerTimeoutError,
)
from vision_inspection.application.services.inspection_service import InspectionService
from vision_inspection.application.services.plc_service import PlcService, PlcServiceError
from vision_inspection.application.services.record_service import RecordService, RecordServiceError
from vision_inspection.domain.models.inspection_result import InspectionResult
from vision_inspection.domain.models.recipe import RecipeDocument
from vision_inspection.infrastructure.storage import InspectionRecordSaveResult

logger = logging.getLogger(__name__)


@dataclass
class InspectionExecutionResult:
    capture: CameraCapture
    inspection_result: InspectionResult
    trigger_source: str
    save_result: InspectionRecordSaveResult | None = None
    save_message: str = ""
    plc_output_sent: bool = False
    plc_output_message: str = ""
    phase_metrics: dict[str, float] | None = None


@dataclass
class SaveResultSnapshot:
    """供 UI 轮询的保存结果快照，线程安全。"""
    status: str  # "ok" | "error"
    record_dir: str = ""
    record_id: str = ""
    error_message: str = ""


class InspectionWorkflowError(RuntimeError):
    pass


class InspectionWorkflowTriggerTimeoutError(InspectionWorkflowError):
    pass


class InspectionWorkflowService:
    def __init__(
        self,
        camera_service: CameraService,
        inspection_service: InspectionService,
        record_service: RecordService | None = None,
        plc_service: PlcService | None = None,
    ) -> None:
        self._camera_service = camera_service
        self._inspection_service = inspection_service
        self._record_service = record_service
        self._plc_service = plc_service
        self._save_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="record-save")
        self._pending_save_futures: set[Future] = set()
        # --- 保存健康状态追踪 ---
        self._save_stats_lock = Lock()
        self._consecutive_save_failures = 0
        self._total_save_failures = 0
        self._total_save_successes = 0
        self._last_save_error = ""
        # 最近的保存结果队列（供 UI 轮询消费）
        self._save_result_queue: deque[SaveResultSnapshot] = deque(maxlen=50)

    def execute_inspection(
        self,
        recipe_document: RecipeDocument,
        trigger_source: str = "manual",
        preferred_device_index: int = 0,
    ) -> InspectionExecutionResult:
        workflow_started_at = perf_counter()
        try:
            capture_started_at = perf_counter()
            capture = self._camera_service.capture_frame(
                trigger_mode=self._resolve_capture_mode(recipe_document, trigger_source),
                preferred_device_index=preferred_device_index,
                timeout_ms=500 if trigger_source == "io" else None,
            )
            capture_ms = (perf_counter() - capture_started_at) * 1000.0
        except CameraTriggerTimeoutError as exc:
            raise InspectionWorkflowTriggerTimeoutError(str(exc)) from exc
        except Exception as exc:
            self._raise_with_failure_record(
                recipe_document=recipe_document,
                trigger_source=trigger_source,
                failure_stage="capture",
                failure_message=str(exc),
            )

        try:
            inspect_started_at = perf_counter()
            inspection_result = self._inspection_service.inspect_image(recipe_document, capture.frame.image)
            inspect_ms = (perf_counter() - inspect_started_at) * 1000.0
        except Exception as exc:
            self._raise_with_failure_record(
                recipe_document=recipe_document,
                trigger_source=trigger_source,
                failure_stage="inspection",
                failure_message=str(exc),
                capture=capture,
            )

        save_result = None
        save_message = ""
        plc_output_sent = False
        plc_output_message = ""
        plc_ms = 0.0

        save_result, save_message = self._save_result_async(
            recipe_document=recipe_document,
            capture=capture,
            inspection_result=inspection_result,
            trigger_source=trigger_source,
        )

        if trigger_source in {"plc", "io", "manual"}:
            plc_started_at = perf_counter()
            plc_output_sent, plc_output_message = self._handle_plc_result(recipe_document, inspection_result)
            plc_ms = (perf_counter() - plc_started_at) * 1000.0

        phase_metrics = dict(inspection_result.phase_metrics)
        phase_metrics.update(
            {
                "capture_ms": capture_ms,
                "inspect_ms": inspect_ms,
                "plc_ms": plc_ms,
                "total_ms": (perf_counter() - workflow_started_at) * 1000.0,
            }
        )
        inspection_result.phase_metrics = phase_metrics

        return InspectionExecutionResult(
            capture=capture,
            inspection_result=inspection_result,
            trigger_source=trigger_source,
            save_result=save_result,
            save_message=save_message,
            plc_output_sent=plc_output_sent,
            plc_output_message=plc_output_message,
            phase_metrics=phase_metrics,
        )

    def _raise_with_failure_record(
        self,
        recipe_document: RecipeDocument,
        trigger_source: str,
        failure_stage: str,
        failure_message: str,
        capture: CameraCapture | None = None,
        inspection_result: InspectionResult | None = None,
    ) -> None:
        save_result = None
        save_message = ""
        if self._record_service is None:
            save_message = "未配置失败记录保存服务"
        else:
            try:
                save_result = self._record_service.save_failure_record(
                    recipe_document=recipe_document,
                    trigger_source=trigger_source,
                    failure_stage=failure_stage,
                    failure_message=failure_message,
                    capture=capture,
                    inspection_result=inspection_result,
                )
                save_message = f"失败记录已保存: {save_result.record_dir}"
            except RecordServiceError as exc:
                save_message = f"失败记录保存失败: {exc}"

        raise InspectionWorkflowError(f"{failure_stage} 失败: {failure_message}; {save_message}")

    def execute_manual_inspection(
        self,
        recipe_document: RecipeDocument,
        preferred_device_index: int = 0,
    ) -> InspectionExecutionResult:
        return self.execute_inspection(
            recipe_document=recipe_document,
            trigger_source="manual",
            preferred_device_index=preferred_device_index,
        )

    def _handle_plc_result(
        self,
        recipe_document: RecipeDocument,
        inspection_result: InspectionResult,
    ) -> tuple[bool, str]:
        plc_config = recipe_document.recipe.plc
        if not plc_config.enabled:
            return False, "配方未启用 PLC，未输出信号"

        if recipe_document.recipe.trigger_mode == "plc_external":
            if inspection_result.overall_result == "OK":
                try:
                    output_message = self._camera_service.emit_pass_output(
                        preferred_device_index=0,
                        channel=plc_config.ng_output.channel or "Line1",
                        delay_ms=plc_config.ng_output.delay_ms,
                    )
                except CameraServiceError as exc:
                    return False, f"相机 IO OK 输出失败: {exc}"
                return True, output_message
            else:
                return False, "检测结果为 NG，Line1 保持低电平"

        if inspection_result.overall_result == "OK":
            return False, "检测结果为 OK，未输出 NG 信号"

        if not plc_config.ng_output.enabled:
            return False, "配方未启用 NG 输出"

        if self._plc_service is None:
            return False, "PLC 服务未配置，未输出 NG 信号"

        try:
            output_result = self._plc_service.emit_ng_output(
                signal_name=plc_config.ng_output.signal_name,
                channel=plc_config.ng_output.channel,
                pulse_ms=plc_config.ng_output.pulse_ms,
                delay_ms=plc_config.ng_output.delay_ms,
                reset_mode=plc_config.ng_output.reset_mode,
            )
        except PlcServiceError as exc:
            return False, f"NG 输出失败: {exc}"

        return True, output_result.message

    def _resolve_capture_mode(self, recipe_document: RecipeDocument, trigger_source: str) -> str:
        if trigger_source == "manual":
            return "manual"
        if trigger_source == "software":
            return "software_trigger"
        if recipe_document.recipe.trigger_mode == "software_trigger":
            return "software_trigger"
        if recipe_document.recipe.trigger_mode == "plc_external":
            return "plc_external"
        return "manual"

    def _save_result_async(
        self,
        recipe_document: RecipeDocument,
        capture: CameraCapture,
        inspection_result: InspectionResult,
        trigger_source: str,
    ) -> tuple[InspectionRecordSaveResult | None, str]:
        if self._record_service is None:
            return None, "未配置结果保存服务"

        # 检查最近的保存失败，如果有则警告用户
        with self._save_stats_lock:
            recent_errors = self._consecutive_save_failures

        future = self._save_executor.submit(
            self._record_service.save_inspection_record,
            recipe_document=recipe_document,
            capture=capture,
            inspection_result=inspection_result,
            trigger_source=trigger_source,
        )
        self._pending_save_futures.add(future)
        future.add_done_callback(self._on_save_future_done)

        if recent_errors > 0:
            with self._save_stats_lock:
                last_err = self._last_save_error
            logger.warning("后台保存进行中，但最近 %d 次保存失败 (最近错误: %s)", recent_errors, last_err[:120])
            return None, f"结果保存已转后台 ⚠️ 最近{recent_errors}次失败"
        return None, "结果保存已转后台"

    def _on_save_future_done(self, future: Future) -> None:
        self._pending_save_futures.discard(future)
        try:
            save_result = future.result()
            with self._save_stats_lock:
                if self._consecutive_save_failures > 0:
                    logger.info(
                        "后台保存已恢复 (之前失败 %d 次, 记录=%s)",
                        self._consecutive_save_failures,
                        save_result.record_id,
                    )
                self._consecutive_save_failures = 0
                self._total_save_successes += 1
                self._save_result_queue.append(
                    SaveResultSnapshot(
                        status="ok",
                        record_dir=str(save_result.record_dir),
                        record_id=save_result.record_id,
                    )
                )
        except Exception as exc:
            error_msg = str(exc)
            with self._save_stats_lock:
                self._consecutive_save_failures += 1
                self._total_save_failures += 1
                self._last_save_error = error_msg
                self._save_result_queue.append(
                    SaveResultSnapshot(status="error", error_message=error_msg)
                )
            logger.error(
                "检测结果图片保存失败 (连续失败=%d, 累计失败=%d): %s",
                self._consecutive_save_failures,
                self._total_save_failures,
                exc,
                exc_info=True,
            )

    @property
    def save_health(self) -> dict:
        """返回保存健康状态，供 UI 轮询显示。"""
        with self._save_stats_lock:
            return {
                "consecutive_failures": self._consecutive_save_failures,
                "total_failures": self._total_save_failures,
                "total_successes": self._total_save_successes,
                "last_error": self._last_save_error,
                "pending_count": len(self._pending_save_futures),
            }

    def drain_save_results(self) -> list[SaveResultSnapshot]:
        """取出并清空最近的保存结果快照，供 UI 轮询消费。"""
        with self._save_stats_lock:
            if not self._save_result_queue:
                return []
            drained = list(self._save_result_queue)
            self._save_result_queue.clear()
            return drained

    def shutdown(self, timeout_seconds: float = 5.0) -> None:
        """等待后台保存完成并关闭线程池。应在应用退出前调用。"""
        pending = list(self._pending_save_futures)
        if pending:
            logger.info("正在等待 %d 个后台保存任务完成 (超时=%.1fs)...", len(pending), timeout_seconds)
            for future in pending:
                try:
                    future.result(timeout=timeout_seconds)
                except Exception as exc:
                    logger.error("后台保存任务未在超时内完成: %s", exc)
            logger.info("后台保存任务等待结束")
        self._save_executor.shutdown(wait=True)
        logger.info("结果保存线程池已关闭")
