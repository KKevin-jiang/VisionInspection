from __future__ import annotations

from typing import Callable, Optional

from vision_inspection.infrastructure.plc import MockPlcAdapter, PlcAdapterBase, PlcOutputResult, PlcTriggerEvent


class PlcServiceError(RuntimeError):
    pass


class PlcService:
    def __init__(self, adapter_factory: Optional[Callable[[], PlcAdapterBase]] = None) -> None:
        self._adapter_factory = adapter_factory or MockPlcAdapter
        self._adapter: Optional[PlcAdapterBase] = None

    def connect(self) -> None:
        adapter = self._get_adapter()
        try:
            adapter.connect()
        except Exception as exc:
            raise PlcServiceError(str(exc)) from exc

    def disconnect(self) -> None:
        if self._adapter is None:
            return
        try:
            self._adapter.disconnect()
        except Exception as exc:
            raise PlcServiceError(str(exc)) from exc

    def is_connected(self) -> bool:
        return self._adapter is not None and self._adapter.is_connected()

    def wait_for_trigger(self, timeout_ms: int = 500) -> Optional[PlcTriggerEvent]:
        adapter = self._get_adapter()
        try:
            return adapter.wait_for_trigger(timeout_ms=timeout_ms)
        except Exception as exc:
            raise PlcServiceError(str(exc)) from exc

    def simulate_trigger(self) -> None:
        adapter = self._get_adapter()
        try:
            adapter.simulate_trigger()
        except Exception as exc:
            raise PlcServiceError(str(exc)) from exc

    def emit_ng_output(
        self,
        signal_name: str,
        channel: str,
        pulse_ms: int = 100,
        delay_ms: int = 0,
        reset_mode: str = "auto",
    ) -> PlcOutputResult:
        adapter = self._get_adapter()
        try:
            return adapter.emit_ng_output(
                signal_name=signal_name,
                channel=channel,
                pulse_ms=pulse_ms,
                delay_ms=delay_ms,
                reset_mode=reset_mode,
            )
        except Exception as exc:
            raise PlcServiceError(str(exc)) from exc

    def _get_adapter(self) -> PlcAdapterBase:
        if self._adapter is None:
            self._adapter = self._adapter_factory()
        return self._adapter
