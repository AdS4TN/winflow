from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PACKAGE_DATA = (
    "app/static/icons/apps/chrome.svg",
    "app/static/icons/apps/vscode.svg",
    "app/static/icons/apps/terminal.svg",
)


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        print(result.stdout)
        fail(f"命令失败：{' '.join(args)}")
    return result


def copy_source_tree(temp_root: Path) -> Path:
    """复制一份最小源码树用于构建，避免 pip wheel 污染当前工作区。"""

    source_root = temp_root / "source"
    ignore = shutil.ignore_patterns(
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
        "*.egg-info",
        "data",
        "logs",
        "docs/internal",
        "static/exe-icons/*.png",
        "static/exe-icons/*.ico",
        ".env",
        ".env.*",
        "winflow-uploader*.log",
    )
    shutil.copytree(ROOT, source_root, ignore=ignore)
    return source_root


def build_wheel(source_root: Path, temp_root: Path) -> Path:
    wheel_dir = temp_root / "wheelhouse"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(source_root),
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=source_root,
    )
    wheels = sorted(wheel_dir.glob("*.whl"))
    if not wheels:
        fail("未生成 wheel")
    return wheels[0]


def assert_wheel_contents(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = sorted(archive.namelist())

    missing = [item for item in REQUIRED_PACKAGE_DATA if item not in names]
    if missing:
        fail(f"wheel 缺少内置静态资源：{', '.join(missing)}")

    forbidden = [
        name
        for name in names
        if name.startswith("data/")
        or name.startswith("logs/")
        or name.startswith("static/exe-icons/")
        or name.endswith(".sqlite")
        or name.endswith(".sqlite-wal")
        or name.endswith(".sqlite-shm")
        or name.endswith(".log")
        or name == ".env"
    ]
    if forbidden:
        fail(f"wheel 包含运行时私有产物：{', '.join(forbidden[:10])}")


def assert_installed_runtime_paths(wheel: Path, temp_root: Path) -> None:
    venv = temp_root / "venv"
    run([sys.executable, "-m", "venv", str(venv)], cwd=temp_root)
    python = venv / "Scripts" / "python.exe"
    if not python.is_file():
        fail("临时 venv 缺少 python.exe")

    # 审计目标是验证 Winflow wheel 的 package data、入口和路径语义。
    # 不在临时 venv 里解析第三方依赖，避免 CI 因网络或镜像波动失败。
    run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], cwd=temp_root)

    run_dir = temp_root / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    local_app_data = temp_root / "LocalAppData"
    env = {**os.environ, "LOCALAPPDATA": str(local_app_data)}

    run([str(python), "-m", "app.main", "--help"], cwd=run_dir, env=env)

    script = rf"""
from pathlib import Path
from app.config import DATA_DIR, EXE_ICON_DIR, PACKAGE_STATIC_DIR
from app.web import static_file_for_request

repo = Path({str(ROOT)!r}).resolve()
data_dir = DATA_DIR.resolve()
exe_icon_dir = EXE_ICON_DIR.resolve()
if repo in [data_dir, *data_dir.parents]:
    raise SystemExit(f"DATA_DIR points into source tree: {{data_dir}}")
if repo in [exe_icon_dir, *exe_icon_dir.parents]:
    raise SystemExit(f"EXE_ICON_DIR points into source tree: {{exe_icon_dir}}")
if not str(data_dir).startswith({str(local_app_data)!r}):
    raise SystemExit(f"DATA_DIR should use LOCALAPPDATA in installed mode: {{data_dir}}")
if not str(exe_icon_dir).startswith({str(local_app_data)!r}):
    raise SystemExit(f"EXE_ICON_DIR should use LOCALAPPDATA in installed mode: {{exe_icon_dir}}")
if not PACKAGE_STATIC_DIR.exists():
    raise SystemExit(f"PACKAGE_STATIC_DIR missing: {{PACKAGE_STATIC_DIR}}")
static_file = static_file_for_request('/static/icons/apps/chrome.svg')
if static_file is None or not static_file.is_file():
    raise SystemExit("installed static route cannot resolve chrome.svg")
if static_file_for_request('/static/../README.md') is not None:
    raise SystemExit("static route allowed directory traversal")
"""
    run([str(python), "-c", script], cwd=run_dir, env=env)


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="winflow_package_audit_"))
    try:
        source_root = copy_source_tree(temp_root)
        wheel = build_wheel(source_root, temp_root)
        assert_wheel_contents(wheel)
        assert_installed_runtime_paths(wheel, temp_root)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    print("[OK] package audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
