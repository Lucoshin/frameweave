import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.animation import validate_request, validate_story, AnimationService


def payload(**changes):
    data = {"mode": "remotion", "prompt": "讲清楚三个习惯", "duration": 12,
            "sceneCount": 3, "aspectRatio": "9:16", "imageSource": "none",
            "textConfig": {"baseUrl": "https://example.com/v1", "apiKey": "secret-key", "model": "test"}}
    return data | changes


def story():
    return {"title": "三个习惯", "scenes": [
        {"title": str(i), "text": "每天行动", "imagePrompt": "一个人在阅读", "visual": "steps"}
        for i in range(3)]}


class AnimationTests(unittest.TestCase):
    def test_invalid_speech_config_is_rejected_before_job_creation(self):
        with self.assertRaisesRegex(ValueError, "语音"):
            validate_request(payload(narration={}))

    def test_overlong_narration_fails_without_rendering_or_truncating_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AnimationService(Path(tmp))
            config = {"provider": "openai", "baseUrl": "https://example.com/v1", "apiKey": "speech-secret", "model": "tts", "voice": "test", "speed": 1}
            with patch("services.animation.generate_story", return_value=story()), patch("services.speech.synthesize_speech", return_value={"path": "test.wav", "duration": 45}), patch.object(service, "_render") as render:
                job = service.create(payload(narration=config), background=False)
            self.assertEqual(job["status"], "failed")
            self.assertIn("未截断音频", job["error"])
            render.assert_not_called()

    def test_narration_extends_frames_and_keeps_audio_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AnimationService(Path(tmp))
            config = {"provider": "openai", "baseUrl": "https://example.com/v1", "apiKey": "speech-secret", "model": "tts", "voice": "test", "speed": 1}
            captured = {}
            def render(job_id, directory):
                captured.update(json.loads((directory / "story.json").read_text(encoding="utf-8")))
                (directory / "video.mp4").write_bytes(b"0" * 2048)
            with patch("services.animation.generate_story", return_value=story()), patch("services.speech.synthesize_speech", return_value={"path": "test.wav", "duration": 7.05}), patch.object(service, "_render", side_effect=render):
                job = service.create(payload(narration=config), background=False)
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual([s["durationInFrames"] for s in captured["scenes"]], [224, 224, 224])
            self.assertEqual(captured["scenes"][0]["audio"], "scene-1.wav")
            self.assertEqual(captured["durationInFrames"], 672)
            self.assertNotIn("speech-secret", json.dumps(captured))

    def test_rejects_missing_ai_and_mismatched_images(self):
        with self.assertRaisesRegex(ValueError, "AI"):
            validate_request(payload(textConfig={}))
        with self.assertRaisesRegex(ValueError, "图片"):
            validate_request(payload(mode="illustrated", imageSource="local", assetIds=["a"]))

    def test_rejects_unknown_mode_and_non_finite_duration(self):
        for change in ({"mode": "javascript"}, {"duration": float("nan")}, {"sceneCount": True}):
            with self.assertRaises(ValueError):
                validate_request(payload(**change))

    def test_scene_schema_and_timing_comes_from_request(self):
        result = validate_story(story(), validate_request(payload()))
        self.assertEqual([s["durationInFrames"] for s in result["scenes"]], [120, 120, 120])
        self.assertEqual(result["durationInFrames"], 360)
        self.assertNotIn("apiKey", json.dumps(result))
        bad = story()
        bad["scenes"][0]["visual"] = "<script>"
        with self.assertRaisesRegex(ValueError, "visual"):
            validate_story(bad, validate_request(payload()))

    def test_success_requires_output_file_and_never_persists_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AnimationService(Path(tmp))
            with patch("services.animation.generate_story", return_value=story()), patch.object(service, "_render", return_value=None):
                job = service.create(payload(), background=False)
            self.assertEqual(job["status"], "failed")
            for file in Path(tmp).rglob("*.json"):
                self.assertNotIn("secret-key", file.read_text(encoding="utf-8"))

    def test_provider_error_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = AnimationService(Path(tmp))
            with patch("services.animation.generate_story", side_effect=RuntimeError("secret-key failed")):
                job = service.create(payload(), background=False)
            self.assertEqual(job["status"], "failed")
            self.assertNotIn("secret-key", job["error"])


if __name__ == "__main__":
    unittest.main()
