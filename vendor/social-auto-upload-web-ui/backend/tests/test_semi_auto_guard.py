import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import app


class SemiAutoPublishGuardTest(unittest.TestCase):
    def test_obsolete_automated_publish_routes_are_not_registered(self):
        post_routes = {
            rule.rule
            for rule in app.url_map.iter_rules()
            if "POST" in rule.methods
        }
        obsolete_endpoints = (
            "/postVideo",
            "/postVideoBatch",
            "/api/v2/drafts/batch-publish",
            "/api/image-publish/publish",
            "/api/image-publish/execute-publish",
            "/api/image-publish/drafts/batch-publish",
        )

        for endpoint in obsolete_endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertNotIn(endpoint, post_routes)

        all_routes = {rule.rule for rule in app.url_map.iter_rules()}
        self.assertNotIn("/postVideo/status/<task_id>", all_routes)

    def test_prepare_and_draft_crud_routes_remain_registered(self):
        routes_by_method = {
            method: {
                rule.rule
                for rule in app.url_map.iter_rules()
                if method in rule.methods
            }
            for method in ("GET", "POST", "DELETE")
        }

        self.assertIn("/api/v2/publish/prepare", routes_by_method["POST"])
        self.assertIn(
            "/api/v2/publish/prepare/<session_id>", routes_by_method["GET"]
        )
        self.assertIn("/api/v2/drafts", routes_by_method["GET"])
        self.assertIn("/api/v2/drafts", routes_by_method["POST"])
        self.assertIn("/api/image-publish/drafts", routes_by_method["GET"])
        self.assertIn("/api/image-publish/drafts", routes_by_method["POST"])
        self.assertIn(
            "/api/image-publish/drafts/<draft_id>", routes_by_method["DELETE"]
        )


if __name__ == "__main__":
    unittest.main()
