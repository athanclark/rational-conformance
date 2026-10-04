"""Check that reproduction metadata and GitHub summaries describe the tested inputs."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name,ROOT/"scripts"/(name+".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


versions = script("versions")
summary = script("summary")


class ReportTests(unittest.TestCase):
    def test_versions_and_results_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            upstream = root/"upstream"
            (upstream/"pgmp").mkdir(parents=True)
            (upstream/"pgmp/META.json").write_text('{"version":"1.0.6"}')
            artifacts = root/"artifacts"
            shas = {"sqlite-rational":"1"*40,"rational-map":"2"*40,"pgmp":"3"*40}

            def output(command, **kwargs):
                if command == ["git","rev-parse","HEAD"]:
                    return shas[kwargs["cwd"].name] if "cwd" in kwargs else "4"*40
                return {"node":"v24.21.0","pg_config":"PostgreSQL 16.14","pkg-config":"6.3.0"}[command[0]]

            with patch.object(sys,"argv",["versions.py","--upstream",str(upstream),
                    "--output",str(artifacts/"versions.json")]), patch.object(versions,"output",side_effect=output):
                versions.main()
            manifest = json.loads((artifacts/"versions.json").read_text())
            self.assertEqual({name:source["commit"] for name,source in manifest["sources"].items()},shas)
            self.assertEqual(manifest["sources"]["pgmp"]["release"],"1.0.6")
            (artifacts/"conformance.json").write_text(json.dumps(dict(
                fixture_version=1,range_overview_cases=160,arithmetic_cases=42,status="failed",
                backends=[dict(name="SQLite",status="passed"),dict(name="PostgreSQL pgmp",status="failed")],
            )))
            captured = io.StringIO()
            with patch.object(sys,"argv",["summary.py","--artifacts",str(artifacts)]), \
                    contextlib.redirect_stdout(captured):
                summary.main()
            text = captured.getvalue()
            self.assertIn("https://github.com/athanclark/rational-map/commit/"+shas["rational-map"],text)
            self.assertIn("| PostgreSQL pgmp | failed |",text)
            self.assertIn("160 range/overview cases",text)

    def test_summary_reports_incomplete_run(self):
        with tempfile.TemporaryDirectory() as temp:
            captured = io.StringIO()
            with patch.object(sys,"argv",["summary.py","--artifacts",temp]), \
                    contextlib.redirect_stdout(captured):
                summary.main()
            self.assertIn("Conformance did not complete",captured.getvalue())


if __name__ == "__main__":
    unittest.main()
