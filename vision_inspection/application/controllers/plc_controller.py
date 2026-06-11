from __future__ import annotations

from typing import Optional

from vision_inspection.application.services.plc_service import PlcService
from vision_inspection.infrastructure.plc import PlcOutputResult, PlcTriggerEvent


class PlcController:
    def __init__(self, plc_service: PlcService) -> None:
        self._plc_service = plc_service

    def connect(self) -> None:
        self._plc_service.connect()

    def disconnect(self) -> None:
        self._plc_service.disconnect()

    def is_connected(self) -> bool:
        return self._plc_service.is_connected()

    def wait_for_trigger(self, timeout_ms: int = 500) -> Optional[PlcTriggerEvent]:
        return self._plc_service.wait_for_trigger(timeout_ms=timeout_ms)

    def simulate_trigger(self) -> None:
        self._plc_service.simulate_trigger()

    def emit_ng_output(
        self,
        signal_name: str,
        channel: str,
        pulse_ms: int = 100,
        delay_ms: int = 0,
        reset_mode: str = "auto",
    ) -> PlcOutputResult:
        return self._plc_service.emit_ng_output(
            signal_name=signal_name,
            channel=channel,
            pulse_ms=pulse_ms,
            delay_ms=delay_ms,
            reset_mode=reset_mode,
        )
