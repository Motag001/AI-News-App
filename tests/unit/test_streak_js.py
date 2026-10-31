import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("node"), "Node.js is needed to run the streak tests")
class BrowserScriptTests(unittest.TestCase):
    def test_streak_and_service_worker_modules(self):
        result = subprocess.run(  # nosec B603 B607 - fixed arguments, no user input
            ["node", "--test", str(ROOT / "tests" / "js" / "streak.test.js"), str(ROOT / "tests" / "js" / "sw.test.js")],
            capture_output=True, text=True, timeout=60, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
