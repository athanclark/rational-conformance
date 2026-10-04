"""Check that independently selected backends fail CI and still report results."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run
from fixture import fixture, oracle


class HarnessTests(unittest.TestCase):
    def invoke(self, argv):
        with patch.object(sys,"argv",["run.py",*argv]), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return run.main()

    def test_requires_postgres_arguments(self):
        with self.assertRaises(SystemExit) as error:
            self.invoke(["--require-pgmp"])
        self.assertEqual(error.exception.code,2)

    def test_explicit_paths_and_all_backend_results(self):
        expected = oracle(fixture())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = [root/"unrelated-esm/index.js",root/"unrelated-bundle/browser.js"]
            module = root/"native/sqlite_rational.so"
            report = root/"results/report.json"
            completed = subprocess.CompletedProcess([],0,json.dumps(expected),"")
            with patch.object(run,"sqlite_adapter",return_value=expected) as sqlite, \
                    patch.object(run.subprocess,"run",return_value=completed) as node, \
                    patch.object(run,"postgres_adapter",return_value=expected) as pg:
                status = self.invoke(["--sqlite-extension",str(module),
                    "--rational-map",str(entries[0]),"--rational-map",str(entries[1]),
                    "--pg-dsn","dbname=test","--require-pgmp","--report",str(report)])
            self.assertEqual(status,0)
            self.assertEqual(sqlite.call_args.args[1],module)
            self.assertEqual([call.args[0][-1] for call in node.call_args_list],list(map(str,entries)))
            pg.assert_called_once()
            result = json.loads(report.read_text())
            self.assertEqual([backend["status"] for backend in result["backends"]],["passed"]*4)
            self.assertEqual((result["range_overview_cases"],result["arithmetic_cases"]),(160,42))

    def test_failure_keeps_other_checks_and_reports_stderr(self):
        expected = oracle(fixture())
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp)/"report.json"
            failure = subprocess.CalledProcessError(1,["node"],stderr="incompatible upstream module")
            with patch.object(run,"sqlite_adapter",side_effect=RuntimeError("bad extension")), \
                    patch.object(run.subprocess,"run",side_effect=failure), \
                    patch.object(run,"postgres_adapter",return_value=expected) as pg:
                status = self.invoke(["--pg-dsn","dbname=test","--require-pgmp","--report",str(report)])
            self.assertEqual(status,1)
            pg.assert_called_once()
            result = json.loads(report.read_text())
            self.assertEqual(result["status"],"failed")
            self.assertEqual([backend["status"] for backend in result["backends"]],["failed","failed","passed"])
            self.assertIn("incompatible upstream module",result["backends"][1]["error"])

    def test_result_mismatch_fails(self):
        expected = oracle(fixture())
        actual = json.loads(json.dumps(expected))
        actual["arithmetic"][0][3] = "999/1"
        with self.assertRaisesRegex(AssertionError,r"arithmetic\[0\] differs"):
            run.check("Broken arithmetic",actual,expected)


if __name__ == "__main__":
    unittest.main()
