#!/usr/bin/env python3
"""Render reports as a GitHub Actions step summary, including incomplete runs."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts",type=Path,default=Path("artifacts"))
    args = parser.parse_args()
    print("## Rational conformance\n")
    versions_file = args.artifacts/"versions.json"
    if versions_file.exists():
        versions = json.loads(versions_file.read_text())
        print("| Upstream project | Tested commit |\n| --- | --- |")
        for name,source in versions["sources"].items():
            sha = source["commit"]
            print(f"| {name} | [{sha}]({source['repository']}/commit/{sha}) |")
        print(f"\nSuite commit: `{versions['suite_commit']}`.\n")
        print(f"{versions['postgresql']}; Node {versions['node']}; "
              f"Python {versions['python']}; SQLite {versions['sqlite']}; GMP {versions['gmp']}.\n")
    report_file = args.artifacts/"conformance.json"
    if not report_file.exists():
        print("Conformance did not complete. Check the failed setup/build step and uploaded logs.")
        return
    report = json.loads(report_file.read_text())
    print(f"Fixture version {report['fixture_version']}: "
          f"{report['range_overview_cases']} range/overview cases and "
          f"{report['arithmetic_cases']} arithmetic cases per backend.\n")
    print("| Backend | Result |\n| --- | --- |")
    for backend in report["backends"]:
        print(f"| {backend['name']} | {backend['status']} |")
    print("\nThe RationalMap ESM and standalone browser bundles run under Node here. "
          "The rational-map repository also tests actual Chromium, Firefox, and WebKit runtimes.")


if __name__ == "__main__":
    main()
