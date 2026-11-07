import json
import os
import threading
import time
import unittest
import urllib.request

os.environ.pop("GEMINI_API_KEY", None)

import sensx25


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = sensx25.start_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    def test_shy_practice_press_updates_the_page_state(self):
        request = urllib.request.Request(
            self.base + "/demo",
            data=json.dumps({"kind": "shy"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 202)
        deadline = time.time() + 4
        last = {}
        while time.time() < deadline:
            with urllib.request.urlopen(self.base + "/state", timeout=2) as response:
                last = json.loads(response.read().decode())
            if last.get("emotion") == "shy" and not last.get("thinking") and not last.get("demo"):
                break
            time.sleep(0.05)
        self.assertEqual(last.get("emotion"), "shy", last)
        self.assertFalse(last.get("thinking"))
        self.assertIn("barely a touch", last.get("line", ""))
        self.assertEqual(last.get("source"), "offline")
        self.assertEqual(len(last.get("grid", [])), 5)

    def test_index_is_the_agent_page(self):
        with urllib.request.urlopen(self.base + "/", timeout=2) as response:
            body = response.read().decode()
        self.assertIn("Mote", body)
        self.assertIn("EventSource", body)


if __name__ == "__main__":
    unittest.main()
