import json
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8765"


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.process = subprocess.Popen(
            [sys.executable, "src/api/server.py", "--host", "127.0.0.1",
             "--port", "8765", "--database", str(ROOT / "data/final/nha_packages.sqlite3")],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(30):
            try:
                urllib.request.urlopen(f"{BASE_URL}/api/packages", timeout=1).read()
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("API server did not become ready")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)

    def get_json(self, path):
        with urllib.request.urlopen(BASE_URL + path, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_package_list_search_and_detail(self):
        status, packages = self.get_json("/api/packages")
        self.assertEqual(status, 200)
        self.assertGreater(len(packages), 0)

        status, matches = self.get_json("/api/packages/search?q=BM001")
        self.assertEqual(status, 200)
        self.assertIn("BM001", [row["package_code"] for row in matches])

        status, detail = self.get_json("/api/packages/BM001")
        self.assertEqual(status, 200)
        self.assertEqual(detail["package_code"], "BM001")
        self.assertIn("eligibility", detail)
        self.assertEqual(detail["preauthorization"]["preauth_required"], "unknown")
        self.assertEqual(detail["investigations"], [])
        self.assertEqual(detail["documents"], [])

    def test_invalid_package_does_not_invent_data(self):
        request = urllib.request.Request(f"{BASE_URL}/api/packages/NOT-A-REAL-PACKAGE")
        try:
            urllib.request.urlopen(request, timeout=5)
            self.fail("Invalid package unexpectedly returned success")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 404)

    def test_diagnosis_search_and_unknown_diagnosis(self):
        status, matches = self.get_json("/api/diagnoses/search?q=Cataract")
        self.assertEqual(status, 200)
        self.assertIsInstance(matches, list)
        status, unknown = self.get_json("/api/diagnoses/search?q=not-a-real-diagnosis")
        self.assertEqual(status, 200)
        self.assertEqual(unknown, [])


if __name__ == "__main__":
    unittest.main()
