"""Tests for local/build_duckdb.py, the build behind the live app and the monthly health check."""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "local" / "build_duckdb.py"
SOURCE = REPO / "Laboratory.csv"
DATABASE = REPO / "batch_monitor.duckdb"
HAS_DUCKDB = importlib.util.find_spec("duckdb") is not None


def run_build(*args):
    return subprocess.run([sys.executable, str(BUILD), *args], capture_output=True, text=True, timeout=300)


def database_state():
    return DATABASE.stat().st_mtime_ns if DATABASE.exists() else None


@unittest.skipUnless(HAS_DUCKDB and SOURCE.exists(), "needs duckdb and Laboratory.csv")
class BuildTests(unittest.TestCase):

    def test_a_tampered_file_is_refused_before_anything_is_built(self):
        before = database_state()
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "Laboratory.csv"
            shutil.copyfile(SOURCE, tampered)
            with open(tampered, "ab") as f:
                f.write(b"\n")  # a single extra byte
            result = run_build(str(tampered))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("doesn't match the verified fingerprint", result.stdout + result.stderr)
        self.assertEqual(database_state(), before, "the existing database must be left untouched")

    def test_the_verified_file_builds_with_every_check_passing(self):
        result = run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("[FAIL]", result.stdout)
        self.assertIn("checks passed", result.stdout)
        self.assertTrue(DATABASE.exists())


if __name__ == "__main__":
    unittest.main()
