from __future__ import annotations

import socket
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import requests

from vision_inspection.utils.logger import get_logger

logger = get_logger(__name__)


def validate_serial_no(serial_no: str | None) -> str | None:
    """校验流水号有效性：非空、非"0"、长度恰好为 10。返回错误消息或 None。"""
    if not serial_no or not serial_no.strip():
        return "流水号为空，无法查询机型"
    serial_no = serial_no.strip()
    if serial_no == "0":
        return "流水号为无效值 '0'，已丢弃"
    if len(serial_no) != 10:
        return f"流水号长度必须为 10 位，当前为 {len(serial_no)} 位"
    return None


@dataclass
class CrankshaftApiResponse:
    code: int
    message: str
    machine_type: str = ""
    serial_no: str = ""
    request_id: str = ""


class CrankshaftApiError(RuntimeError):
    pass


class CrankshaftApiClient:
    """曲轴工位 HTTP API 客户端 — 查询流水号对应的机型。"""

    def __init__(self, base_url: str, timeout_ms: int = 1500, source: str = "vision-inspection") -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_ms = timeout_ms
        self._source = source
        self._last_processed_serial: Optional[str] = None

    @property
    def last_processed_serial(self) -> str | None:
        return self._last_processed_serial

    def get_machine_type(self, serial_no: str) -> str:
        """查询机型，返回完整机型号（如 '10V3AABB1234'）。"""
        validation_error = validate_serial_no(serial_no)
        if validation_error:
            raise CrankshaftApiError(validation_error)

        serial_no = serial_no.strip()
        if serial_no == self._last_processed_serial:
            logger.info("流水号 %s 已处理过，跳过重复请求", serial_no)
            raise CrankshaftApiError(f"流水号 {serial_no} 已处理过，幂等跳过")

        request_id = str(uuid.uuid4())
        url = f"{self._base_url}/api/v1/crankshaft/model-by-serial"
        payload = {
            "serialNo": serial_no,
            "source": self._source,
            "requestId": request_id,
        }

        last_error = None
        for retry_index in range(4):
            cost_start = time.perf_counter()
            try:
                response = requests.post(url, json=payload, timeout=self._timeout_ms / 1000.0)
                response.raise_for_status()
                data = response.json()
                cost_ms = (time.perf_counter() - cost_start) * 1000
                code = int(data.get("code", -1))
                machine_type = str(data.get("machineType", "")).strip()
                logger.info(
                    "API 查询机型: requestId=%s serialNo=%s responseCode=%d machineType=%s costMs=%d retryIndex=%d",
                    request_id, serial_no, code, machine_type, int(cost_ms), retry_index,
                )

                if code == 0:
                    if not machine_type:
                        raise CrankshaftApiError(f"API 返回机型为空，流水号: {serial_no}")
                    self._last_processed_serial = serial_no
                    return machine_type
                elif code == 1003 and retry_index < 3:
                    delay_ms = [200, 300, 500][retry_index]
                    logger.warning("API 返回 code=1003，第 %d 次重试，等待 %d ms", retry_index + 1, delay_ms)
                    time.sleep(delay_ms / 1000.0)
                    continue
                else:
                    raise CrankshaftApiError(
                        f"API 返回异常: code={code}, message={data.get('message', 'unknown')}, serialNo={serial_no}"
                    )
            except requests.RequestException as exc:
                cost_ms = (time.perf_counter() - cost_start) * 1000
                last_error = exc
                logger.error("API 请求失败 (retry %d): %s, costMs=%d", retry_index, exc, int(cost_ms))
                if retry_index < 3 and isinstance(exc, (requests.ConnectionError, requests.Timeout)):
                    delay_ms = [200, 300, 500][retry_index]
                    time.sleep(delay_ms / 1000.0)
                    continue
                raise CrankshaftApiError(f"API 请求失败: {exc}") from exc

        raise CrankshaftApiError(f"API 请求失败（已重试 3 次）: {last_error}") from last_error

    def check_health(self) -> str:
        """返回 'ok' / 'no_service' / 'no_network' 三种状态。"""
        from urllib.parse import urlparse
        parsed = urlparse(self._base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8080

        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.close()
        except OSError:
            return "no_network"

        try:
            response = requests.get(
                f"{self._base_url}/api/v1/health",
                timeout=max(3, self._timeout_ms / 1000.0),
            )
            return "ok" if response.status_code == 200 else "no_service"
        except requests.RequestException:
            return "no_service"
