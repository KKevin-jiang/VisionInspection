from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from vision_inspection.infrastructure.camera import (
    CameraDeviceInfo,
    CameraFrame,
    HikCameraClient,
    HikCameraError,
    HikCameraTimeoutError,
)

_logger = logging.getLogger(__name__)


@dataclass
class CameraCapture:
    device: CameraDeviceInfo
    frame: CameraFrame


class CameraServiceError(RuntimeError):
    pass


class CameraTriggerTimeoutError(CameraServiceError):
    pass


class CameraService:
    def __init__(self, camera_client_factory: Optional[Callable[[], HikCameraClient]] = None) -> None:
        self._camera_client_factory = camera_client_factory or HikCameraClient
        self._camera_client: Optional[HikCameraClient] = None
        self._devices: List[CameraDeviceInfo] = []
        self._active_device_index: Optional[int] = None
        self._capture_mode: Optional[str] = None
        self._trigger_activation: str = "RisingEdge"
        self._pass_pulse_ms: int = 500

    def list_devices(self) -> List[CameraDeviceInfo]:
        client = self._get_client()
        if not self._devices:
            self._devices = client.enum_devices()
        return list(self._devices)

    def capture_manual_frame(self, preferred_device_index: int = 0) -> CameraCapture:
        return self.capture_frame(trigger_mode="manual", preferred_device_index=preferred_device_index)

    def capture_frame(
        self,
        trigger_mode: str = "manual",
        preferred_device_index: int = 0,
        timeout_ms: int | None = None,
    ) -> CameraCapture:
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            raise CameraServiceError("未发现可用海康相机")

        if preferred_device_index < 0 or preferred_device_index >= len(devices):
            raise CameraServiceError(f"无效的相机索引: {preferred_device_index}")

        selected_device = devices[preferred_device_index]
        self._ensure_device_open(preferred_device_index)
        effective_timeout_ms = timeout_ms if timeout_ms is not None else self._default_timeout_for_mode(trigger_mode)

        try:
            self._prepare_capture_mode(trigger_mode)
            if not client.is_grabbing:
                client.start_grabbing()
            if trigger_mode == "software_trigger":
                client.trigger_software_once()
            # 外部触发模式下清空帧缓冲，丢弃检测处理期间堆积的旧帧，
            # 确保 grab_frame 只接收新的 Line0 触发帧。
            if (trigger_mode or "manual").strip().lower() == "plc_external":
                import time as _time2
                _t_clear = _time2.perf_counter()
                client.clear_image_buffer()
            frame = client.grab_frame(timeout_ms=effective_timeout_ms)
            if (trigger_mode or "manual").strip().lower() == "plc_external":
                _elapsed = (_time2.perf_counter() - _t_clear) * 1000
                _logger.info(
                    "capture_frame: grab_frame 返回 (frame=%d, 距clear %.1f ms, timeout=%d ms)%s",
                    frame.frame_number, _elapsed, effective_timeout_ms,
                    " ⚡帧到达极快!" if _elapsed < 50 else "",
                )
            return CameraCapture(device=selected_device, frame=frame)
        except HikCameraTimeoutError as exc:
            raise CameraTriggerTimeoutError(self._build_timeout_message(trigger_mode, effective_timeout_ms)) from exc
        except HikCameraError as exc:
            raise CameraServiceError(str(exc)) from exc

    def set_pass_pulse_ms(self, pulse_ms: int) -> None:
        self._pass_pulse_ms = pulse_ms

    def emit_pass_output(
        self,
        preferred_device_index: int = 0,
        channel: str = "Line1",
        delay_ms: int = 0,
    ) -> str:
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            raise CameraServiceError("未发现可用海康相机")
        if preferred_device_index < 0 or preferred_device_index >= len(devices):
            raise CameraServiceError(f"无效的相机索引: {preferred_device_index}")

        self._ensure_device_open(preferred_device_index)
        output_channel = channel or "Line1"
        pulse_ms = self._pass_pulse_ms
        _logger.info("emit_pass_output: channel=%s pulse_ms=%d delay_ms=%d activation=%s",
                     output_channel, pulse_ms, delay_ms, self._trigger_activation)
        try:
            client.pulse_output_line(
                line_name=output_channel,
                pulse_ms=pulse_ms,
                delay_ms=delay_ms,
                trigger_activation=self._trigger_activation,
            )
        except HikCameraError as exc:
            raise CameraServiceError(str(exc)) from exc
        # NOTE: _capture_mode is intentionally preserved here.
        # pulse_output_line()'s finally block restores the camera to external trigger
        # mode + starts grabbing, so the camera state matches what _capture_mode says.
        # Invalidating _capture_mode would force _prepare_capture_mode to stop/restart
        # grabbing on every subsequent IO cycle, creating a window where Line0 triggers
        # are missed.
        return f"相机 {output_channel} 已输出 OK 脉冲 {pulse_ms} ms"

    def diagnose_output_line(
        self,
        preferred_device_index: int = 0,
        channel: str = "Line1",
    ) -> str:
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            raise CameraServiceError("未发现可用海康相机")
        if preferred_device_index < 0 or preferred_device_index >= len(devices):
            raise CameraServiceError(f"无效的相机索引: {preferred_device_index}")

        self._ensure_device_open(preferred_device_index)
        output_channel = channel or "Line1"
        try:
            return client.diagnose_output_line(line_name=output_channel)
        except HikCameraError as exc:
            raise CameraServiceError(str(exc)) from exc

    def clear_image_buffer(self, preferred_device_index: int = 0) -> None:
        """清空相机内部图像缓冲，丢弃抓流期间堆积的旧帧。"""
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            return
        self._ensure_device_open(preferred_device_index)
        client.clear_image_buffer()

    def flush_grab_pipeline(self, preferred_device_index: int = 0) -> None:
        """停止拉流→清空缓冲→重新拉流，彻底冲刷相机取流管线。

        用于 NG 检测后确保下一次 grab_frame 必须等待新的 Line0 触发，
        而非立即返回检测期间堆积在 SDK 队列中的旧帧。

        .. warning::
           此方法在 stop_grabbing 之后调用 clear_image_buffer 会失败
           (0x80000003 MV_E_CALLORDER)，且 start_grabbing 重启采集引擎时
           若 Line0 仍为 HIGH 电平，相机会不经触发立即出帧。
           NG 路径已改用 clear_image_buffer 替代，本方法保留供其他场景使用。
        """
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            return
        self._ensure_device_open(preferred_device_index)
        _logger.info("flush_grab_pipeline: 开始 (is_grabbing=%s)", client.is_grabbing)
        if client.is_grabbing:
            client.stop_grabbing()
        client.clear_image_buffer()
        client.start_grabbing()
        _logger.info("flush_grab_pipeline: stop→clear→start 完成")

    def prepare_external_trigger_listener(self, preferred_device_index: int = 0) -> str:
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            raise CameraServiceError("未发现可用海康相机")
        if preferred_device_index < 0 or preferred_device_index >= len(devices):
            raise CameraServiceError(f"无效的相机索引: {preferred_device_index}")

        selected_device = devices[preferred_device_index]
        self._ensure_device_open(preferred_device_index)
        self._prepare_capture_mode("plc_external")
        try:
            if not client.is_grabbing:
                client.start_grabbing()
            # Clear any stale frames that may have been buffered during
            # start_grabbing, so the first grab_frame() call genuinely
            # waits for a fresh Line0 trigger.
            client.clear_image_buffer()
        except HikCameraError as exc:
            raise CameraServiceError(str(exc)) from exc
        return selected_device.display_name

    CAMERA_PARAM_NODES: dict[str, str] = {
        "exposure_us": "ExposureTime",
        "gain_raw": "GainRaw",
        "gamma": "Gamma",
        "frame_rate": "AcquisitionFrameRate",
        "digital_gain": "DigitalGain",
    }

    def get_camera_params(self, preferred_device_index: int = 0) -> dict[str, float]:
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            raise CameraServiceError("未发现可用海康相机")
        if preferred_device_index < 0 or preferred_device_index >= len(devices):
            raise CameraServiceError(f"无效的相机索引: {preferred_device_index}")
        self._ensure_device_open(preferred_device_index)

        params: dict[str, float] = {}
        for config_key, node_name in self.CAMERA_PARAM_NODES.items():
            try:
                value = client.get_float_param(node_name)
                params[config_key] = value
            except HikCameraError:
                try:
                    value = float(client.get_int_param(node_name))
                    params[config_key] = value
                except HikCameraError:
                    continue
        return params

    def set_camera_param(self, node_name: str, value: float, preferred_device_index: int = 0) -> None:
        client = self._get_client()
        devices = self.list_devices()
        if not devices:
            raise CameraServiceError("未发现可用海康相机")
        if preferred_device_index < 0 or preferred_device_index >= len(devices):
            raise CameraServiceError(f"无效的相机索引: {preferred_device_index}")
        self._ensure_device_open(preferred_device_index)

        try:
            client.set_float_param(node_name, value)
        except HikCameraError:
            try:
                client.set_int_param(node_name, int(value))
            except HikCameraError as exc:
                raise CameraServiceError(str(exc)) from exc

    def shutdown(self) -> None:
        if self._camera_client is None:
            return
        try:
            self._camera_client.shutdown()
        finally:
            self._camera_client = None
            self._devices = []
            self._active_device_index = None
            self._capture_mode = None

    def _get_client(self) -> HikCameraClient:
        if self._camera_client is None:
            self._camera_client = self._camera_client_factory()
            try:
                self._camera_client.initialize_sdk()
            except HikCameraError as exc:
                self._camera_client = None
                raise CameraServiceError(str(exc)) from exc
        return self._camera_client

    def _ensure_device_open(self, device_index: int) -> None:
        client = self._get_client()
        if client.is_open and self._active_device_index == device_index:
            return

        if client.is_open:
            client.close_device()

        try:
            client.open_device(device_index)
        except HikCameraError as exc:
            raise CameraServiceError(str(exc)) from exc

        self._active_device_index = device_index
        self._capture_mode = None

    def set_trigger_activation(self, activation: str) -> None:
        if self._trigger_activation != activation:
            _logger.info("set_trigger_activation: %s -> %s (invalidating capture_mode cache)",
                         self._trigger_activation, activation)
            self._capture_mode = None
        self._trigger_activation = activation

    def _prepare_capture_mode(self, trigger_mode: str) -> None:
        client = self._get_client()
        normalized_mode = (trigger_mode or "manual").strip().lower()
        if normalized_mode not in {"manual", "plc_external", "software_trigger"}:
            raise CameraServiceError(f"不支持的采图模式: {trigger_mode}")

        if self._capture_mode == normalized_mode:
            return

        if client.is_grabbing:
            client.stop_grabbing()

        try:
            if normalized_mode == "manual":
                client.set_continuous_mode()
            elif normalized_mode == "plc_external":
                client.set_external_trigger_mode(trigger_activation=self._trigger_activation)
            else:
                client.set_software_trigger_mode()
        except HikCameraError as exc:
            raise CameraServiceError(str(exc)) from exc

        self._capture_mode = normalized_mode

    def _default_timeout_for_mode(self, trigger_mode: str) -> int:
        normalized_mode = (trigger_mode or "manual").strip().lower()
        if normalized_mode == "plc_external":
            return 500
        return 1000

    def _build_timeout_message(self, trigger_mode: str, timeout_ms: int) -> str:
        normalized_mode = (trigger_mode or "manual").strip().lower()
        if normalized_mode == "plc_external":
            return f"等待相机 Line0 外部触发超时，{timeout_ms} ms 内未收到硬件脉冲"
        if normalized_mode == "software_trigger":
            return f"软件触发采图超时，{timeout_ms} ms 内未收到图像"
        return f"相机采图超时，{timeout_ms} ms 内未收到图像"
