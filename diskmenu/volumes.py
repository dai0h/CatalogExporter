"""Windows 卷枚举与“是否自动扫描”判断。只使用系统 API，不依赖第三方库。"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional

DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6

_EXTERNAL_CACHE: dict = {"time": 0.0, "map": None}


def invalidate_external_cache() -> None:
    _EXTERNAL_CACHE["time"] = 0.0
    _EXTERNAL_CACHE["map"] = None


def _query_fixed_drive_interfaces() -> Optional[dict[str, dict]]:
    """通过 WMI 查询盘符 -> 物理接口类型的映射。
    查询失败返回 None；查询成功但结果为空也返回 None（视为未知，交给启发式规则）。"""
    now = time.time()
    if now - _EXTERNAL_CACHE["time"] < 60:
        return _EXTERNAL_CACHE["map"]
    script = r"""
$rows = @()
Get-PhysicalDisk | ForEach-Object {
  $pd = $_
  Get-Partition -DiskNumber $pd.DeviceId -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter } | ForEach-Object {
    $rows += [pscustomobject]@{ Drive = "$($_.DriveLetter):"; Interface = $pd.BusType }
  }
}
$rows | ConvertTo-Json -Compress
"""
    drive_map: Optional[dict[str, dict]] = None
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            if isinstance(data, dict):
                data = [data]
            if data:
                drive_map = {}
                for item in data:
                    drive = (item.get("Drive") or "").strip().upper().rstrip("\\")
                    if drive:
                        drive_map[drive] = {
                            "interface": (item.get("Interface") or "").strip().lower(),
                            "pnp": "",
                        }
    except Exception:
        drive_map = None
    _EXTERNAL_CACHE["time"] = now
    _EXTERNAL_CACHE["map"] = drive_map
    return drive_map


def drive_is_usb(drive: str) -> bool:
    """判断盘符是否为 USB 外接。只认 USB/1394/Thunderbolt 接口或 PNP 设备 ID 以 USB 开头的盘，
    避免把报成 SCSI 的 M.2/NVMe 误判为 USB。查询失败时返回 False。"""
    drive_map = _query_fixed_drive_interfaces()
    if drive_map is None:
        return False
    info = drive_map.get(drive.upper().rstrip("\\"))
    if info is None:
        return False
    interface = info["interface"]
    pnp = info["pnp"]
    if interface in {"usb", "ieee 1394", "1394", "thunderbolt", "esata"}:
        return True
    return pnp.startswith("USB")


@dataclass
class VolumeInfo:
    drive: str                # 如 "E:"
    volume_guid: str          # 如 \\?\Volume{...}\，稳定标识
    label: str
    serial: str
    file_system: str
    total: int
    free: int
    drive_type: int

    @property
    def disk_id(self) -> str:
        if self.volume_guid:
            return self.volume_guid
        if self.serial:
            return f"vol:{self.serial}"
        return f"drive:{self.drive.replace(':', '')}"

    def display_name(self) -> str:
        label = self.label.strip()
        if label:
            return f"{label} ({self.drive})"
        return f"{self.drive} 卷"


def list_volumes() -> list[VolumeInfo]:
    """枚举当前所有带盘符的卷。"""
    kernel32 = ctypes.windll.kernel32
    mask = kernel32.GetLogicalDrives()
    result: list[VolumeInfo] = []
    for i in range(26):
        if not (mask & (1 << i)):
            continue
        letter = chr(ord("A") + i)
        drive = f"{letter}:"
        root = drive + "\\"

        drive_type = kernel32.GetDriveTypeW(root)
        if drive_type in (DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR):
            continue

        name_buf = ctypes.create_unicode_buffer(261)
        serial = wintypes.DWORD(0)
        max_len = wintypes.DWORD(0)
        flags = wintypes.DWORD(0)
        fs_buf = ctypes.create_unicode_buffer(261)
        ok = kernel32.GetVolumeInformationW(
            root,
            name_buf,
            len(name_buf),
            ctypes.byref(serial),
            ctypes.byref(max_len),
            ctypes.byref(flags),
            fs_buf,
            len(fs_buf),
        )

        guid_buf = ctypes.create_unicode_buffer(100)
        guid_ok = kernel32.GetVolumeNameForVolumeMountPointW(root, guid_buf, len(guid_buf))

        total = ctypes.c_ulonglong(0)
        free = ctypes.c_ulonglong(0)
        if not kernel32.GetDiskFreeSpaceExW(root, None, ctypes.byref(total), ctypes.byref(free)):
            total.value = 0
            free.value = 0

        result.append(
            VolumeInfo(
                drive=drive,
                volume_guid=guid_buf.value if guid_ok else "",
                label=name_buf.value if ok else "",
                serial=f"{serial.value:08X}" if ok else "",
                file_system=fs_buf.value if ok else "",
                total=int(total.value),
                free=int(free.value),
                drive_type=int(drive_type),
            )
        )
    return result


def system_drive() -> str:
    return (os.environ.get("SystemDrive") or "C:").upper().rstrip("\\")


def is_eligible(info: VolumeInfo, settings: dict[str, str], app_drive: Optional[str] = None) -> bool:
    """判断一块卷是否应该自动扫描。默认扫描所有本地盘（固定盘 + 可移动盘）。
    用户可在设置里勾掉对应选项，或用“忽略的盘符”排除个别盘。"""
    if info.drive_type not in (DRIVE_REMOVABLE, DRIVE_FIXED):
        return False

    drive = info.drive.upper()
    ignore = {x.strip().upper().rstrip("\\") for x in settings.get("ignore_drives", "").split(",") if x.strip()}
    if drive in ignore:
        return False
    extra = {x.strip().upper().rstrip("\\") for x in settings.get("extra_external", "").split(",") if x.strip()}
    if drive in extra:
        return True
    if info.drive_type == DRIVE_REMOVABLE and settings.get("scan_removable", "1") != "1":
        return False
    if info.drive_type == DRIVE_FIXED and settings.get("scan_fixed_new", "1") != "1":
        return False
    return True


def mounted_drive(conn_any=None) -> str:
    """返回程序所在盘符（通常与数据目录同盘），用于排除自身。"""
    try:
        from .paths import app_data_dir

        return str(app_data_dir().anchor).rstrip("\\")
    except Exception:
        return ""
