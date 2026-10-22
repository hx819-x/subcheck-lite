import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from subcheck.core import analyze
from subcheck.report import render_html


ROOT = Path(__file__).resolve().parents[1]
CLEAN = "1\n00:00:00,000 --> 00:00:02,000\n你好世界\n"


class ReportTests(unittest.TestCase):
    def test_escapes_subtitle_and_filename(self):
        malicious = CLEAN.replace("你好世界", '<script>alert("x")</script>&')
        report = render_html(analyze(malicious, filename='<img src=x onerror=alert(1)>.srt'))
        self.assertNotIn("<script>", report)
        self.assertNotIn("<img src=x", report)
        self.assertIn("&lt;script&gt;", report)
        self.assertIn("&lt;img", report)
        self.assertIn("Content-Security-Policy", report)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.source = self.folder / "测试 subtitle.srt"
        self.source.write_text(CLEAN, encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "subcheck", str(self.source), *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_exports_both_reports_and_preserves_input(self):
        html = self.folder / "nested" / "report.html"
        json_path = self.folder / "report.json"
        process = self.run_cli("--html", html, "--json", json_path)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("你好世界", html.read_text(encoding="utf-8"))
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["total_cues"], 1)
        self.assertEqual(data["summary"]["errors"], 0)
        self.assertEqual(self.source.read_text(encoding="utf-8"), CLEAN)

    def test_errors_return_one_and_still_export(self):
        self.source.write_text("1\n00:00:02,000 --> 00:00:01,000\n倒置\n", encoding="utf-8")
        target = self.folder / "report.html"
        process = self.run_cli("--html", target)
        self.assertEqual(process.returncode, 1)
        self.assertTrue(target.exists())

    def test_warnings_fail_only_in_strict_mode(self):
        self.assertEqual(self.run_cli("--max-chars", 1).returncode, 0)
        self.assertEqual(self.run_cli("--max-chars", 1, "--strict").returncode, 1)

    def test_input_cannot_be_overwritten(self):
        self.assertEqual(self.run_cli("--html", self.source).returncode, 2)
        self.assertEqual(self.source.read_text(encoding="utf-8"), CLEAN)

    def test_input_hardlink_cannot_be_overwritten(self):
        alias = self.folder / "alias.html"
        os.link(self.source, alias)
        self.assertEqual(self.run_cli("--html", alias).returncode, 2)
        self.assertEqual(self.source.read_text(encoding="utf-8"), CLEAN)

    def test_reports_need_distinct_paths(self):
        target = self.folder / "report"
        self.assertEqual(self.run_cli("--html", target, "--json", target).returncode, 2)
        self.assertFalse(target.exists())

    def test_missing_file_and_bad_encoding(self):
        self.assertEqual(self.run_cli("--encoding", "not-an-encoding").returncode, 2)
        self.source.unlink()
        self.assertEqual(self.run_cli().returncode, 2)

    def test_symlink_loop_returns_file_error_without_traceback(self):
        self.source.unlink()
        self.source.symlink_to(self.source.name)
        process = self.run_cli()
        self.assertEqual(process.returncode, 2)
        self.assertNotIn("Traceback", process.stderr)

    def test_explicit_gb18030(self):
        self.source.write_bytes(CLEAN.encode("gb18030"))
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("--encoding", "gb18030").returncode, 0)

    def test_invalid_threshold_is_usage_error(self):
        self.assertEqual(self.run_cli("--max-cps", "nan").returncode, 2)
        self.assertEqual(self.run_cli("--min-duration-ms", "-1").returncode, 2)


if __name__ == "__main__":
    unittest.main()
