from __future__ import annotations

from typing import List

from vision_inspection.application.services.camera_service import CameraCapture, CameraService
from vision_inspection.infrastructure.camera import CameraDeviceInfo


class CameraController:
    def __init__(self, camera_service: CameraService) -> None:
        self._camera_service = camera_service

    def list_devices(self) -> List[CameraDeviceInfo]:
        return self._camera_service.list_devices()

    def capture_manual_frame(self, preferred_device_index: int = 0) -> CameraCapture:
        return self._camera_service.capture_manual_frame(preferred_device_index)

    def prepare_external_trigger_listener(self, preferred_device_index: int = 0) -> str:
        return self._camera_service.prepare_external_trigger_listener(preferred_device_index)

    def clear_image_buffer(self, preferred_device_index: int = 0) -> None:
        self._camera_service.clear_image_buffer(preferred_device_index)

    def set_trigger_activation(self, activation: str) -> None:
        self._camera_service.set_trigger_activation(activation)

    def set_pass_pulse_ms(self, pulse_ms: int) -> None:
        self._camera_service.set_pass_pulse_ms(pulse_ms)

    def emit_pass_output(
        self,
        preferred_device_index: int = 0,
        channel: str = "Line1",
        delay_ms: int = 0,
    ) -> str:
        return self._camera_service.emit_pass_output(
            preferred_device_index=preferred_device_index,
            channel=channel,
            delay_ms=delay_ms,
        )

    def diagnose_output_line(
        self,
        preferred_device_index: int = 0,
        channel: str = "Line1",
    ) -> str:
        return self._camera_service.diagnose_output_line(
            preferred_device_index=preferred_device_index,
            channel=channel,
        )

    def get_camera_params(self, preferred_device_index: int = 0) -> dict[str, float]:
        return self._camera_service.get_camera_params(preferred_device_index)

    def set_camera_param(self, node_name: str, value: float, preferred_device_index: int = 0) -> None:
        return self._camera_service.set_camera_param(node_name, value, preferred_device_index)

    def shutdown(self) -> None:
        self._camera_service.shutdown()
