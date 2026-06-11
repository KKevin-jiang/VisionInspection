from __future__ import annotations

import sys
import threading
import time
from ctypes import POINTER, byref, c_ubyte, cast, memset, sizeof, string_at
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import numpy as np


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
    MVCC_FLOATVALUE,
    MVCC_INTVALUE,
)
from MvCameraControl_class import MvCamera
from MvErrorDefine_const import MV_E_GC_TIMEOUT, MV_E_NODATA, MV_OK
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

    def set_external_trigger_mode(self, trigger_source: int = MV_TRIGGER_SOURCE_LINE0) -> None:
        self._ensure_opened()
        self._try_set_enum_value_by_string("AcquisitionMode", "Continuous")
        self._try_set_enum_value_by_string("TriggerSelector", "FrameStart")
        ret = self._camera.MV_CC_SetEnumValue("TriggerMode", 1)
        self._raise_for_ret("set trigger mode on", ret)
        ret = self._camera.MV_CC_SetEnumValue("TriggerSource", trigger_source)
        self._raise_for_ret("set trigger source", ret)
        self._try_set_enum_value_by_string("TriggerActivation", "RisingEdge")
        self._camera.MV_CC_ClearImageBuffer()

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

    def configure_output_line(self, line_name: str = "Line1", user_output_name: str = "UserOutput0") -> None:
        self._ensure_opened()
        self._set_enum_value_by_string("LineSelector", line_name, f"select output line {line_name}")
        self._set_enum_value_by_string("LineMode", "Output", f"set {line_name} output mode")
        self._set_enum_value_by_string("LineSource", user_output_name, f"set {line_name} source")
        self._set_enum_value_by_string("UserOutputSelector", user_output_name, f"select user output {user_output_name}")
        ret = self._camera.MV_CC_SetBoolValue("UserOutputValue", False)
        self._raise_for_ret("reset user output value", ret)

    def pulse_output_line(
        self,
        line_name: str = "Line1",
        pulse_ms: int = 50,
        delay_ms: int = 0,
        user_output_name: str = "UserOutput0",
    ) -> None:
        self._ensure_opened()
        self.configure_output_line(line_name=line_name, user_output_name=user_output_name)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        self._set_user_output_state(user_output_name=user_output_name, enabled=True)
        time.sleep(max(1, pulse_ms) / 1000.0)
        self._set_user_output_state(user_output_name=user_output_name, enabled=False)

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
        self._raise_for_ret("start grabbing", ret)
        self._grabbing = True

    def stop_grabbing(self) -> None:
        self._ensure_opened()
        if not self._grabbing:
            return
        ret = self._camera.MV_CC_StopGrabbing()
        self._raise_for_ret("stop grabbing", ret)
        self._grabbing = False

    def grab_frame(self, timeout_ms: int = 1000) -> CameraFrame:
        self._ensure_opened()
        if not self._grabbing:
            raise HikCameraError("camera is not grabbing")

        frame_out = MV_FRAME_OUT()
        memset(byref(frame_out), 0, sizeof(frame_out))
        ret = self._camera.MV_CC_GetImageBuffer(frame_out, timeout_ms)
        if ret in (MV_E_NODATA, MV_E_GC_TIMEOUT):
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

    def _set_user_output_state(self, user_output_name: str, enabled: bool) -> None:
        self._set_enum_value_by_string("UserOutputSelector", user_output_name, f"select user output {user_output_name}")
        ret = self._camera.MV_CC_SetBoolValue("UserOutputValue", enabled)
        self._raise_for_ret("set user output value", ret)

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
