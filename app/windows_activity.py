from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import MAX_WINDOW_TITLE_LENGTH

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
psapi.GetModuleBaseNameW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
psapi.GetModuleBaseNameW.restype = wintypes.DWORD


@dataclass(frozen=True)
class ForegroundWindow:
    hwnd: int
    pid: int
    title: str
    process_name: str
    exe_path: Optional[str]


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    title = buffer.value.strip()
    if len(title) > MAX_WINDOW_TITLE_LENGTH:
        title = title[:MAX_WINDOW_TITLE_LENGTH] + "…"
    return title


def _get_process_path(pid: int) -> Optional[str]:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def _get_process_name(pid: int, exe_path: Optional[str]) -> str:
    if exe_path:
        return Path(exe_path).name
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return f"pid:{pid}"
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        copied = psapi.GetModuleBaseNameW(handle, None, buffer, 1024)
        if copied:
            return buffer.value
    finally:
        kernel32.CloseHandle(handle)
    return f"pid:{pid}"


def get_foreground_window() -> Optional[ForegroundWindow]:
    """获取当前前台窗口。失败时返回 None，不抛出异常。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return None
    title = _get_window_title(hwnd)
    exe_path = _get_process_path(pid.value)
    process_name = _get_process_name(pid.value, exe_path)
    return ForegroundWindow(
        hwnd=int(hwnd),
        pid=int(pid.value),
        title=title,
        process_name=process_name,
        exe_path=exe_path,
    )
