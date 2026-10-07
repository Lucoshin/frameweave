import json
import sys
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


class TestLoginSseStream(unittest.TestCase):
    def test_legacy_messages_are_emitted_as_json_with_canonical_statuses(self):
        import app as app_module

        status_queue = Queue()
        status_queue.put("https://example.test/qr-code")
        status_queue.put(json.dumps({"status": "200", "name": "tester"}))

        stream = app_module.sse_stream(status_queue, heartbeat_interval=0.01)
        progress = json.loads(next(stream).removeprefix("data: "))
        success = json.loads(next(stream).removeprefix("data: "))

        self.assertEqual(progress, {
            "status": "progress",
            "data": "https://example.test/qr-code",
        })
        self.assertEqual(success["status"], "success")
        self.assertEqual(success["name"], "tester")
        with self.assertRaises(StopIteration):
            next(stream)

    def test_disconnect_requests_session_cancellation(self):
        import app as app_module

        status_queue = Queue()
        status_queue.put("waiting")
        on_disconnect = Mock()
        stream = app_module.sse_stream(
            status_queue,
            on_disconnect=on_disconnect,
            heartbeat_interval=0.01,
        )

        next(stream)
        stream.close()

        on_disconnect.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
