"""Transporte HID nativo para Windows usando únicamente DLLs del sistema.

Utiliza ``hid.dll``, ``setupapi.dll`` y ``kernel32.dll`` (incluidas en toda
instalación de Windows 10/11) a través de ``ctypes``.

Ventajas frente a ``pydualsense``/``pyhidapi``:
- No requiere descargar ni colocar ``hidapi.dll`` manualmente.
- No requiere compilar extensiones C ni Visual Studio Build Tools.
- Ajusta automáticamente el tamaño del informe de salida a
  ``HIDP_CAPS.OutputReportByteLength`` (en Windows USB suele ser 48 bytes para
  DualSense), evitando errores de tamaño de búfer en ``WriteFile``.
- Usa I/O asíncrono (``FILE_FLAG_OVERLAPPED``) para permitir lectura continua
  y escritura concurrente sin bloqueos al cerrar el dispositivo.
"""

from __future__ import annotations

import ctypes
import struct
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass
class HidDeviceInfo:
    path: str
    vendor_id: int
    product_id: int
    version_number: int
    usage_page: int
    usage: int
    input_report_length: int
    output_report_length: int
    connection_type: str = "USB"  # "USB" | "BT"


if sys.platform == "win32":
    from ctypes import wintypes

    _IS_64BIT = ctypes.sizeof(ctypes.c_void_p) == 8
    _ULONG_PTR = ctypes.c_uint64 if _IS_64BIT else ctypes.c_uint32
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    _DIGCF_PRESENT = 0x00000002
    _DIGCF_DEVICEINTERFACE = 0x00000010

    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _OPEN_EXISTING = 3
    _FILE_FLAG_OVERLAPPED = 0x40000000

    _ERROR_IO_PENDING = 997
    _WAIT_OBJECT_0 = 0
    _HIDP_STATUS_SUCCESS = 0x00110000

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        if not _IS_64BIT:
            _pack_ = 1
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("InterfaceClassGuid", _GUID),
            ("Flags", wintypes.DWORD),
            ("Reserved", _ULONG_PTR),
        ]

    class _HIDD_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("Size", wintypes.DWORD),
            ("VendorID", wintypes.USHORT),
            ("ProductID", wintypes.USHORT),
            ("VersionNumber", wintypes.USHORT),
        ]

    class _HIDP_CAPS(ctypes.Structure):
        _fields_ = [
            ("Usage", wintypes.USHORT),
            ("UsagePage", wintypes.USHORT),
            ("InputReportByteLength", wintypes.USHORT),
            ("OutputReportByteLength", wintypes.USHORT),
            ("FeatureReportByteLength", wintypes.USHORT),
            ("Reserved", wintypes.USHORT * 17),
            ("NumberLinkCollectionNodes", wintypes.USHORT),
            ("NumberInputButtonCaps", wintypes.USHORT),
            ("NumberInputValueCaps", wintypes.USHORT),
            ("NumberInputDataIndices", wintypes.USHORT),
            ("NumberOutputButtonCaps", wintypes.USHORT),
            ("NumberOutputValueCaps", wintypes.USHORT),
            ("NumberOutputDataIndices", wintypes.USHORT),
            ("NumberFeatureButtonCaps", wintypes.USHORT),
            ("NumberFeatureValueCaps", wintypes.USHORT),
            ("NumberFeatureDataIndices", wintypes.USHORT),
        ]

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [
            ("Internal", _ULONG_PTR),
            ("InternalHigh", _ULONG_PTR),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _hid = ctypes.WinDLL("hid", use_last_error=True)
    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # hid.dll
    _hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(_GUID)]
    _hid.HidD_GetHidGuid.restype = None

    _hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(_HIDD_ATTRIBUTES)]
    _hid.HidD_GetAttributes.restype = wintypes.BOOLEAN

    _hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    _hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN

    _hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    _hid.HidD_FreePreparsedData.restype = wintypes.BOOLEAN

    _hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(_HIDP_CAPS)]
    _hid.HidP_GetCaps.restype = ctypes.c_long

    _hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    _hid.HidD_GetFeature.restype = wintypes.BOOLEAN

    # setupapi.dll
    _setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD,
    ]
    _setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p

    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_GUID),
        wintypes.DWORD, ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
    ]
    _setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    _setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    # kernel32.dll
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE

    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_OVERLAPPED),
    ]
    _kernel32.ReadFile.restype = wintypes.BOOL

    _kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_OVERLAPPED),
    ]
    _kernel32.WriteFile.restype = wintypes.BOOL

    _kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR,
    ]
    _kernel32.CreateEventW.restype = wintypes.HANDLE

    _kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
    _kernel32.ResetEvent.restype = wintypes.BOOL

    _kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    _kernel32.SetEvent.restype = wintypes.BOOL

    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD

    _kernel32.WaitForMultipleObjects.argtypes = [
        wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD,
    ]
    _kernel32.WaitForMultipleObjects.restype = wintypes.DWORD

    _kernel32.GetOverlappedResult.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED),
        ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
    ]
    _kernel32.GetOverlappedResult.restype = wintypes.BOOL

    _kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED)]
    _kernel32.CancelIoEx.restype = wintypes.BOOL


def enumerate_devices(vendor_id: int, product_ids: Sequence[int]) -> List[HidDeviceInfo]:
    """Enumera dispositivos HID conectados que coincidan con VID y PID en Windows."""
    if sys.platform != "win32":
        return []

    guid = _GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))

    dev_info = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE,
    )
    if not dev_info or dev_info == _INVALID_HANDLE_VALUE:
        return []

    found: List[HidDeviceInfo] = []
    try:
        index = 0
        cb_detail = 8 if _IS_64BIT else 6
        while True:
            iface_data = _SP_DEVICE_INTERFACE_DATA()
            iface_data.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(
                dev_info, None, ctypes.byref(guid), index, ctypes.byref(iface_data),
            ):
                break
            index += 1

            required_size = wintypes.DWORD(0)
            _setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(iface_data), None, 0, ctypes.byref(required_size), None,
            )
            if required_size.value <= 4:
                continue

            buf = ctypes.create_string_buffer(required_size.value)
            struct.pack_into("<I", buf, 0, cb_detail)
            if not _setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(iface_data), buf, required_size.value, None, None,
            ):
                continue

            path = buf.raw[4:required_size.value].decode("utf-16-le", errors="ignore").split("\x00", 1)[0]
            if not path:
                continue

            # Abrir con acceso 0 permite consultar atributos incluso si otro proceso lo tiene abierto.
            handle = _kernel32.CreateFileW(
                path, 0, _FILE_SHARE_READ | _FILE_SHARE_WRITE, None, _OPEN_EXISTING, 0, None,
            )
            if not handle or handle == _INVALID_HANDLE_VALUE:
                continue

            try:
                attrs = _HIDD_ATTRIBUTES()
                attrs.Size = ctypes.sizeof(_HIDD_ATTRIBUTES)
                if not _hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
                    continue
                if attrs.VendorID != vendor_id or attrs.ProductID not in product_ids:
                    continue

                usage_page = 0
                usage = 0
                in_len = 64
                out_len = 48
                preparsed = ctypes.c_void_p()
                if _hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
                    try:
                        caps = _HIDP_CAPS()
                        if _hid.HidP_GetCaps(preparsed, ctypes.byref(caps)) == _HIDP_STATUS_SUCCESS:
                            usage_page = int(caps.UsagePage)
                            usage = int(caps.Usage)
                            in_len = int(caps.InputReportByteLength)
                            out_len = int(caps.OutputReportByteLength)
                    finally:
                        _hid.HidD_FreePreparsedData(preparsed)

                is_bt = (in_len >= 78 or out_len >= 78 or "bth" in path.lower() or "00001124" in path.lower())
                found.append(
                    HidDeviceInfo(
                        path=path,
                        vendor_id=int(attrs.VendorID),
                        product_id=int(attrs.ProductID),
                        version_number=int(attrs.VersionNumber),
                        usage_page=usage_page,
                        usage=usage,
                        input_report_length=in_len,
                        output_report_length=out_len,
                        connection_type="BT" if is_bt else "USB",
                    )
                )
            finally:
                _kernel32.CloseHandle(handle)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(dev_info)

    # Priorizar interfaz Gamepad USB (UsagePage=1, Usage=5, InputReportByteLength=64)
    found.sort(
        key=lambda d: (
            0 if (d.usage_page == 0x01 and d.usage == 0x05) else 1,
            0 if d.input_report_length in (64, 78) else 1,
        )
    )
    return found


class Win32HidDevice:
    """Envoltorio de bajo nivel sobre un handle HID abierto con OVERLAPPED I/O."""

    def __init__(self, info: HidDeviceInfo) -> None:
        if sys.platform != "win32":
            raise OSError("Win32HidDevice solo está disponible en Windows")

        self.info = info
        self.connection_type = info.connection_type
        default_in = 78 if info.connection_type == "BT" else 64
        default_out = 78 if info.connection_type == "BT" else 48
        self.input_report_length = max(default_in, info.input_report_length)
        self.output_report_length = info.output_report_length if info.output_report_length > 0 else default_out
        self._write_lock = threading.Lock()
        self._closed = False

        handle = _kernel32.CreateFileW(
            info.path,
            _GENERIC_READ | _GENERIC_WRITE,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_OVERLAPPED,
            None,
        )
        if not handle or handle == _INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            raise OSError(f"No se pudo abrir el dispositivo HID (Win32 error {err})")

        self._handle = handle
        self._read_event = _kernel32.CreateEventW(None, True, False, None)
        self._write_event = _kernel32.CreateEventW(None, True, False, None)
        self._stop_event = _kernel32.CreateEventW(None, True, False, None)

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        """Lee un Feature Report HID (necesario en Bluetooth: Report 0x05 desbloquea modo 0x31)."""
        if self._closed or not self._handle:
            return b""
        buf = ctypes.create_string_buffer(length)
        buf[0] = bytes([report_id])
        ok = _hid.HidD_GetFeature(self._handle, buf, length)
        if not ok:
            return b""
        return bytes(buf.raw[:length])

    def read(self, timeout_ms: int = 100) -> bytes:
        if self._closed:
            return b""

        _kernel32.ResetEvent(self._read_event)
        ov = _OVERLAPPED()
        ov.hEvent = self._read_event

        buf = ctypes.create_string_buffer(self.input_report_length)
        bytes_read = wintypes.DWORD(0)

        ok = _kernel32.ReadFile(
            self._handle, buf, self.input_report_length,
            ctypes.byref(bytes_read), ctypes.byref(ov),
        )
        if not ok:
            err = ctypes.get_last_error()
            if err != _ERROR_IO_PENDING:
                raise OSError(f"Error al leer del DualSense (Win32 error {err})")

            handles = (wintypes.HANDLE * 2)(self._read_event, self._stop_event)
            wait = _kernel32.WaitForMultipleObjects(2, handles, False, timeout_ms)
            if wait == _WAIT_OBJECT_0:
                if not _kernel32.GetOverlappedResult(
                    self._handle, ctypes.byref(ov), ctypes.byref(bytes_read), False,
                ):
                    err2 = ctypes.get_last_error()
                    raise OSError(f"Error al completar lectura HID (Win32 error {err2})")
            else:
                _kernel32.CancelIoEx(self._handle, ctypes.byref(ov))
                _kernel32.GetOverlappedResult(
                    self._handle, ctypes.byref(ov), ctypes.byref(bytes_read), True,
                )
                return b""

        return bytes(buf.raw[:bytes_read.value])

    def write(self, data: bytes, timeout_ms: int = 500) -> int:
        if self._closed:
            raise OSError("El dispositivo HID está cerrado")

        target_len = self.output_report_length
        if len(data) < target_len:
            payload = data + bytes(target_len - len(data))
        elif len(data) > target_len:
            payload = data[:target_len]
        else:
            payload = data

        with self._write_lock:
            if self._closed:
                raise OSError("El dispositivo HID está cerrado")

            _kernel32.ResetEvent(self._write_event)
            ov = _OVERLAPPED()
            ov.hEvent = self._write_event

            buf = ctypes.create_string_buffer(payload, target_len)
            written = wintypes.DWORD(0)

            ok = _kernel32.WriteFile(
                self._handle, buf, target_len,
                ctypes.byref(written), ctypes.byref(ov),
            )
            if not ok:
                err = ctypes.get_last_error()
                if err != _ERROR_IO_PENDING:
                    raise OSError(f"Error al escribir al DualSense (Win32 error {err})")

                wait = _kernel32.WaitForSingleObject(self._write_event, timeout_ms)
                if wait == _WAIT_OBJECT_0:
                    if not _kernel32.GetOverlappedResult(
                        self._handle, ctypes.byref(ov), ctypes.byref(written), False,
                    ):
                        err2 = ctypes.get_last_error()
                        raise OSError(f"Error al completar escritura HID (Win32 error {err2})")
                else:
                    _kernel32.CancelIoEx(self._handle, ctypes.byref(ov))
                    raise OSError("Tiempo de espera agotado al enviar datos al DualSense")

            return int(written.value)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._stop_event:
            _kernel32.SetEvent(self._stop_event)
        if self._handle:
            _kernel32.CancelIoEx(self._handle, None)
            _kernel32.CloseHandle(self._handle)
            self._handle = None
        for ev_name in ("_read_event", "_write_event", "_stop_event"):
            ev = getattr(self, ev_name, None)
            if ev:
                _kernel32.CloseHandle(ev)
                setattr(self, ev_name, None)
