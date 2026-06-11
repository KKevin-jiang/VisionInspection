from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PlcTriggerEvent:
    source: str
    message: str


@dataclass(frozen=True)
class PlcOutputResult:
    signal_name: str
    channel: str
    message: str


class PlcAdapterBase:
    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError

    def wait_for_trigger(self, timeout_ms: int = 500) -> Optional[PlcTriggerEvent]:
        raise NotImplementedError

    def simulate_trigger(self) -> None:
        raise NotImplementedError

    def emit_ng_output(
        self,
        signal_name: str,
        channel: str,
        pulse_ms: int = 100,
        delay_ms: int = 0,
        reset_mode: str = "auto",
    ) -> PlcOutputResult:
        raise NotImplementedError
