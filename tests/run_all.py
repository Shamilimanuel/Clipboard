"""Runs every test file in this folder, each in a throwaway data folder, and reports pass or fail.

    python tests\\run_all.py        (add -v to see what each file printed)

The tests never show a window on screen (that would steal your keyboard focus) and never touch the real
clipboard or your history: windows are hidden, the clipboard functions are replaced by recorders.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

folder = Path(__file__).resolve().parent
failed = 0
for test in sorted(folder.glob("test_*.py")):
    with tempfile.TemporaryDirectory(prefix="clipboardtest_") as data_dir:
        env = dict(os.environ, CLIPBOARD_DATA_DIR=data_dir, PYTHONIOENCODING="utf-8")
        run = subprocess.run([sys.executable, str(test)], env=env, capture_output=True, text=True, encoding="utf-8")
    status = "PASS" if run.returncode == 0 else "FAIL"
    print(f"{status}  {test.name}")
    output = (run.stdout + run.stderr).strip()
    if run.returncode != 0:
        failed += 1
        print("\n".join("    " + line for line in output.splitlines()[-15:]))
    elif "-v" in sys.argv:
        print("\n".join("    " + line for line in output.splitlines()))
print("\nall passed" if not failed else f"\n{failed} test file(s) failed")
sys.exit(1 if failed else 0)
