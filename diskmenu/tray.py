"""Windows 系统托盘图标与设备事件消息循环（ctypes 实现，无第三方依赖）。"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional

from .paths import APP_TITLE, app_data_dir, icon_path

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

LRESULT = ctypes.c_ssize_t

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_DEVICECHANGE = 0x0219
WM_APP = 0x8000
WM_CONTEXTMENU = 0x007B
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
NIN_SELECT = 0x0400

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4
NIF_MESSAGE = 0x0001
NIF_ICON = 0x0002
NIF_TIP = 0x0004
NIF_INFO = 0x0010
NIIF_INFO = 0x0001
NOTIFYICON_VERSION_4 = 4

DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004
DEVICE_NOTIFY_WINDOW_HANDLE = 0x0000
DBT_DEVTYP_DEVICEINTERFACE = 0x0005

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
IDI_APPLICATION = 32512
HWND_MESSAGE = -3


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


GUID_DEVINTERFACE_VOLUME = GUID(
    0x53F5630D,
    0xB6BF,
    0x11D0,
    (ctypes.c_ubyte * 8)(0x94, 0xF2, 0x00, 0xA0, 0xC9, 0x1E, 0xFB, 0x8B),
)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [
        ("dbch_size", wintypes.DWORD),
        ("dbch_devicetype", wintypes.DWORD),
        ("dbch_reserved", wintypes.DWORD),
    ]


class DEV_BROADCAST_DEVICEINTERFACE_W(ctypes.Structure):
    _fields_ = [
        ("dbcc_size", wintypes.DWORD),
        ("dbcc_devicetype", wintypes.DWORD),
        ("dbcc_reserved", wintypes.DWORD),
        ("dbcc_classguid", GUID),
        ("dbcc_name", wintypes.WCHAR * 1),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


def _configure_winapi() -> None:
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.PostQuitMessage.restype = None
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.LPRECT,
    ]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.RegisterDeviceNotificationW.restype = wintypes.HANDLE
    user32.RegisterDeviceNotificationW.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


_configure_winapi()


class TrayIcon:
    """托盘图标 + 隐藏消息窗口。必须在 Windows 上使用。"""

    def __init__(
        self,
        title: str = APP_TITLE,
        on_open: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_device_change: Optional[Callable[[], None]] = None,
    ) -> None:
        self.title = title
        self.on_open = on_open
        self.on_quit = on_quit
        self.on_device_change = on_device_change
        self._hwnd: Optional[int] = None
        self._nid: Optional[NOTIFYICONDATAW] = None
        self._thread: Optional[threading.Thread] = None
        self._icon_handle = None
        self._wndproc = WNDPROC(self._window_proc)
        self._callback_message = WM_APP + 1
        self._class_atom = None
        self._dev_notify_handle = None
        self._last_open_time = 0.0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self.run, name="DiskMenu-tray", daemon=True)
        self._thread.start()

    def run(self) -> None:
        try:
            self._create_window()
            self._add_icon()
            self._register_device_notifications()
            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            self._remove_icon()
            if self._hwnd:
                user32.DestroyWindow(self._hwnd)
                self._hwnd = None
        except Exception as exc:
            self._log_error(f"托盘线程异常：{exc}")
            raise

    def stop(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    def notify(self, title: str, message: str) -> None:
        if self._nid is None:
            return
        try:
            nid = self._nid
            nid.uFlags = NIF_INFO
            nid.szInfoTitle = (title or APP_TITLE)[:63]
            nid.szInfo = (message or "")[:255]
            nid.dwInfoFlags = NIIF_INFO
            nid.uTimeoutOrVersion = 5000
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            pass

    def _log_error(self, text: str) -> None:
        try:
            log_path = app_data_dir() / "error.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass

    # ---------------- internals ----------------

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DEVICECHANGE:
            if wparam in (DBT_DEVICEARRIVAL, DBT_DEVICEREMOVECOMPLETE):
                if self.on_device_change:
                    try:
                        self.on_device_change()
                    except Exception:
                        pass
            return 0
        if msg == self._callback_message:
            # Shell_NotifyIcon 把鼠标事件包装在回调消息里，lParam 低 16 位是具体通知
            code = lparam & 0xFFFF
            if code in (WM_CONTEXTMENU, WM_RBUTTONUP):
                self._show_menu()
                return 0
            if code in (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_SELECT):
                self._open_gui()
                return 0
            return 0
        if msg in (WM_CONTEXTMENU, WM_RBUTTONUP):
            self._show_menu()
            return 0
        if msg == WM_LBUTTONDBLCLK:
            self._open_gui()
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _open_gui(self) -> None:
        if self.on_open:
            now = time.time()
            if now - self._last_open_time < 0.8:
                return
            self._last_open_time = now
            try:
                self.on_open()
            except Exception:
                pass

    def _create_window(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        class_name = "DiskMenuTrayWindow"
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = class_name
        self._class_atom = user32.RegisterClassW(ctypes.byref(wc))
        if self._class_atom == 0:
            raise ctypes.WinError()
        self._hwnd = user32.CreateWindowExW(
            0,
            class_name,
            self.title,
            0,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            None,
            hinst,
            None,
        )
        if not self._hwnd:
            raise ctypes.WinError()

    def _add_icon(self) -> None:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_APP + 1
        nid.hIcon = self._load_icon()
        nid.szTip = self.title[:127]
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            self._log_error(f"Shell_NotifyIcon NIM_ADD 失败：{kernel32.GetLastError()}")
            return
        nid.uTimeoutOrVersion = NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
        self._nid = nid

    def _load_icon(self):
        try:
            path = str(icon_path())
            if path and os.path.exists(path):
                handle = user32.LoadImageW(
                    None,
                    path,
                    IMAGE_ICON,
                    0,
                    0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE,
                )
                if handle:
                    return handle
        except Exception:
            pass
        return user32.LoadIconW(None, IDI_APPLICATION)

    def _register_device_notifications(self) -> None:
        dbi = DEV_BROADCAST_DEVICEINTERFACE_W()
        dbi.dbcc_size = ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE_W)
        dbi.dbcc_devicetype = DBT_DEVTYP_DEVICEINTERFACE
        dbi.dbcc_reserved = 0
        dbi.dbcc_classguid = GUID_DEVINTERFACE_VOLUME
        self._dev_notify_handle = user32.RegisterDeviceNotificationW(
            self._hwnd,
            ctypes.byref(dbi),
            DEVICE_NOTIFY_WINDOW_HANDLE,
        )

    def _remove_icon(self) -> None:
        if self._nid is not None:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            self._nid = None

    def _show_menu(self) -> None:
        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            pt.x = 0
            pt.y = 0
        x = int(pt.x)
        y = int(pt.y)
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        user32.AppendMenuW(menu, MF_STRING, 1, "打开主界面")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, 2, "退出")
        cmd = user32.TrackPopupMenu(
            menu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            x,
            y,
            0,
            self._hwnd,
            None,
        )
        user32.DestroyMenu(menu)
        if cmd == 1 and self.on_open:
            try:
                self.on_open()
            except Exception:
                pass
        elif cmd == 2 and self.on_quit:
            try:
                self.on_quit()
            except Exception:
                pass
