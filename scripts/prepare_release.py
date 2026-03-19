#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist" / "github-release"

EXCLUDE_NAMES = {
    ".git",
    "output",
    "outputs",
    "reports",
    "profiles",
    "config.json",
    "ui_config.json",
    ".DS_Store",
}

def run_privacy_scan(base_dir: Path) -> int:
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "privacy_scan.py"), "--base-dir", str(base_dir), "--fail-on-warning"]
    return subprocess.call(cmd)

def copy_tree_sanitized(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        # Normalize relative path
        rel = Path(root).relative_to(src)
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_NAMES and not d.startswith(".")]
        for name in files:
            if name in EXCLUDE_NAMES:
                continue
            # Skip compiled/cache files
            if name.endswith((".log", ".pyc")):
                continue
            src_fp = Path(root) / name
            dst_dir = dst / rel
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_fp, dst_dir / name)

def main() -> int:
    print(f"Preparing sanitized release at: {DIST_DIR}")
    copy_tree_sanitized(PROJECT_ROOT, DIST_DIR)
    # Ensure example configs exist in dist
    for ex in ("config.example.json", "ui_config.example.json"):
        shutil.copy2(PROJECT_ROOT / ex, DIST_DIR / ex)
    # Run privacy scan on dist copy (fail on warnings)
    code = run_privacy_scan(DIST_DIR)
    if code != 0:
        print("Privacy scan failed. Please review reports before publishing.")
        return code
    print("Sanitized release prepared successfully.")
    print(f"Next: review {DIST_DIR} and push to GitHub after confirmation.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

