"""Publish the built site/ folder to the gh-pages branch (GitHub Pages serves that branch as-is).

Usage: python -m shared.publish "<commit message>"
The branch holds only the generated site, as a single fresh commit each time, so its history never
mixes with the source history on main.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def publish(message: str) -> None:
    if not (SITE / "index.html").exists():
        sys.exit("site/ is missing: run `make site` first")
    remote = git("remote", "get-url", "origin", cwd=ROOT)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "site"
        shutil.copytree(SITE, work)
        (work / ".nojekyll").touch()  # serve files exactly as built, without Jekyll processing
        git("init", "-q", "-b", "gh-pages", cwd=work)
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", message, cwd=work)
        git("push", "-q", "--force", remote, "gh-pages", cwd=work)
    print(f"published {SITE} to gh-pages on {remote}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        sys.exit('usage: python -m shared.publish "<commit message>"')
    publish(sys.argv[1])
