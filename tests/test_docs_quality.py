from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocsQualityTests(unittest.TestCase):
    def test_public_markdown_has_no_replacement_question_runs(self) -> None:
        replacement_run = "?" * 4
        ignored_parts = {
            ".git",
            "data",
            "logs",
            "docs/internal",
            "static/exe-icons",
            "__pycache__",
            ".venv",
        }
        public_markdown = [
            path
            for path in ROOT.rglob("*.md")
            if not any(part in path.relative_to(ROOT).as_posix() for part in ignored_parts)
        ]
        self.assertTrue(public_markdown)
        for path in public_markdown:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn(replacement_run, path.read_text(encoding="utf-8"))

    def test_readme_declares_source_tree_alpha_boundary(self) -> None:
        """当前 alpha 主路径仍是源码运行，但安装态基础路径已有审计。"""

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("当前 alpha 版本仍推荐从仓库源码目录运行", readme)
        self.assertIn("scripts/package_audit.py", readme)
        self.assertIn("winflow", readme)
        self.assertIn("Windows installer", readme)
        self.assertIn("安装态数据目录", readme)

    def test_public_docs_explain_architecture_and_troubleshooting(self) -> None:
        """GitHub 访客和贡献者应能快速理解项目结构与常见问题。"""

        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        troubleshooting = (ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")

        for phrase in (
            "Windows-first",
            "app/windows_activity.py",
            "app/activity_bands.py",
            "app/uploader.py",
            "隐私边界",
        ):
            with self.subTest(doc="ARCHITECTURE.md", phrase=phrase):
                self.assertIn(phrase, architecture)

        for phrase in (
            "本地页面没有数据",
            "采集器看起来没有更新",
            "浏览器没有显示具体标签页",
            "图标看起来不对或太小",
            "上传命令失败",
        ):
            with self.subTest(doc="TROUBLESHOOTING.md", phrase=phrase):
                self.assertIn(phrase, troubleshooting)

    def test_runtime_data_directory_overrides_are_documented(self) -> None:
        """运行时数据目录已经从源码树路径抽象出来，文档必须同步。"""

        docs = "\n".join(
            [
                (ROOT / "README.md").read_text(encoding="utf-8"),
                (ROOT / "PRIVACY.md").read_text(encoding="utf-8"),
                (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8"),
                (ROOT / ".env.example").read_text(encoding="utf-8"),
            ]
        )
        for phrase in (
            "WINFLOW_DATA_DIR",
            "WINFLOW_DB",
            "WINFLOW_EXE_ICON_DIR",
            "%LOCALAPPDATA%\\Winflow",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, docs)

    def test_public_check_commands_are_consistent(self) -> None:
        """README、贡献指南、PR 模板和发布清单应给出同一组关键检查。"""

        documents = {
            "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
            "CONTRIBUTING.md": (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"),
            ".github/pull_request_template.md": (
                ROOT / ".github" / "pull_request_template.md"
            ).read_text(encoding="utf-8"),
            "docs/RELEASE_CHECKLIST.md": (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(
                encoding="utf-8"
            ),
        }
        commands = (
            "python -m compileall -q app tests scripts",
            "python -m unittest discover -s tests",
            "python scripts/release_audit.py",
            "python scripts/package_audit.py",
        )
        for name, text in documents.items():
            for command in commands:
                with self.subTest(document=name, command=command):
                    self.assertIn(command, text)

    def test_governance_docs_match_current_release_scope(self) -> None:
        """路线图和变更日志应反映当前已经完成的开源发布基线。"""

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

        for phrase in (
            "移除默认浏览器历史读取模块",
            "WINFLOW_DATA_DIR",
            "scripts/package_audit.py",
            "app/static/",
        ):
            with self.subTest(document="CHANGELOG.md", phrase=phrase):
                self.assertIn(phrase, changelog)

        for phrase in (
            "[x] 文档化上传 API",
            "[x] 安装态基础路径审计",
            "[x] 增加发布审计和打包审计",
        ):
            with self.subTest(document="ROADMAP.md", phrase=phrase):
                self.assertIn(phrase, roadmap)

    def test_api_schema_collector_status_matches_current_keys(self) -> None:
        """collector/status 文档不能继续展示已不存在的字段。"""

        api_schema = (ROOT / "docs" / "API_SCHEMA.md").read_text(encoding="utf-8")
        self.assertIn('"last_status": "extended"', api_schema)
        self.assertNotIn('"started_at"', api_schema)
        self.assertNotIn('"event_count"', api_schema)

    def test_github_release_guide_documents_manual_steps(self) -> None:
        """首次公开发布需要人工完成的 GitHub 设置必须单独说明。"""

        guide = (ROOT / "docs" / "GITHUB_RELEASE_GUIDE.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

        for phrase in (
            "OWNER/winflow",
            "GitHub 仓库设置",
            "README 截图或 GIF",
            "v0.1.0-alpha",
            "发布后验证",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guide)

        self.assertIn("docs/GITHUB_RELEASE_GUIDE.md", readme)
        self.assertIn("docs/GITHUB_RELEASE_GUIDE.md", checklist)


if __name__ == "__main__":
    unittest.main()
