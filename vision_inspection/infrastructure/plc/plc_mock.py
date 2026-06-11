from __future__ import annotations

import threading
import time
from typing import Optional

from vision_inspection.infrastructure.plc.plc_base import PlcAdapterBase, PlcOutputResult, PlcTriggerEvent


class MockPlcAdapter(PlcAdapterBase):
    def __init__(self) -> None:
        self._connected = False
        self._trigger_event = threading.Event()
        self._last_output_message = ""

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        self._trigger_event.set()

    def is_connected(self) -> bool:
        return self._connected

    def wait_for_trigger(self, timeout_ms: int = 500) -> Optional[PlcTriggerEvent]:
        if not self._connected:
            return None
        signaled = self._trigger_event.wait(timeout_ms / 1000.0)
        if not signaled or not self._connected:
            return None
        self._trigger_event.clear()
        return PlcTriggerEvent(source="mock_plc", message="收到模拟 PLC 触发")

    def simulate_trigger(self) -> None:
        if self._connected:
            self._trigger_event.set()

    def emit_ng_output(
        self,
        signal_name: str,
        channel: str,
        pulse_ms: int = 100,
        delay_ms: int = 0,
        reset_mode: str = "auto",
    ) -> PlcOutputResult:
        if not self._connected:
            raise RuntimeError("PLC 未连接，无法输出 NG 信号")

        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        self._last_output_message = f"Mock PLC 输出 NG 信号: {signal_name} -> {channel}"

        if reset_mode == "auto" and pulse_ms > 0:
            time.sleep(pulse_ms / 1000.0)
            self._last_output_message = (
                f"Mock PLC 已自动复位 NG 信号: {signal_name} -> {channel}, 脉宽 {pulse_ms}ms"
            )

        return PlcOutputResult(
            signal_name=signal_name,
            channel=channel,
            message=self._last_output_message,
        )
