"""基于命名互斥量的单实例检测。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183

kernel32 = ctypes.windll.kernel32
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.ReleaseMutex.restype = wintypes.BOOL
kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class SingleInstance:
    def __init__(self, name: str = "CatalogExporterV2App") -> None:
        self._name = f"Local\\{name}"
        self._handle = None

    def acquire(self) -> bool:
        """尝试获取互斥量。返回 True 表示本进程是第一个实例。"""
        self._handle = kernel32.CreateMutexW(None, False, self._name)
        error = ctypes.windll.kernel32.GetLastError()
        if error == ERROR_ALREADY_EXISTS:
            if self._handle:
                kernel32.CloseHandle(self._handle)
                self._handle = None
            return False
        return True

    def release(self) -> None:
        if self._handle:
            kernel32.ReleaseMutex(self._handle)
            kernel32.CloseHandle(self._handle)
            self._handle = None

    @staticmethod
    def is_running(name: str = "CatalogExporterV2App") -> bool:
        """不占用互斥量，仅探测是否已有实例在运行。"""
        handle = kernel32.CreateMutexW(None, False, f"Local\\{name}")
        error = ctypes.windll.kernel32.GetLastError()
        if handle:
            kernel32.CloseHandle(handle)
        return error == ERROR_ALREADY_EXISTS
