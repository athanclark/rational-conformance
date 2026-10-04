#!/usr/bin/env python3
"""Record public source revisions and runtime versions for reproduction."""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import subprocess


def output(command, **kwargs):
    return subprocess.run(command,check=True,text=True,capture_output=True,timeout=30,**kwargs).stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream",type=Path,default=Path("upstream"))
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    repositories = {
        "sqlite-rational": "https://github.com/athanclark/sqlite-rational",
        "rational-map": "https://github.com/athanclark/rational-map",
        "pgmp": "https://github.com/dvarrazzo/pgmp",
    }
    sources = {name: dict(repository=url,commit=output(["git","rev-parse","HEAD"],cwd=args.upstream/name))
               for name,url in repositories.items()}
    sources["pgmp"]["release"] = json.loads((args.upstream/"pgmp/META.json").read_text())["version"]
    versions = dict(sources=sources,suite_commit=output(["git","rev-parse","HEAD"]),
                    python=platform.python_version(),sqlite=sqlite3.sqlite_version,
                    node=output(["node","--version"]),postgresql=output(["pg_config","--version"]),
                    gmp=output(["pkg-config","--modversion","gmp"]))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(versions,indent=2)+"\n")


if __name__ == "__main__":
    main()
