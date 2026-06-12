from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PUBLIC_FILES = (
    "README.md",
    "LICENSE",
    "PRIVACY.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "ROADMAP.md",
    ".env.example",
    ".gitattributes",
    ".github/workflows/ci.yml",
    "docs/ARCHITECTURE.md",
    "docs/TROUBLESHOOTING.md",
    "docs/GITHUB_RELEASE_GUIDE.md",
    "docs/API_SCHEMA.md",
    "docs/UPLOAD_API.md",
    "docs/RELEASE_CHECKLIST.md",
)

FORBIDDEN_PUBLIC_PATHS = (
    "app/browser_history.py",
    "static/icons/sites",
)

REQUIRED_CHECK_COMMANDS = (
    "python -m compileall -q app tests scripts",
    "python -m unittest discover -s tests",
    "python scripts/release_audit.py",
    "python scripts/package_audit.py",
)

FORBIDDEN_IMPLEMENTATION_TERMS = (
    "browser_history",
    "browser_visit_rows",
    "BrowserVisit",
    "insert_browser_visits",
    "fetch_browser_visits",
    "WINFLOW_HISTORY_DAYS",
    "normalize_browser_rows",
    "icon_for_site",
    "event_type=\"web\"",
    "event_type = \"web\"",
    "ScreenCaptureKit",
    "AVFoundation",
    "NSWorkspace",
    "CGWindow",
    "AppleScript",
    "CoreGraphics",
    "Quartz",
    "AppKit",
)

FORBIDDEN_PUBLIC_RESIDUE_TERMS = (
    "Agent A",
    "等待 Agent",
    "生产代码尚未合入",
    "subagent",
    "getMockTimelineBands",
    "mockTs",
    "buildMockTimelineRange",
    "mockDurationLabel",
    "mockBandTooltip",
    "模拟数据展示UI",
    "static/icons/sites",
    "your-name",
    "????",
)

FORBIDDEN_PUBLIC_PRIVATE_TERMS = tuple(
    item
    for item in (
        os.environ.get("USERPROFILE", ""),
        "127.0.0.1:" + "40444",
        "新建" + "文件夹",
    )
    if item
)

IGNORED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "data",
    "logs",
    "docs/internal",
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def run_git_ls_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [
        ROOT / line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and (ROOT / line.strip()).is_file()
    ]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_skipped(path: Path) -> bool:
    relative = rel(path)
    return any(part in relative for part in IGNORED_PARTS)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def assert_required_files_exist() -> None:
    missing = [item for item in REQUIRED_PUBLIC_FILES if not (ROOT / item).is_file()]
    if missing:
        fail(f"缺少开源发布文件：{', '.join(missing)}")


def assert_forbidden_public_paths_absent() -> None:
    for relative in FORBIDDEN_PUBLIC_PATHS:
        if (ROOT / relative).exists():
            fail(f"公开版本不应包含路径：{relative}")


def assert_no_runtime_private_artifacts(candidates: list[Path]) -> None:
    forbidden_suffixes = (".sqlite", ".sqlite-shm", ".sqlite-wal", ".db", ".log")
    for path in candidates:
        relative = rel(path)
        if relative == "static/exe-icons/.gitkeep":
            continue
        if relative.startswith("static/exe-icons/"):
            fail(f"本机提取图标不应发布：{relative}")
        if relative.startswith("static/icons/sites/"):
            fail(f"站点图标不属于当前应用级统计边界：{relative}")
        if path.name == ".env":
            fail(".env 不应发布，请只提交 .env.example")
        if path.suffix.lower() in forbidden_suffixes or path.name.endswith(".log"):
            fail(f"运行时私有产物不应发布：{relative}")


def assert_no_forbidden_implementation_terms(candidates: list[Path]) -> None:
    targets = [
        path
        for path in candidates
        if rel(path).startswith("app/") and path.suffix == ".py"
    ]
    targets.append(ROOT / "requirements.txt")
    targets.append(ROOT / "pyproject.toml")

    for path in targets:
        if not path.exists():
            continue
        text = read_text(path)
        for term in FORBIDDEN_IMPLEMENTATION_TERMS:
            if term in text:
                fail(f"实现层出现禁止项 {term!r}：{rel(path)}")


def assert_no_private_strings(candidates: list[Path]) -> None:
    for path in candidates:
        if is_skipped(path) or path.suffix.lower() in {".png", ".ico", ".sqlite", ".db"}:
            continue
        text = read_text(path)
        for term in FORBIDDEN_PUBLIC_PRIVATE_TERMS:
            if term in text:
                fail(f"公开候选文件包含本机私有字符串 {term!r}：{rel(path)}")


def assert_no_public_residue_terms(candidates: list[Path]) -> None:
    for path in candidates:
        if rel(path) == "scripts/release_audit.py":
            continue
        if is_skipped(path) or path.suffix.lower() in {".png", ".ico", ".sqlite", ".db"}:
            continue
        text = read_text(path)
        for term in FORBIDDEN_PUBLIC_RESIDUE_TERMS:
            if term in text:
                fail(f"公开候选文件包含开发残留 {term!r}：{rel(path)}")


def assert_windows_first_docs() -> None:
    readme = read_text(ROOT / "README.md")
    required_phrases = (
        "Windows-first",
        "不是 macOS 移植版",
        "不读取浏览器历史",
        "不上传服务器",
        "Win32",
    )
    for phrase in required_phrases:
        if phrase not in readme:
            fail(f"README 缺少 Windows-first/隐私定位短语：{phrase}")


def assert_github_owner_placeholder_is_tracked() -> None:
    checklist = read_text(ROOT / "docs" / "RELEASE_CHECKLIST.md")
    if "OWNER/winflow" not in checklist:
        fail("发布清单缺少 GitHub 仓库 OWNER/winflow 占位替换项")


def assert_source_tree_alpha_boundary() -> None:
    readme = read_text(ROOT / "README.md")
    checklist = read_text(ROOT / "docs" / "RELEASE_CHECKLIST.md")
    if "当前 alpha 版本仍推荐从仓库源码目录运行" not in readme:
        fail("README 缺少 alpha 阶段源码目录运行边界说明")
    if "scripts/package_audit.py" not in readme or "scripts/package_audit.py" not in checklist:
        fail("README 或发布清单缺少 package audit 说明")
    if "静态资源路径" not in checklist or "Windows installer" not in checklist:
        fail("发布清单缺少 installer/静态资源路径验证项")


def assert_runtime_path_docs() -> None:
    combined = "\n".join(
        read_text(ROOT / item)
        for item in (
            "README.md",
            "PRIVACY.md",
            "docs/ARCHITECTURE.md",
            ".env.example",
        )
    )
    for phrase in ("WINFLOW_DATA_DIR", "WINFLOW_DB", "WINFLOW_EXE_ICON_DIR"):
        if phrase not in combined:
            fail(f"运行时路径配置缺少公开文档说明：{phrase}")
    pyproject = read_text(ROOT / "pyproject.toml")
    if 'app = ["static/icons/apps/*.svg"]' not in pyproject:
        fail("pyproject.toml 缺少内置 SVG 图标 package-data 声明")


def assert_check_commands_are_documented() -> None:
    docs = {
        "README.md": read_text(ROOT / "README.md"),
        "CONTRIBUTING.md": read_text(ROOT / "CONTRIBUTING.md"),
        ".github/pull_request_template.md": read_text(ROOT / ".github" / "pull_request_template.md"),
        "docs/RELEASE_CHECKLIST.md": read_text(ROOT / "docs" / "RELEASE_CHECKLIST.md"),
    }
    for path, text in docs.items():
        for command in REQUIRED_CHECK_COMMANDS:
            if command not in text:
                fail(f"{path} 缺少检查命令：{command}")

    ci = read_text(ROOT / ".github" / "workflows" / "ci.yml")
    for command in REQUIRED_CHECK_COMMANDS:
        if command not in ci:
            fail(f"CI 缺少检查命令：{command}")


def assert_governance_docs_match_scope() -> None:
    changelog = read_text(ROOT / "CHANGELOG.md")
    roadmap = read_text(ROOT / "ROADMAP.md")
    api_schema = read_text(ROOT / "docs" / "API_SCHEMA.md")

    for phrase in (
        "移除默认浏览器历史读取模块",
        "WINFLOW_DATA_DIR",
        "scripts/package_audit.py",
        "app/static/",
    ):
        if phrase not in changelog:
            fail(f"CHANGELOG 缺少当前发布变化：{phrase}")

    for phrase in (
        "[x] 文档化上传 API",
        "[x] 安装态基础路径审计",
        "[x] 增加发布审计和打包审计",
    ):
        if phrase not in roadmap:
            fail(f"ROADMAP 未反映已完成范围：{phrase}")

    if '"last_status": "extended"' not in api_schema:
        fail("API_SCHEMA 的 collector/status 示例缺少 last_status")
    if '"started_at"' in api_schema or '"event_count"' in api_schema:
        fail("API_SCHEMA 的 collector/status 示例包含已不存在字段")


def main() -> int:
    candidates = run_git_ls_files()
    assert_required_files_exist()
    assert_forbidden_public_paths_absent()
    assert_no_runtime_private_artifacts(candidates)
    assert_no_forbidden_implementation_terms(candidates)
    assert_no_private_strings(candidates)
    assert_no_public_residue_terms(candidates)
    assert_windows_first_docs()
    assert_github_owner_placeholder_is_tracked()
    assert_source_tree_alpha_boundary()
    assert_runtime_path_docs()
    assert_check_commands_are_documented()
    assert_governance_docs_match_scope()
    print("[OK] release audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
