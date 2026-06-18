from __future__ import annotations

import logging
import sys
import threading
import time
from ctypes import POINTER, byref, c_ubyte, cast, memset, sizeof, string_at
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

_logger = logging.getLogger(__name__)

def _get_logger():
    return _logger


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
MVIMPORT_DIR = WORKSPACE_ROOT / "MvImport"
if str(MVIMPORT_DIR) not in sys.path:
    sys.path.append(str(MVIMPORT_DIR))

from CameraParams_const import MV_GENTL_CXP_DEVICE, MV_GENTL_GIGE_DEVICE, MV_GENTL_XOF_DEVICE, MV_GIGE_DEVICE, MV_USB_DEVICE
from CameraParams_header import (
    MV_ACCESS_Exclusive,
    MV_CC_DEVICE_INFO,
    MV_CC_DEVICE_INFO_LIST,
    MV_CC_PIXEL_CONVERT_PARAM_EX,
    MV_FRAME_OUT,
    MV_TRIGGER_MODE_OFF,
    MV_TRIGGER_SOURCE_LINE0,
    MV_TRIGGER_SOURCE_SOFTWARE,
    MVCC_ENUMENTRY,
    MVCC_ENUMVALUE,
    MVCC_FLOATVALUE,
    MVCC_INTVALUE,
    MVCC_INTVALUE_EX,
)
from MvCameraControl_class import MvCamera
from MvErrorDefine_const import MV_E_CALLORDER, MV_E_GC_TIMEOUT, MV_E_NODATA, MV_OK
from PixelType_header import (
    PixelType_Gvsp_BGR8_Packed,
    PixelType_Gvsp_BayerBG10,
    PixelType_Gvsp_BayerBG10_Packed,
    PixelType_Gvsp_BayerBG12,
    PixelType_Gvsp_BayerBG12_Packed,
    PixelType_Gvsp_BayerBG16,
    PixelType_Gvsp_BayerBG8,
    PixelType_Gvsp_BayerGB10,
    PixelType_Gvsp_BayerGB10_Packed,
    PixelType_Gvsp_BayerGB12,
    PixelType_Gvsp_BayerGB12_Packed,
    PixelType_Gvsp_BayerGB16,
    PixelType_Gvsp_BayerGB8,
    PixelType_Gvsp_BayerGR10,
    PixelType_Gvsp_BayerGR10_Packed,
    PixelType_Gvsp_BayerGR12,
    PixelType_Gvsp_BayerGR12_Packed,
    PixelType_Gvsp_BayerGR16,
    PixelType_Gvsp_BayerGR8,
    PixelType_Gvsp_BayerRBGG8,
    PixelType_Gvsp_BayerRG10,
    PixelType_Gvsp_BayerRG10_Packed,
    PixelType_Gvsp_BayerRG12,
    PixelType_Gvsp_BayerRG12_Packed,
    PixelType_Gvsp_BayerRG16,
    PixelType_Gvsp_BayerRG8,
    PixelType_Gvsp_Mono10,
    PixelType_Gvsp_Mono10_Packed,
    PixelType_Gvsp_Mono12,
    PixelType_Gvsp_Mono12_Packed,
    PixelType_Gvsp_Mono8,
    PixelType_Gvsp_RGB8_Packed,
    PixelType_Gvsp_YUV422_Packed,
    PixelType_Gvsp_YUV422_YUYV_Packed,
)


MONO_PIXEL_TYPES = {
    PixelType_Gvsp_Mono8,
    PixelType_Gvsp_Mono10,
    PixelType_Gvsp_Mono10_Packed,
    PixelType_Gvsp_Mono12,
    PixelType_Gvsp_Mono12_Packed,
}

COLOR_PIXEL_TYPES = {
    PixelType_Gvsp_RGB8_Packed,
    PixelType_Gvsp_BGR8_Packed,
    PixelType_Gvsp_BayerGR8,
    PixelType_Gvsp_BayerRG8,
    PixelType_Gvsp_BayerGB8,
    PixelType_Gvsp_BayerBG8,
    PixelType_Gvsp_BayerGR10,
    PixelType_Gvsp_BayerRG10,
    PixelType_Gvsp_BayerGB10,
    PixelType_Gvsp_BayerBG10,
    PixelType_Gvsp_BayerGR12,
    PixelType_Gvsp_BayerRG12,
    PixelType_Gvsp_BayerGB12,
    PixelType_Gvsp_BayerBG12,
    PixelType_Gvsp_BayerGR10_Packed,
    PixelType_Gvsp_BayerRG10_Packed,
    PixelType_Gvsp_BayerGB10_Packed,
    PixelType_Gvsp_BayerBG10_Packed,
    PixelType_Gvsp_BayerGR12_Packed,
    PixelType_Gvsp_BayerRG12_Packed,
    PixelType_Gvsp_BayerGB12_Packed,
    PixelType_Gvsp_BayerBG12_Packed,
    PixelType_Gvsp_BayerRBGG8,
    PixelType_Gvsp_BayerGR16,
    PixelType_Gvsp_BayerRG16,
    PixelType_Gvsp_BayerGB16,
    PixelType_Gvsp_BayerBG16,
    PixelType_Gvsp_YUV422_Packed,
    PixelType_Gvsp_YUV422_YUYV_Packed,
}


def _decode_char_array(ctypes_char_array: Any) -> str:
    byte_str = memoryview(ctypes_char_array).tobytes()
    null_index = byte_str.find(b"\x00")
    if null_index != -1:
        byte_str = byte_str[:null_index]
    for encoding in ("gbk", "utf-8", "latin-1"):
        try:
            return byte_str.decode(encoding)
        except UnicodeDecodeError:
            continue
    return byte_str.decode("latin-1", errors="replace")


def _to_hex_str(num: int) -> str:
    if num < 0:
        num = num + 2 ** 32
    return f"0x{num:x}"


@dataclass(frozen=True)
class CameraDeviceInfo:
    index: int
    layer_type: int
    manufacturer: str
    model_name: str
    user_defined_name: str
    serial_number: str
    ip_address: str
    display_name: str


@dataclass
class CameraFrame:
    image: np.ndarray
    width: int
    height: int
    pixel_type: int
    frame_number: int


class HikCameraError(RuntimeError):
    pass


class HikCameraTimeoutError(HikCameraError):
    pass


ERROR_HINTS = {
    0x80000203: "设备无访问权限。通常是相机已被海康 MVS、Viewer、其他上位机程序或上一次未释放的连接占用。",
    0x80000204: "设备忙或网络断开。请检查相机连接状态、网线和当前是否正在被其他程序取流。",
    0x80000305: "USB 驱动不匹配或未正确安装。请检查海康驱动和设备管理器状态。",
}


class HikCameraClient:
    _sdk_lock = threading.Lock()
    _sdk_ref_count = 0

    def __init__(self) -> None:
        self._camera: Optional[MvCamera] = None
        self._device_list = MV_CC_DEVICE_INFO_LIST()
        self._selected_index: Optional[int] = None
        self._opened = False
        self._grabbing = False
        self._initialized = False

    @property
    def is_open(self) -> bool:
        return self._opened

    @property
    def is_grabbing(self) -> bool:
        return self._grabbing

    def initialize_sdk(self) -> None:
        with self._sdk_lock:
            if self.__class__._sdk_ref_count == 0:
                ret = MvCamera.MV_CC_Initialize()
                self._raise_for_ret("initialize SDK", ret)
            self.__class__._sdk_ref_count += 1
            self._initialized = True

    def finalize_sdk(self) -> None:
        with self._sdk_lock:
            if not self._initialized:
                return
            self.__class__._sdk_ref_count = max(0, self.__class__._sdk_ref_count - 1)
            if self.__class__._sdk_ref_count == 0:
                ret = MvCamera.MV_CC_Finalize()
                self._raise_for_ret("finalize SDK", ret)
            self._initialized = False

    def enum_devices(self) -> List[CameraDeviceInfo]:
        self._ensure_initialized()
        self._device_list = MV_CC_DEVICE_INFO_LIST()
        n_layer_type = (
            MV_GIGE_DEVICE
            | MV_USB_DEVICE
            | MV_GENTL_GIGE_DEVICE
            | MV_GENTL_CXP_DEVICE
            | MV_GENTL_XOF_DEVICE
        )
        ret = MvCamera.MV_CC_EnumDevices(n_layer_type, self._device_list)
        self._raise_for_ret("enumerate devices", ret)

        devices = []
        for index in range(self._device_list.nDeviceNum):
            device_info = cast(self._device_list.pDeviceInfo[index], POINTER(MV_CC_DEVICE_INFO)).contents
            devices.append(self._build_device_info(index, device_info))
        return devices

    def open_device(self, device_index: int) -> None:
        self._ensure_initialized()
        if self._opened:
            raise HikCameraError("camera is already open")

        if self._device_list.nDeviceNum == 0:
            self.enum_devices()
        if device_index < 0 or device_index >= self._device_list.nDeviceNum:
            raise HikCameraError(f"invalid device index: {device_index}")

        device_info = cast(self._device_list.pDeviceInfo[device_index], POINTER(MV_CC_DEVICE_INFO)).contents
        if not MvCamera.MV_CC_IsDeviceAccessible(device_info, MV_ACCESS_Exclusive):
            raise HikCameraError(
                "open device failed: 0x80000203. 设备无访问权限。"
                "请先关闭海康 MVS、Viewer 或其他占用该相机的程序，再重试。"
            )
        self._camera = MvCamera()
        ret = self._camera.MV_CC_CreateHandle(device_info)
        self._raise_for_ret("create camera handle", ret)

        try:
            ret = self._camera.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            self._raise_for_ret("open device", ret)
            self._configure_packet_size(device_info)
            self._camera.MV_CC_SetBayerCvtQuality(1)
            self._opened = True
            self._selected_index = device_index
        except Exception:
            self._safe_destroy_handle()
            raise

    def close_device(self) -> None:
        if self._camera is None:
            return
        if self._grabbing:
            self.stop_grabbing()
        if self._opened:
            ret = self._camera.MV_CC_CloseDevice()
            self._raise_for_ret("close device", ret)
            self._opened = False
        self._safe_destroy_handle()
        self._selected_index = None

    def set_external_trigger_mode(
        self,
        trigger_source: int = MV_TRIGGER_SOURCE_LINE0,
        trigger_activation: str = "RisingEdge",
        output_line: str = "Line1",
    ) -> None:
        self._ensure_opened()
        # ── 0. Turn OFF trigger mode first ──
        # Many GenICam nodes (TriggerSource, TriggerActivation) are only
        # writable when TriggerMode is Off. Changing them while trigger is
        # On may silently fail, leaving the camera in an inconsistent state.
        self._camera.MV_CC_SetEnumValue("TriggerMode", 0)  # Off
        # ── 1. Ensure Line0 is configured as INPUT ──
        self._ensure_line_input("Line0", context="set_external_trigger_mode")
        # ── 2. Configure trigger parameters (safe now — TriggerMode=Off) ──
        self._try_set_enum_value_by_string("AcquisitionMode", "Continuous")
        self._try_set_enum_value_by_string("TriggerSelector", "FrameStart")
        ret = self._camera.MV_CC_SetEnumValue("TriggerSource", trigger_source)
        self._raise_for_ret("set trigger source", ret)
        ret = self._camera.MV_CC_SetEnumValueByString("TriggerActivation", trigger_activation)
        self._raise_for_ret("set trigger activation", ret)
        # ── 3. Turn trigger mode back ON ──
        ret = self._camera.MV_CC_SetEnumValue("TriggerMode", 1)  # On
        self._raise_for_ret("set trigger mode on", ret)
        # ── 4. Ensure output line strobe is disabled ──
        self._disable_strobe_on_line(output_line, context="set_external_trigger_mode")
        self._camera.MV_CC_ClearImageBuffer()
        # ── 5. Verify final trigger state ──
        tm = self._read_enum_node("TriggerMode")
        ts = self._read_enum_node("TriggerSource")
        ta = self._read_enum_node("TriggerActivation")
        _logger.info(
            "set_external_trigger_mode: final state TriggerMode=%s TriggerSource=%s TriggerActivation=%s",
            tm["current"] if tm else "?",
            ts["current"] if ts else "?",
            ta["current"] if ta else "?",
        )

    def _ensure_line_input(self, line_name: str, context: str = "") -> None:
        """Ensure a physical I/O line is configured as Input.

        This is critical for Line0: if the line was previously used as an output
        (e.g. StrobeEnable accidentally applied to it), the camera may have
        auto-switched its LineMode to Output, making it unable to receive
        external trigger signals.
        """
        prefix = f"{context}: " if context else ""
        # ① Select the line
        ret_sel = self._camera.MV_CC_SetEnumValueByString("LineSelector", line_name)
        if ret_sel != MV_OK:
            _logger.warning("%s_ensure_line_input: LineSelector=%s 失败: 0x%08X", prefix, line_name, ret_sel)
            return
        # ② Read current LineMode
        line_mode = self._read_enum_node("LineMode")
        mode_str = line_mode["current"] if line_mode else "?"
        _logger.info("%s%s LineMode 当前=%s", prefix, line_name, mode_str)
        # ③ Try to set LineMode=Input
        ret_mode = self._camera.MV_CC_SetEnumValueByString("LineMode", "Input")
        if ret_mode != MV_OK:
            _logger.info("%s%s LineMode=Input 不支持或失败: 0x%08X (当前=%s)", prefix, line_name, ret_mode, mode_str)
        else:
            _logger.info("%s%s LineMode=Input OK (was %s)", prefix, line_name, mode_str)
        # ④ Also ensure StrobeEnable is off on this line
        ret_sd = self._camera.MV_CC_SetBoolValue("StrobeEnable", False)
        if ret_sd != MV_OK:
            _logger.info("%s%s StrobeEnable=False: 0x%08X (non-critical)", prefix, line_name, ret_sd)
        readback_sd = self._read_bool_node("StrobeEnable")
        _logger.info("%s%s StrobeEnable 回读=%s", prefix, line_name, readback_sd)
        # ⑤ Read current electrical level of the line
        line_status = self._read_bool_node("LineStatus")
        _logger.info("%s%s LineStatus 回读=%s (True=High/有信号, False=Low/无信号)", prefix, line_name, line_status)

    def _disable_strobe_on_line(self, line_name: str, context: str = "") -> None:
        """关闭指定输出线的频闪输出。

        ⚠️ 关键：StrobeEnable / LineSource / StrobeLineDuration 在海康相机上都是
        **按 LineSelector 分线** 的设置。必须先 LineSelector=Line1 再写 StrobeEnable，
        否则会把 StrobeEnable 写到当前选中的其它线（如 Line0），Line1 的频闪不会被关闭，
        导致每次真实 Line0 触发曝光时 Line1 都跟着输出脉冲 → 电平一直为高。
        """
        prefix = f"{context}: " if context else ""
        # ① 先选中目标输出线
        ret_sel = self._camera.MV_CC_SetEnumValueByString("LineSelector", line_name)
        if ret_sel != MV_OK:
            _logger.warning("%sLineSelector=%s 失败: 0x%08X", prefix, line_name, ret_sel)
            return
        # ② 关闭该线的频闪
        ret_sd = self._camera.MV_CC_SetBoolValue("StrobeEnable", False)
        if ret_sd != MV_OK:
            _logger.warning("%s%s StrobeEnable=False 失败: 0x%08X", prefix, line_name, ret_sd)
        # ③ 回读确认（StrobeEnable 是否真的关闭了）
        readback = self._read_bool_node("StrobeEnable")
        _logger.info("%s%s StrobeEnable 回读=%s (期望 False)", prefix, line_name, readback)

    def _log_selected_line_status(self, line_name: str, context: str = "") -> None:
        prefix = f"{context}: " if context else ""
        line_status = self._read_bool_node("LineStatus")
        _logger.info("%s%s LineStatus 回读=%s (True=High/有信号, False=Low/无信号)", prefix, line_name, line_status)

    def set_software_trigger_mode(self) -> None:
        self._ensure_opened()
        ret = self._camera.MV_CC_SetEnumValue("TriggerMode", 1)
        self._raise_for_ret("set trigger mode on", ret)
        ret = self._camera.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)
        self._raise_for_ret("set software trigger source", ret)
        self._camera.MV_CC_ClearImageBuffer()

    def set_continuous_mode(self) -> None:
        self._ensure_opened()
        ret = self._camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
        self._raise_for_ret("set continuous mode", ret)
        self._camera.MV_CC_ClearImageBuffer()

    def trigger_software_once(self) -> None:
        self._ensure_opened()
        ret = self._camera.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)
        self._raise_for_ret("set software trigger source", ret)
        ret = self._camera.MV_CC_SetCommandValue("TriggerSoftware")
        self._raise_for_ret("trigger software once", ret)

    def _ensure_line_output(self, line_name: str, context: str = "") -> None:
        """Ensure a physical I/O line is configured for output.

        MV-CS060-10GC (and similar Hikvision cameras) have three LineMode states:
          - Input   → physical output driver disabled
          - Output  → general-purpose output (UserOutput, TimerActive, etc.)
          - Strobe  → specialised strobe output (ExposureStartActive, etc.)

        **Strobe is a legitimate output mode.**  When LineMode=Strobe, the line
        driver IS active.  Attempting to switch Strobe→Output fails with
        MV_E_CALLORDER (0x80000004) because the camera treats it as an illegal
        state transition while strobe resources are held.

        Strategy:
          Input   → try Output first, fall back to Strobe
          Output  → already correct, no-op
          Strobe  → already output-capable; just disable StrobeEnable to start clean
        """
        prefix = f"{context}: " if context else ""
        # ① Select the line
        ret_sel = self._camera.MV_CC_SetEnumValueByString("LineSelector", line_name)
        if ret_sel != MV_OK:
            _logger.warning("%s_ensure_line_output: LineSelector=%s 失败: 0x%08X", prefix, line_name, ret_sel)
            return
        # ② Read current LineMode + supported values
        line_mode = self._read_enum_node("LineMode")
        mode_str = line_mode["current"] if line_mode else "?"
        supported = line_mode["supported"] if line_mode else []
        _logger.info("%s%s LineMode 当前=%s 可选=%s", prefix, line_name, mode_str, supported)

        # ③ Decide action
        if mode_str == "Output":
            _logger.info("%s%s LineMode 已是 Output，无需切换", prefix, line_name)
        elif mode_str == "Strobe":
            # Strobe IS an output mode — don't fight it. Just ensure StrobeEnable
            # is off so the line is idle before we configure the new pulse.
            _logger.info("%s%s LineMode=Strobe（频闪输出模式，已是输出状态，无需切换到 Output）", prefix, line_name)
            self._try_set_bool_value("StrobeEnable", False)
        elif mode_str == "Input":
            # Must switch to an output-capable mode.  Some cameras support
            # "Output", others only offer "Strobe".  Try Output first.
            if "Output" in supported:
                ret_mode = self._camera.MV_CC_SetEnumValueByString("LineMode", "Output")
                if ret_mode == MV_OK:
                    _logger.info("%s%s LineMode: Input → Output OK", prefix, line_name)
                else:
                    _logger.warning(
                        "%s%s LineMode: Input → Output 失败 0x%08X，尝试 Strobe", prefix, line_name, ret_mode,
                    )
                    if "Strobe" in supported:
                        ret_s = self._camera.MV_CC_SetEnumValueByString("LineMode", "Strobe")
                        _logger.info("%s%s LineMode: Input → Strobe ret=0x%08X", prefix, line_name, ret_s)
            elif "Strobe" in supported:
                ret_mode = self._camera.MV_CC_SetEnumValueByString("LineMode", "Strobe")
                _logger.info("%s%s LineMode: Input → Strobe (Output 不支持) ret=0x%08X", prefix, line_name, ret_mode)
            else:
                _logger.warning(
                    "%s%s LineMode=Input 且不支持 Output/Strobe —— 物理输出可能未激活，PLC 将收不到信号！",
                    prefix, line_name,
                )
        else:
            # Unknown / unreadable — try Output as a best-effort fallback
            _logger.warning("%s%s LineMode 未知状态=%s，尝试设为 Output", prefix, line_name, mode_str)
            ret_mode = self._camera.MV_CC_SetEnumValueByString("LineMode", "Output")
            if ret_mode != MV_OK and "Strobe" in supported:
                self._camera.MV_CC_SetEnumValueByString("LineMode", "Strobe")

        # ④ Read back final LineMode for verification
        line_mode2 = self._read_enum_node("LineMode")
        final_mode = line_mode2["current"] if line_mode2 else "?"
        _logger.info("%s%s LineMode 最终=%s", prefix, line_name, final_mode)

        # ⑤ Read LineInverter — if True, output polarity is reversed (PLC sees inverted signal)
        line_inverter = self._read_bool_node("LineInverter")
        _logger.info("%s%s LineInverter=%s (False=正常极性, True=反相)", prefix, line_name, line_inverter)

        # ⑥ Check StrobeEnable state before pulse configuration
        sb_readback = self._read_bool_node("StrobeEnable")
        _logger.info("%s%s StrobeEnable 当前=%s", prefix, line_name, sb_readback)

    def configure_output_line(self, line_name: str = "Line1") -> None:
        self._ensure_opened()
        self._ensure_line_output(line_name, context="configure_output_line")

    def _list_user_output_sources(self) -> List[str]:
        line_source = self._read_enum_node("LineSource")
        if not line_source:
            return []
        return [source for source in line_source["supported"] if source.startswith("UserOutput")]

    def _list_line_sources(self) -> List[str]:
        line_source = self._read_enum_node("LineSource")
        if not line_source:
            return []
        return list(line_source["supported"])

    def _reset_user_output_sources(self, user_sources: List[str], context: str = "") -> None:
        prefix = f"{context}: " if context else ""
        for source in user_sources:
            ret_src = self._camera.MV_CC_SetEnumValueByString("LineSource", source)
            ret_sel = self._camera.MV_CC_SetEnumValueByString("UserOutputSelector", source)
            ret_low = self._camera.MV_CC_SetBoolValue("UserOutputValue", False)
            _logger.info(
                "%sreset %s -> LineSource=0x%08X UserOutputSelector=0x%08X UserOutputValue(False)=0x%08X",
                prefix,
                source,
                ret_src,
                ret_sel,
                ret_low,
            )

    def pulse_output_line(
        self,
        line_name: str = "Line1",
        pulse_ms: int = 50,
        delay_ms: int = 0,
        trigger_activation: str = "RisingEdge",
    ) -> None:
        self._ensure_opened()

        pulse_ms_safe = max(1, pulse_ms)
        delay_ms_safe = max(0, delay_ms)
        pulse_us = pulse_ms_safe * 1000
        delay_us = delay_ms_safe * 1000
        _logger = _get_logger()

        # ── All output-line configuration MUST happen while NOT grabbing ──
        was_grabbing = self._grabbing
        if was_grabbing:
            _logger.info("pulse_output_line: stop grabbing before config (was_grabbing=True)")
            self.stop_grabbing()

        try:
            # Select the output line first (now safe — not streaming)
            self.configure_output_line(line_name=line_name)
            _logger.info("pulse_output_line: LineSelector=%s OK", line_name)

            # --- Attempt 1: direct UserOutput pulse (best match for PLC digital input) ---
            user_sources = self._list_user_output_sources()
            _logger.info("pulse_output_line: UserOutput candidates=%s", user_sources)
            for source in user_sources:
                ret_src = self._camera.MV_CC_SetEnumValueByString("LineSource", source)
                ret_sel = self._camera.MV_CC_SetEnumValueByString("UserOutputSelector", source)
                _logger.info(
                    "pulse_output_line: Attempt1 source=%s LineSource=0x%08X UserOutputSelector=0x%08X",
                    source,
                    ret_src,
                    ret_sel,
                )
                if ret_src != MV_OK or ret_sel != MV_OK:
                    continue

                self._camera.MV_CC_SetBoolValue("StrobeEnable", False)
                if delay_ms_safe:
                    time.sleep(delay_ms_safe / 1000.0)

                ret_high = self._camera.MV_CC_SetBoolValue("UserOutputValue", True)
                _logger.info("pulse_output_line: Attempt1 %s UserOutputValue=True ret=0x%08X", source, ret_high)
                if ret_high != MV_OK:
                    self._camera.MV_CC_SetBoolValue("UserOutputValue", False)
                    continue

                time.sleep(pulse_ms_safe / 1000.0)
                ret_low = self._camera.MV_CC_SetBoolValue("UserOutputValue", False)
                self._raise_for_ret(f"set {source} UserOutputValue=False", ret_low)
                _logger.info("pulse_output_line: Attempt1 SUCCESS via %s", source)
                return

            # --- Attempt 2: TimerActive (if timer nodes exist) ---
            timer_available = self._read_enum_node("TimerSelector") is not None
            _logger.info("pulse_output_line: TimerSelector available=%s", timer_available)
            if timer_available:
                ret_src = self._camera.MV_CC_SetEnumValueByString("LineSource", "TimerActive")
                _logger.info(
                    "pulse_output_line: Attempt2 LineSource=TimerActive ret=0x%08X", ret_src
                )
                if ret_src == MV_OK:
                    self._camera.MV_CC_SetBoolValue("StrobeEnable", False)
                    for timer_sel in ("Timer1", "Timer2", "Timer0"):
                        if self._camera.MV_CC_SetEnumValueByString("TimerSelector", timer_sel) != MV_OK:
                            continue
                        if (
                            self._camera.MV_CC_SetEnumValueByString("TimerTriggerSource", "LineTrigger")
                            != MV_OK
                        ):
                            continue
                        self._camera.MV_CC_SetIntValueEx("TimerDelay", delay_us)
                        self._camera.MV_CC_SetIntValueEx("TimerDuration", pulse_us)
                        cmd_ret = self._camera.MV_CC_SetCommandValue("LineTriggerSoftware")
                        _logger.info(
                            "pulse_output_line: Attempt2 %s LineTriggerSoftware ret=0x%08X",
                            timer_sel, cmd_ret,
                        )
                        if cmd_ret == MV_OK:
                            time.sleep(pulse_ms_safe / 1000.0 + 0.05)
                            _logger.info("pulse_output_line: Attempt2 SUCCESS via %s", timer_sel)
                            return

            # --- Attempt 3: one-shot start event source (preferred over exposure retrigger) ---
            level_sources = self._list_line_sources()
            one_shot_source = next(
                (
                    source
                    for source in ("AcquisitionStartActive", "FrameBurstStartActive", "FrameStartActive")
                    if source in level_sources
                ),
                None,
            )
            _logger.info("pulse_output_line: one-shot-source candidates=%s selected=%s", level_sources, one_shot_source)
            if one_shot_source:
                ret_tm_off = self._camera.MV_CC_SetEnumValue("TriggerMode", 0)  # Off → free-running
                self._raise_for_ret("set TriggerMode=Off (free-running)", ret_tm_off)
                _logger.info("pulse_output_line: TriggerMode=Off (free-running) OK")

                ret_src = self._camera.MV_CC_SetEnumValueByString("LineSource", one_shot_source)
                self._raise_for_ret(f"set LineSource={one_shot_source}", ret_src)
                _logger.info("pulse_output_line: Attempt3 LineSource=%s OK", one_shot_source)

                ret_strobe = self._camera.MV_CC_SetBoolValue("StrobeEnable", True)
                self._raise_for_ret("enable StrobeEnable for Attempt3", ret_strobe)
                effective_pulse_us = self._set_int_node_ex_clamped(
                    "StrobeLineDuration",
                    pulse_us,
                    "set Attempt3 StrobeLineDuration",
                )
                effective_delay_us = self._set_int_node_ex_clamped(
                    "StrobeLineDelay",
                    delay_us,
                    "set Attempt3 StrobeLineDelay",
                )
                _logger.info(
                    "pulse_output_line: Attempt3 strobe pulse configured duration=%d us delay=%d us",
                    effective_pulse_us,
                    effective_delay_us,
                )

                # StartGrabbing should emit a single acquisition/frame-start event,
                # and StrobeLineDuration stretches it into a PLC-visible pulse.
                self.start_grabbing()
                _logger.info(
                    "pulse_output_line: Attempt3 start_grabbing OK, waiting %.3f s for one-shot pulse",
                    pulse_ms_safe / 1000.0 + delay_ms_safe / 1000.0 + 0.2,
                )
                probe_sleep = min(0.05, (pulse_ms_safe + delay_ms_safe) / 1000.0 + 0.2)
                if probe_sleep > 0:
                    time.sleep(probe_sleep)
                self._log_selected_line_status(line_name, context="pulse_output_line Attempt3 active")
                remaining_sleep = (pulse_ms_safe + delay_ms_safe) / 1000.0 + 0.2 - probe_sleep
                if remaining_sleep > 0:
                    time.sleep(remaining_sleep)
                self.stop_grabbing()
                self._log_selected_line_status(line_name, context="pulse_output_line Attempt3 stopped")
                self._disable_strobe_on_line(line_name, context="pulse_output_line")
                _logger.info("pulse_output_line: Attempt3 SUCCESS via %s", one_shot_source)
                return

            # --- Attempt 4: free-running level source (preferred for PLC input if available) ---
            level_source = next(
                (
                    source
                    for source in ("AcquisitionActive", "FrameBurstActive", "FrameActive")
                    if source in level_sources
                ),
                None,
            )
            _logger.info("pulse_output_line: level-source candidates=%s selected=%s", level_sources, level_source)
            if level_source:
                ret_tm_off = self._camera.MV_CC_SetEnumValue("TriggerMode", 0)  # Off → free-running
                self._raise_for_ret("set TriggerMode=Off (free-running)", ret_tm_off)
                _logger.info("pulse_output_line: TriggerMode=Off (free-running) OK")

                self._camera.MV_CC_SetBoolValue("StrobeEnable", False)
                ret_src = self._camera.MV_CC_SetEnumValueByString("LineSource", level_source)
                self._raise_for_ret(f"set LineSource={level_source}", ret_src)
                _logger.info("pulse_output_line: Attempt4 LineSource=%s OK", level_source)

                if delay_ms_safe:
                    time.sleep(delay_ms_safe / 1000.0)

                self.start_grabbing()
                _logger.info(
                    "pulse_output_line: Attempt4 start_grabbing OK, holding %s for %.3f s",
                    level_source,
                    pulse_ms_safe / 1000.0,
                )
                probe_sleep = min(0.05, pulse_ms_safe / 1000.0)
                if probe_sleep > 0:
                    time.sleep(probe_sleep)
                self._log_selected_line_status(line_name, context="pulse_output_line Attempt4 active")
                remaining_sleep = pulse_ms_safe / 1000.0 - probe_sleep
                if remaining_sleep > 0:
                    time.sleep(remaining_sleep)
                self.stop_grabbing()
                self._log_selected_line_status(line_name, context="pulse_output_line Attempt4 stopped")
                _logger.info("pulse_output_line: Attempt4 SUCCESS via %s", level_source)
                return

            # --- Attempt 5: ExposureStartActive strobe via free-running mode ---
            #
            # 本相机 (MV-CS060-10GC) 仅支持此方案。详见需求文档 4.6 节。
            #
            # ⚠️ 历经三轮调试（2026-06-15）发现的关键事实：
            #   - TriggerSelector 只读，固定为 FrameBurstStart（非 FrameStart）
            #   - 尝试写 TriggerSelector → 0x80000106 (ACCESS_DENIED)
            #   - 切换 TriggerSource=Software → 0x80000004 (CALLORDER)
            #     → 频闪子系统与触发源切换存在互锁，无法通过 Software Trigger 实现
            #
            # ✅ 新方案：Continuous 自由运行模式 + ExposureStartActive 频闪
            #   TriggerMode=Off → 相机进入连续自由采集
            #   → 每帧曝光触发 ExposureStartActive → Line1 输出频闪脉冲
            #   → StrobeLineDuration=500ms > 帧间隔 → 频闪持续重触发
            #   → Line1 在自由运行期间保持 HIGH → sleep 后停流关频闪 → Line1 回 LOW
            #
            #   无需 TriggerSource 切换，无需 TriggerSoftware，无 CALLORDER 冲突。
            _logger.info("pulse_output_line: falling back to Attempt 5 (free-running + ExposureStartActive strobe)")

            # ── ① Switch to free-running continuous mode ──
            ret_tm_off = self._camera.MV_CC_SetEnumValue("TriggerMode", 0)  # Off → free-running
            self._raise_for_ret("set TriggerMode=Off (free-running)", ret_tm_off)
            _logger.info("pulse_output_line: TriggerMode=Off (free-running) OK")

            # ── ② Configure strobe on Line1 ──
            ret_src = self._camera.MV_CC_SetEnumValueByString(
                "LineSource", "ExposureStartActive"
            )
            self._raise_for_ret("set LineSource=ExposureStartActive", ret_src)
            _logger.info("pulse_output_line: LineSource=ExposureStartActive OK")

            ret_strobe = self._camera.MV_CC_SetBoolValue("StrobeEnable", True)
            self._raise_for_ret("enable StrobeEnable", ret_strobe)
            _logger.info("pulse_output_line: StrobeEnable=True OK")

            effective_pulse_us = self._set_int_node_ex_clamped(
                "StrobeLineDuration",
                pulse_us,
                "set StrobeLineDuration",
            )
            _logger.info("pulse_output_line: StrobeLineDuration=%d us OK", effective_pulse_us)

            effective_delay_us = self._set_int_node_ex_clamped(
                "StrobeLineDelay",
                delay_us,
                "set StrobeLineDelay",
            )
            _logger.info("pulse_output_line: StrobeLineDelay=%d us OK", effective_delay_us)

            # StrobeLinePreDelay not present on all cameras; non-critical
            pre_ret = self._camera.MV_CC_SetIntValueEx("StrobeLinePreDelay", 0)
            _logger.info("pulse_output_line: StrobeLinePreDelay=0 ret=0x%08X (non-critical)", pre_ret)

            # ── ③ Start grabbing → camera free-runs → each exposure fires strobe ──
            #     StrobeLineDuration (500ms) >> frame interval (~17ms at 60fps)
            #     → strobe retriggers before expiry → Line1 stays HIGH continuously
            self.start_grabbing()
            _logger.info(
                "pulse_output_line: start_grabbing OK (free-running), "
                "sleeping %.3f s for pulse duration", pulse_ms_safe / 1000.0 + 0.2
            )

            # Pulse duration: sleep while camera free-runs with strobe active
            probe_sleep = min(0.05, pulse_ms_safe / 1000.0 + 0.2)
            if probe_sleep > 0:
                time.sleep(probe_sleep)
            self._log_selected_line_status(line_name, context="pulse_output_line Attempt5 active")
            remaining_sleep = pulse_ms_safe / 1000.0 + 0.2 - probe_sleep
            if remaining_sleep > 0:
                time.sleep(remaining_sleep)

            # ── ④ Stop grabbing → disable strobe → Line1 goes LOW ──
            self.stop_grabbing()
            _logger.info("pulse_output_line: stop_grabbing OK")
            self._log_selected_line_status(line_name, context="pulse_output_line Attempt5 stopped")

            # Disable strobe — MUST select Line1 first (strobe params are per-line)
            self._disable_strobe_on_line(line_name, context="pulse_output_line")
        finally:
            self._reset_user_output_sources(user_sources if 'user_sources' in locals() else [], context="pulse_output_line")
            # --- Restore external trigger mode ---
            self.set_external_trigger_mode(
                trigger_activation=trigger_activation,
            )
            _logger.info("pulse_output_line: external trigger mode restored (activation=%s)", trigger_activation)
            if was_grabbing:
                self.start_grabbing()
                _logger.info("pulse_output_line: grabbing restarted")
            self._camera.MV_CC_ClearImageBuffer()
            _logger.info("pulse_output_line: ClearImageBuffer done, pulse sequence complete")

    def diagnose_output_line(self, line_name: str = "Line1") -> str:
        """Probe the output line and report exactly what it supports and how
        each output mechanism responds. Returns a human-readable multi-line
        report (does not raise on individual SDK failures)."""
        self._ensure_opened()
        report: List[str] = []

        ret = self._camera.MV_CC_SetEnumValueByString("LineSelector", line_name)
        report.append(f"[1] LineSelector={line_name}: {_to_hex_str(ret)}")
        if ret != MV_OK:
            report.append("    无法选中该输出线，后续探测中止。")
            return "\n".join(report)

        line_mode = self._read_enum_node("LineMode")
        if line_mode is not None:
            report.append(f"[2] LineMode 当前={line_mode['current']}")
            report.append(f"    LineMode 可选={', '.join(line_mode['supported']) or '(无)'}")
        else:
            report.append("[2] LineMode 读取失败（该线可能为固定输出，无 LineMode）")

        line_source = self._read_enum_node("LineSource")
        if line_source is not None:
            report.append(f"[3] LineSource 当前={line_source['current']}")
            report.append(f"    LineSource 可选={', '.join(line_source['supported']) or '(无)'}")
            supported_sources = set(line_source["supported"])
        else:
            report.append("[3] LineSource 读取失败")
            supported_sources = set()

        report.append(f"[4] UserOutput 方案（软件直接控制电平）:")
        user_candidates = [s for s in line_source["supported"] if s.startswith("UserOutput")] if line_source else []
        if not user_candidates:
            report.append("    LineSource 不支持任何 UserOutput，无法用软件电平方案。")
        for source in user_candidates:
            ret_src = self._camera.MV_CC_SetEnumValueByString("LineSource", source)
            ret_sel = self._camera.MV_CC_SetEnumValueByString("UserOutputSelector", source)
            ret_high = self._camera.MV_CC_SetBoolValue("UserOutputValue", True)
            readback_high = self._read_bool_node("UserOutputValue")
            ret_low = self._camera.MV_CC_SetBoolValue("UserOutputValue", False)
            report.append(
                f"    {source}: setSource={_to_hex_str(ret_src)} "
                f"setSelector={_to_hex_str(ret_sel)} "
                f"setHigh={_to_hex_str(ret_high)}(回读={readback_high}) "
                f"setLow={_to_hex_str(ret_low)}"
            )

        strobe_enable = self._read_bool_node("StrobeEnable")
        report.append(f"[5] StrobeEnable 当前回读={strobe_enable}")

        line_inverter = self._read_bool_node("LineInverter")
        report.append(f"[6] LineInverter 当前回读={line_inverter}")

        trigger_mode = self._read_enum_node("TriggerMode")
        trigger_source = self._read_enum_node("TriggerSource")
        report.append(
            f"[7] TriggerMode={trigger_mode['current'] if trigger_mode else '?'}"
            f"  TriggerSource={trigger_source['current'] if trigger_source else '?'}"
        )

        report.append("[8] Timer 节点探测（TimerActive 方案可行性）:")
        timer_selector = self._read_enum_node("TimerSelector")
        if timer_selector is not None:
            report.append(f"    TimerSelector 当前={timer_selector['current']}")
            report.append(f"    TimerSelector 可选={', '.join(timer_selector['supported']) or '(无)'}")
        else:
            report.append("    TimerSelector 读取失败——TimerActive 方案不可用")
        timer_trig_src = self._read_enum_node("TimerTriggerSource")
        if timer_trig_src is not None:
            report.append(f"    TimerTriggerSource 当前={timer_trig_src['current']}")
            report.append(f"    TimerTriggerSource 可选={', '.join(timer_trig_src['supported']) or '(无)'}")
        else:
            report.append("    TimerTriggerSource 读取失败")
        try:
            from ctypes import c_int64
            timer_delay = c_int64(0)
            ret_td = self._camera.MV_CC_GetIntValueEx("TimerDelay", timer_delay)
            if ret_td == MV_OK:
                report.append(f"    TimerDelay 当前={timer_delay.value} us")
            else:
                report.append(f"    TimerDelay: {_to_hex_str(ret_td)}")
        except Exception:
            report.append("    TimerDelay: 不支持读取")
        try:
            from ctypes import c_int64
            timer_dur = c_int64(0)
            ret_tdur = self._camera.MV_CC_GetIntValueEx("TimerDuration", timer_dur)
            if ret_tdur == MV_OK:
                report.append(f"    TimerDuration 当前={timer_dur.value} us")
            else:
                report.append(f"    TimerDuration: {_to_hex_str(ret_tdur)}")
        except Exception:
            report.append("    TimerDuration: 不支持读取")

        return "\n".join(report)

    def _read_enum_node(self, node_name: str) -> Optional[dict]:
        enum_value = MVCC_ENUMVALUE()
        memset(byref(enum_value), 0, sizeof(enum_value))
        ret = self._camera.MV_CC_GetEnumValue(node_name, enum_value)
        if ret != MV_OK:
            return None
        current = self._enum_symbolic(node_name, enum_value.nCurValue)
        supported = [
            self._enum_symbolic(node_name, enum_value.nSupportValue[i])
            for i in range(enum_value.nSupportedNum)
        ]
        return {"current": current, "supported": supported}

    def _enum_symbolic(self, node_name: str, value: int) -> str:
        entry = MVCC_ENUMENTRY()
        memset(byref(entry), 0, sizeof(entry))
        entry.nValue = value
        ret = self._camera.MV_CC_GetEnumEntrySymbolic(node_name, entry)
        if ret != MV_OK:
            return str(value)
        symbolic = _decode_char_array(entry.chSymbolic)
        return symbolic or str(value)

    def _read_bool_node(self, node_name: str) -> Optional[bool]:
        from ctypes import c_bool

        bool_value = c_bool(False)
        ret = self._camera.MV_CC_GetBoolValue(node_name, bool_value)
        if ret != MV_OK:
            return None
        return bool(bool_value.value)

    def _read_int_node_ex(self, node_name: str) -> Optional[dict[str, int]]:
        int_value = MVCC_INTVALUE_EX()
        memset(byref(int_value), 0, sizeof(int_value))
        ret = self._camera.MV_CC_GetIntValueEx(node_name, int_value)
        if ret != MV_OK:
            return None
        return {
            "current": int(int_value.nCurValue),
            "max": int(int_value.nMax),
            "min": int(int_value.nMin),
            "inc": int(int_value.nInc),
        }

    def _set_int_node_ex_clamped(self, node_name: str, value: int, action: str) -> int:
        node_info = self._read_int_node_ex(node_name)
        if not node_info:
            ret = self._camera.MV_CC_SetIntValueEx(node_name, value)
            self._raise_for_ret(action, ret)
            return value

        min_value = node_info["min"]
        max_value = node_info["max"]
        increment = max(1, node_info["inc"])
        clamped = min(max(value, min_value), max_value)
        if increment > 1:
            clamped = min_value + ((clamped - min_value) // increment) * increment
            clamped = min(max(clamped, min_value), max_value)

        if clamped != value:
            _logger.warning(
                "%s requested=%d exceeds supported range [%d, %d] inc=%d; using %d",
                action,
                value,
                min_value,
                max_value,
                increment,
                clamped,
            )
        else:
            _logger.info(
                "%s using %d within supported range [%d, %d] inc=%d",
                action,
                clamped,
                min_value,
                max_value,
                increment,
            )

        ret = self._camera.MV_CC_SetIntValueEx(node_name, clamped)
        self._raise_for_ret(action, ret)
        return clamped

    def _save_enum_node(self, node_name: str) -> Optional[int]:
        """Return the current integer value of an enum node, or None if unreadable."""
        enum_value = MVCC_ENUMVALUE()
        memset(byref(enum_value), 0, sizeof(enum_value))
        ret = self._camera.MV_CC_GetEnumValue(node_name, enum_value)
        if ret != MV_OK:
            return None
        return int(enum_value.nCurValue)

    def _restore_enum_node(self, node_name: str, saved_value: Optional[int]) -> None:
        """Restore an enum node to a previously saved integer value."""
        if saved_value is None:
            return
        self._camera.MV_CC_SetEnumValue(node_name, saved_value)

    def get_float_param(self, node_name: str) -> float:
        self._ensure_opened()
        st_float = MVCC_FLOATVALUE()
        ret = self._camera.MV_CC_GetFloatValue(node_name, st_float)
        self._raise_for_ret(f"get float param '{node_name}'", ret)
        return float(st_float.fCurValue)

    def set_float_param(self, node_name: str, value: float) -> None:
        self._ensure_opened()
        ret = self._camera.MV_CC_SetFloatValue(node_name, value)
        self._raise_for_ret(f"set float param '{node_name}'={value}", ret)

    def get_int_param(self, node_name: str) -> int:
        self._ensure_opened()
        st_int = MVCC_INTVALUE()
        ret = self._camera.MV_CC_GetIntValue(node_name, st_int)
        self._raise_for_ret(f"get int param '{node_name}'", ret)
        return int(st_int.nCurValue)

    def set_int_param(self, node_name: str, value: int) -> None:
        self._ensure_opened()
        ret = self._camera.MV_CC_SetIntValue(node_name, value)
        self._raise_for_ret(f"set int param '{node_name}'={value}", ret)

    def start_grabbing(self) -> None:
        self._ensure_opened()
        if self._grabbing:
            return
        ret = self._camera.MV_CC_StartGrabbing()
        if ret == MV_E_CALLORDER:
            # CALLORDER on StartGrabbing typically means the device is
            # already streaming.  Sync our flag and carry on.
            _logger.warning("start_grabbing: SDK returned CALLORDER (already grabbing); syncing flag to True")
            self._grabbing = True
            return
        self._raise_for_ret("start grabbing", ret)
        self._grabbing = True

    def stop_grabbing(self) -> None:
        self._ensure_opened()
        if not self._grabbing:
            return
        ret = self._camera.MV_CC_StopGrabbing()
        if ret == MV_E_CALLORDER:
            # CALLORDER on StopGrabbing means the SDK believes we are not
            # currently streaming.  The most common cause is that our
            # internal _grabbing flag drifted out of sync with the real
            # device state (e.g. after a partially-failed pulse_output_line
            # sequence).  Sync the flag and move on — forcing an error here
            # would leave the flag stuck at True permanently and break
            # every subsequent capture attempt.
            _logger.warning("stop_grabbing: SDK returned CALLORDER (not grabbing); syncing flag to False")
            self._grabbing = False
            return
        self._raise_for_ret("stop grabbing", ret)
        self._grabbing = False

    def clear_image_buffer(self) -> None:
        """Clear the camera's internal image buffer."""
        self._ensure_opened()
        ret = self._camera.MV_CC_ClearImageBuffer()
        if ret != MV_OK:
            _logger.warning("clear_image_buffer failed: 0x%08X", ret)
        else:
            _logger.info("clear_image_buffer OK")

    def grab_frame(self, timeout_ms: int = 1000) -> CameraFrame:
        self._ensure_opened()
        if not self._grabbing:
            raise HikCameraError("camera is not grabbing")

        # Lightweight log — avoid _read_enum_node calls during active grab
        # as they may interfere with the SDK's internal grab engine.
        _logger.info("grab_frame: waiting up to %d ms (grabbing=%s)", timeout_ms, self._grabbing)

        frame_out = MV_FRAME_OUT()
        memset(byref(frame_out), 0, sizeof(frame_out))
        ret = self._camera.MV_CC_GetImageBuffer(frame_out, timeout_ms)
        if ret in (MV_E_NODATA, MV_E_GC_TIMEOUT):
            _logger.warning("grab_frame: timeout after %d ms", timeout_ms)
            raise HikCameraTimeoutError(f"grab frame timed out: {_to_hex_str(ret)}")
        self._raise_for_ret("grab frame", ret)

        try:
            image = self._convert_frame_to_ndarray(frame_out)
            frame_info = frame_out.stFrameInfo
            return CameraFrame(
                image=image,
                width=frame_info.nWidth,
                height=frame_info.nHeight,
                pixel_type=frame_info.enPixelType,
                frame_number=frame_info.nFrameNum,
            )
        finally:
            ret = self._camera.MV_CC_FreeImageBuffer(frame_out)
            self._raise_for_ret("free image buffer", ret)

    def shutdown(self) -> None:
        self.close_device()
        self.finalize_sdk()

    def __enter__(self) -> "HikCameraClient":
        self.initialize_sdk()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.shutdown()

    def _build_device_info(self, index: int, device_info: MV_CC_DEVICE_INFO) -> CameraDeviceInfo:
        manufacturer = ""
        model_name = ""
        user_defined_name = ""
        serial_number = ""
        ip_address = ""

        if device_info.nTLayerType in (MV_GIGE_DEVICE, MV_GENTL_GIGE_DEVICE):
            info = device_info.SpecialInfo.stGigEInfo
            manufacturer = _decode_char_array(info.chManufacturerName)
            model_name = _decode_char_array(info.chModelName)
            user_defined_name = _decode_char_array(info.chUserDefinedName)
            ip_address = self._format_ip_address(info.nCurrentIp)
        elif device_info.nTLayerType == MV_USB_DEVICE:
            info = device_info.SpecialInfo.stUsb3VInfo
            manufacturer = _decode_char_array(info.chManufacturerName)
            model_name = _decode_char_array(info.chModelName)
            user_defined_name = _decode_char_array(info.chUserDefinedName)
            serial_number = _decode_char_array(info.chSerialNumber)
        elif device_info.nTLayerType == MV_GENTL_CXP_DEVICE:
            info = device_info.SpecialInfo.stCXPInfo
            manufacturer = _decode_char_array(info.chManufacturerName)
            model_name = _decode_char_array(info.chModelName)
            user_defined_name = _decode_char_array(info.chUserDefinedName)
            serial_number = _decode_char_array(info.chSerialNumber)
        elif device_info.nTLayerType == MV_GENTL_XOF_DEVICE:
            info = device_info.SpecialInfo.stXoFInfo
            manufacturer = _decode_char_array(info.chManufacturerName)
            model_name = _decode_char_array(info.chModelName)
            user_defined_name = _decode_char_array(info.chUserDefinedName)
            serial_number = _decode_char_array(info.chSerialNumber)

        display_name = f"[{index}] {model_name or 'Unknown'}"
        if user_defined_name:
            display_name = f"[{index}] {user_defined_name} {model_name}".strip()
        return CameraDeviceInfo(
            index=index,
            layer_type=device_info.nTLayerType,
            manufacturer=manufacturer,
            model_name=model_name,
            user_defined_name=user_defined_name,
            serial_number=serial_number,
            ip_address=ip_address,
            display_name=display_name,
        )

    def _configure_packet_size(self, device_info: MV_CC_DEVICE_INFO) -> None:
        if device_info.nTLayerType not in (MV_GIGE_DEVICE, MV_GENTL_GIGE_DEVICE):
            return
        packet_size = self._camera.MV_CC_GetOptimalPacketSize()
        if int(packet_size) <= 0:
            return
        ret = self._camera.MV_CC_SetIntValue("GevSCPSPacketSize", packet_size)
        self._raise_for_ret("set packet size", ret)

    def _convert_frame_to_ndarray(self, frame_out: MV_FRAME_OUT) -> np.ndarray:
        frame_info = frame_out.stFrameInfo
        width = frame_info.nWidth
        height = frame_info.nHeight
        pixel_type = frame_info.enPixelType
        frame_len = frame_info.nFrameLen

        if pixel_type == PixelType_Gvsp_Mono8:
            return np.frombuffer(string_at(frame_out.pBufAddr, frame_len), dtype=np.uint8).copy().reshape(height, width)

        if pixel_type == PixelType_Gvsp_BGR8_Packed:
            return np.frombuffer(string_at(frame_out.pBufAddr, frame_len), dtype=np.uint8).copy().reshape(height, width, 3)

        if pixel_type == PixelType_Gvsp_RGB8_Packed:
            rgb = np.frombuffer(string_at(frame_out.pBufAddr, frame_len), dtype=np.uint8).copy().reshape(height, width, 3)
            return rgb[:, :, ::-1].copy()

        if pixel_type in MONO_PIXEL_TYPES:
            return self._convert_pixel_type(frame_out, PixelType_Gvsp_Mono8, channel_count=1)

        if pixel_type in COLOR_PIXEL_TYPES:
            return self._convert_pixel_type(frame_out, PixelType_Gvsp_BGR8_Packed, channel_count=3)

        raise HikCameraError(f"unsupported pixel type: {pixel_type}")

    def _convert_pixel_type(self, frame_out: MV_FRAME_OUT, dst_pixel_type: int, channel_count: int) -> np.ndarray:
        frame_info = frame_out.stFrameInfo
        width = frame_info.nWidth
        height = frame_info.nHeight
        dst_size = width * height * channel_count

        dst_buffer = (c_ubyte * dst_size)()
        convert_param = MV_CC_PIXEL_CONVERT_PARAM_EX()
        memset(byref(convert_param), 0, sizeof(convert_param))
        convert_param.nWidth = width
        convert_param.nHeight = height
        convert_param.pSrcData = frame_out.pBufAddr
        convert_param.nSrcDataLen = frame_info.nFrameLen
        convert_param.enSrcPixelType = frame_info.enPixelType
        convert_param.enDstPixelType = dst_pixel_type
        convert_param.pDstBuffer = dst_buffer
        convert_param.nDstBufferSize = dst_size

        ret = self._camera.MV_CC_ConvertPixelTypeEx(convert_param)
        self._raise_for_ret("convert pixel type", ret)

        image = np.ctypeslib.as_array(dst_buffer, shape=(convert_param.nDstLen,)).copy()
        if channel_count == 1:
            return image.reshape(height, width)
        return image.reshape(height, width, channel_count)

    def _safe_destroy_handle(self) -> None:
        if self._camera is None:
            return
        self._camera.MV_CC_DestroyHandle()
        self._camera = None

    def _set_enum_value_by_string(self, node_name: str, value: str, action: str) -> None:
        ret = self._camera.MV_CC_SetEnumValueByString(node_name, value)
        self._raise_for_ret(action, ret)

    def _try_set_enum_value_by_string(self, node_name: str, value: str) -> None:
        ret = self._camera.MV_CC_SetEnumValueByString(node_name, value)
        if ret == MV_OK:
            return

    def _try_set_bool_value(self, node_name: str, value: bool) -> None:
        ret = self._camera.MV_CC_SetBoolValue(node_name, value)
        if ret == MV_OK:
            return

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise HikCameraError("SDK is not initialized")

    def _ensure_opened(self) -> None:
        if not self._opened or self._camera is None:
            raise HikCameraError("camera is not open")

    def _raise_for_ret(self, action: str, ret: int) -> None:
        if ret != MV_OK:
            hint = ERROR_HINTS.get(ret)
            if hint:
                raise HikCameraError(f"{action} failed: {_to_hex_str(ret)}. {hint}")
            raise HikCameraError(f"{action} failed: {_to_hex_str(ret)}")

    @staticmethod
    def _format_ip_address(ip_value: int) -> str:
        return ".".join(
            [
                str((ip_value & 0xff000000) >> 24),
                str((ip_value & 0x00ff0000) >> 16),
                str((ip_value & 0x0000ff00) >> 8),
                str(ip_value & 0x000000ff),
            ]
        )
