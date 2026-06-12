from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .config import EXE_ICON_DIR

STATIC_EXE_ICON_DIR = EXE_ICON_DIR
ICON_EXTRACTION_TIMEOUT_SECONDS = 8
ICON_SIZE = 256
ICON_CACHE_VERSION = "png-normalized-v2"
_SHORTCUT_ICON_CACHE: dict[Path, Path] | None = None


def icon_url_for_exe(exe_path: str | None, process_name: str = "") -> str | None:
    """为 Windows exe 生成 Web 可用图标 URL。"""
    path = _existing_exe_path(exe_path)
    if path is None:
        return None

    icon_source = _shortcut_icon_source_for_exe(path) or path
    target = _cache_path_for_icon_source(icon_source, path, process_name)
    if not target.exists() or target.stat().st_size <= 0:
        if not _extract_png_icon_with_powershell(icon_source, target):
            _remove_partial(target)
            if icon_source != path:
                fallback = _cache_path_for_icon_source(path, path, process_name)
                if not fallback.exists() or fallback.stat().st_size <= 0:
                    if not _extract_png_icon_with_powershell(path, fallback):
                        _remove_partial(fallback)
                        return None
                target = fallback
            else:
                return None

    return "/static/exe-icons/" + target.name


def _existing_exe_path(exe_path: str | None) -> Path | None:
    if not exe_path:
        return None
    try:
        path = Path(exe_path).expanduser()
    except (OSError, ValueError):
        return None
    if path.suffix.lower() != ".exe":
        return None
    try:
        if not path.is_file():
            return None
    except OSError:
        return None
    return path


def _cache_path_for_exe(path: Path, process_name: str = "") -> Path:
    """兼容旧测试：返回当前 exe 图标 PNG 缓存路径。"""
    return _cache_path_for_icon_source(path, path, process_name)


def _cache_path_for_icon_source(icon_source: Path, exe_path: Path, process_name: str = "") -> Path:
    try:
        exe_stat = exe_path.stat()
        exe_stamp = f"{exe_stat.st_size}:{exe_stat.st_mtime_ns}"
    except OSError:
        exe_stamp = "unknown"
    try:
        source_stat = icon_source.stat()
        source_stamp = f"{source_stat.st_size}:{source_stat.st_mtime_ns}"
    except OSError:
        source_stamp = "unknown"
    key = f"{exe_path.resolve()}|{exe_stamp}|{icon_source.resolve()}|{source_stamp}|{ICON_CACHE_VERSION}|{ICON_SIZE}"
    digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]
    label = process_name or exe_path.stem or "app"
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-_.").lower()[:42] or "app"
    return STATIC_EXE_ICON_DIR / f"{safe_label}-{digest}.png"


def _shortcut_icon_source_for_exe(exe_path: Path) -> Path | None:
    mapping = _shortcut_icon_sources()
    try:
        return mapping.get(exe_path.resolve())
    except OSError:
        return None


def _shortcut_icon_sources() -> dict[Path, Path]:
    global _SHORTCUT_ICON_CACHE
    if _SHORTCUT_ICON_CACHE is not None:
        return _SHORTCUT_ICON_CACHE
    _SHORTCUT_ICON_CACHE = _scan_shortcut_icon_sources()
    return _SHORTCUT_ICON_CACHE


def _scan_shortcut_icon_sources() -> dict[Path, Path]:
    """扫描桌面和开始菜单 .lnk，建立 TargetPath -> IconLocation 映射。"""
    if os.name != "nt":
        return {}
    roots = _shortcut_roots()
    if not roots:
        return {}
    script = r'''
param([string[]]$roots)
$ErrorActionPreference = 'SilentlyContinue'
$shell = New-Object -ComObject WScript.Shell
foreach($root in $roots){
  if(-not (Test-Path -LiteralPath $root)){ continue }
  Get-ChildItem -LiteralPath $root -Filter *.lnk -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      $shortcut = $shell.CreateShortcut($_.FullName)
      if([string]::IsNullOrWhiteSpace($shortcut.TargetPath)){ return }
      $icon = $shortcut.IconLocation
      if([string]::IsNullOrWhiteSpace($icon)){ $icon = $shortcut.TargetPath }
      [pscustomobject]@{
        TargetPath = $shortcut.TargetPath
        IconLocation = $icon
        ShortcutPath = $_.FullName
      } | ConvertTo-Json -Compress
    } catch {}
  }
}
'''
    completed = _run_powershell_script(script, [str(root) for root in roots], timeout=12)
    if completed is None or completed.returncode != 0:
        return {}
    mapping: dict[Path, Path] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            import json

            item = json.loads(line)
        except Exception:
            continue
        target = _existing_exe_path(str(item.get("TargetPath") or ""))
        if target is None:
            continue
        icon_source = _icon_source_from_location(str(item.get("IconLocation") or ""), target)
        if icon_source is None:
            continue
        try:
            mapping.setdefault(target.resolve(), icon_source.resolve())
        except OSError:
            continue
    return mapping


def _shortcut_roots() -> list[Path]:
    candidates = [
        os.environ.get("USERPROFILE") and Path(os.environ["USERPROFILE"]) / "Desktop",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
        os.environ.get("APPDATA") and Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        os.environ.get("PROGRAMDATA") and Path(os.environ["PROGRAMDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    roots: list[Path] = []
    for candidate in candidates:
        if isinstance(candidate, Path) and candidate.exists():
            roots.append(candidate)
    return roots


def _icon_source_from_location(icon_location: str, fallback: Path) -> Path | None:
    raw = (icon_location or "").strip().strip('"')
    if not raw:
        return fallback
    # WScript.Shell 的 IconLocation 常见格式：C:\x\app.exe,0 或 "C:\x\app.ico",0。
    if "," in raw:
        raw = raw.rsplit(",", 1)[0].strip().strip('"')
    raw = os.path.expandvars(raw)
    try:
        path = Path(raw).expanduser()
    except (OSError, ValueError):
        return fallback
    if path.suffix.lower() not in {".exe", ".ico", ".dll"}:
        return fallback
    try:
        if not path.is_file():
            return fallback
    except OSError:
        return fallback
    return path


def _extract_png_icon_with_powershell(icon_source: Path, target: Path) -> bool:
    if os.name != "nt":
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    script = r'''
param(
  [Parameter(Mandatory=$true)][string]$source,
  [Parameter(Mandatory=$true)][string]$out,
  [int]$size = 256
)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
public struct SHFILEINFO
{
    public IntPtr hIcon;
    public int iIcon;
    public uint dwAttributes;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string szDisplayName;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=80)] public string szTypeName;
}

[ComImport]
[Guid("46EB5926-582E-4017-9FDF-E8998DAA0950")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IImageList
{
    [PreserveSig] int Add(IntPtr hbmImage, IntPtr hbmMask, ref int pi);
    [PreserveSig] int ReplaceIcon(int i, IntPtr hicon, ref int pi);
    [PreserveSig] int SetOverlayImage(int iImage, int iOverlay);
    [PreserveSig] int Replace(int i, IntPtr hbmImage, IntPtr hbmMask);
    [PreserveSig] int AddMasked(IntPtr hbmImage, int crMask, ref int pi);
    [PreserveSig] int Draw(IntPtr pimldp);
    [PreserveSig] int Remove(int i);
    [PreserveSig] int GetIcon(int i, int flags, out IntPtr picon);
}

public static class WinflowIconExport
{
    private const uint SHGFI_SYSICONINDEX = 0x000004000;
    private const uint SHGFI_ICON = 0x000000100;
    private const int SHIL_LARGE = 0;
    private const int SHIL_EXTRALARGE = 2;
    private const int SHIL_JUMBO = 4;
    private const int ILD_TRANSPARENT = 1;

    [DllImport("Shell32.dll", CharSet=CharSet.Unicode)]
    private static extern IntPtr SHGetFileInfo(string pszPath, uint dwFileAttributes, ref SHFILEINFO psfi, uint cbFileInfo, uint uFlags);

    [DllImport("Shell32.dll", EntryPoint="#727")]
    private static extern int SHGetImageList(int iImageList, ref Guid riid, out IImageList ppv);

    [DllImport("user32.dll", SetLastError=true)]
    private static extern bool DestroyIcon(IntPtr hIcon);

    public static void Save(string source, string target, int size)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(target));
        string ext = Path.GetExtension(source).ToLowerInvariant();
        if (ext == ".ico")
        {
            using (Icon icon = new Icon(source, size, size))
            using (Bitmap bitmap = icon.ToBitmap())
            {
                bitmap.Save(target, ImageFormat.Png);
            }
            return;
        }

        SHFILEINFO sfi = new SHFILEINFO();
        IntPtr res = SHGetFileInfo(source, 0, ref sfi, (uint)Marshal.SizeOf(typeof(SHFILEINFO)), SHGFI_SYSICONINDEX | SHGFI_ICON);
        if (res == IntPtr.Zero || sfi.iIcon < 0) throw new InvalidOperationException("SHGetFileInfo failed.");

        Guid iid = new Guid("46EB5926-582E-4017-9FDF-E8998DAA0950");
        IImageList imageList;
        int listSize = size >= 256 ? SHIL_JUMBO : (size >= 48 ? SHIL_EXTRALARGE : SHIL_LARGE);
        int hr = SHGetImageList(listSize, ref iid, out imageList);
        if (hr != 0 || imageList == null) throw new COMException("SHGetImageList failed.", hr);

        IntPtr hIcon;
        hr = imageList.GetIcon(sfi.iIcon, ILD_TRANSPARENT, out hIcon);
        if (hr != 0 || hIcon == IntPtr.Zero) throw new COMException("GetIcon failed.", hr);
        try
        {
            using (Icon icon = (Icon)Icon.FromHandle(hIcon).Clone())
            using (Bitmap bitmap = icon.ToBitmap())
            {
                bitmap.Save(target, ImageFormat.Png);
            }
        }
        finally
        {
            DestroyIcon(hIcon);
            if (sfi.hIcon != IntPtr.Zero) DestroyIcon(sfi.hIcon);
        }
    }
}
"@ -ReferencedAssemblies @('System.Drawing.dll','System.dll')
[WinflowIconExport]::Save($source, $out, $size)
'''
    completed = _run_powershell_script(script, [str(icon_source), str(target), str(ICON_SIZE)], timeout=ICON_EXTRACTION_TIMEOUT_SECONDS)
    ok = completed is not None and completed.returncode == 0 and target.exists() and target.stat().st_size > 0
    if ok:
        _normalize_png_icon_canvas(target)
    return ok


def _normalize_png_icon_canvas(
    path: Path,
    *,
    canvas_size: int = ICON_SIZE,
    target_ratio: float = 0.84,
    skip_ratio: float = 0.72,
) -> None:
    """把小图标从大透明画布里裁出、放大并居中。

    某些 Windows 应用只在 exe 中提供 32/48px 图标，Shell Jumbo ImageList 会把这个
    小图标放进 256px 透明画布里。前端按整张图缩放时，视觉上就会变得很小。
    这里只在非透明内容明显偏小时处理；Chrome/Codex 这类本来满幅的图标不会被动到。
    """
    try:
        from PIL import Image
    except Exception:
        # Pillow 不可用时保留原图，避免图标提取功能整体失败。
        return

    try:
        with Image.open(path) as source:
            image = source.convert("RGBA")
    except Exception:
        return

    if image.size != (canvas_size, canvas_size):
        image = image.resize((canvas_size, canvas_size), Image.Resampling.LANCZOS)

    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return

    content_width = bbox[2] - bbox[0]
    content_height = bbox[3] - bbox[1]
    if content_width <= 0 or content_height <= 0:
        return

    # 已经足够大的图标不处理，避免改变正常图标的留白和阴影。
    if max(content_width, content_height) >= canvas_size * skip_ratio:
        return

    cropped = image.crop(bbox)
    target_max = max(1, int(canvas_size * target_ratio))
    scale = min(target_max / content_width, target_max / content_height)
    new_size = (
        max(1, round(content_width * scale)),
        max(1, round(content_height * scale)),
    )

    resized = cropped.resize(new_size, Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    output.alpha_composite(
        resized,
        (
            (canvas_size - new_size[0]) // 2,
            (canvas_size - new_size[1]) // 2,
        ),
    )

    try:
        output.save(path)
    except Exception:
        pass


def _extract_icon_with_powershell(exe_path: Path, target: Path) -> bool:
    """兼容旧函数名：现在实际导出 PNG。"""
    return _extract_png_icon_with_powershell(exe_path, target)


def _run_powershell_script(script: str, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str] | None:
    script_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".ps1",
            prefix="winflow_ps_",
            delete=False,
        ) as script_file:
            script_file.write(script)
            script_path = Path(script_file.name)
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                *args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if script_path is not None:
            _remove_partial(script_path)


def _remove_partial(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
