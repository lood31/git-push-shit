import contextlib
import io
import json
import os
import subprocess
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from unittest.mock import patch

import push_shit as ps
from tests.support import RepoCase


class API(BaseHTTPRequestHandler):
    calls: ClassVar[list] = []
    models: ClassVar[list] = ["actual-gemma-id"]
    health = 200
    health_payload = b'{"status":"ok"}'
    chat_status = 200
    content = "test model connected"

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.calls.append(("GET", self.path, None))
        if self.path == "/v1/models":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": m} for m in self.models]}).encode())
        else:
            self.send_response(self.health if self.path == "/health" else 404)
            self.end_headers()
            self.wfile.write(self.health_payload)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(("POST", self.path, body))
        status = self.chat_status if self.path == "/v1/chat/completions" else 404
        self.send_response(status)
        self.end_headers()
        reply = {"choices": [{"message": {"content": self.content}}]}
        if status != 200:
            reply = {"error": {"message": "model unavailable"}}
        self.wfile.write(json.dumps(reply).encode())


class ConnectionTests(RepoCase):
    def setUp(self):
        super().setUp()
        API.calls = []
        API.models = ["actual-gemma-id"]
        API.health = 200
        API.health_payload = b'{"status":"ok"}'
        API.chat_status = 200
        API.content = "test model connected"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), API)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def connect(self, args):
        panel = ps._Panel()
        output = io.StringIO()
        with patch.object(panel, "target", str(self.repo)), \
                contextlib.redirect_stdout(output):
            ps._panel_connect(panel, args)
        return panel, output.getvalue()

    def test_explicit_v1_endpoint_is_normalized(self):
        panel, output = self.connect([self.endpoint + "/v1/", "actual-gemma-id"])
        self.assertTrue(panel.connected, output)
        posts = [c for c in API.calls if c[0] == "POST"]
        self.assertEqual(posts[-1][1], "/v1/chat/completions")

    def test_single_model_id_is_discovered(self):
        panel, output = self.connect([self.endpoint])
        self.assertTrue(panel.connected, output)
        self.assertEqual(panel.model, "actual-gemma-id")
        self.assertEqual([c for c in API.calls if c[0] == "POST"][-1][2]["model"], "actual-gemma-id")

    def test_multiple_models_require_explicit_choice(self):
        API.models = ["gemma-a", "gemma-b"]
        panel, output = self.connect([self.endpoint])
        self.assertFalse(panel.connected)
        self.assertIn("gemma-a", output)
        self.assertIn("gemma-b", output)
        self.assertFalse(any(c[0] == "POST" for c in API.calls))

    def test_explicit_model_wins(self):
        panel, output = self.connect([self.endpoint, "explicit-id"])
        self.assertTrue(panel.connected, output)
        self.assertEqual([c for c in API.calls if c[0] == "POST"][-1][2]["model"], "explicit-id")

    def test_missing_health_does_not_block_chat(self):
        API.health = 404
        panel, output = self.connect([self.endpoint, "actual-gemma-id"])
        self.assertTrue(panel.connected, output)

    def test_plain_text_health_response_does_not_silence_the_model(self):
        API.health_payload = b"OK"
        with patch.dict(os.environ, {"PUSH_SHIT_ENDPOINT": self.endpoint}):
            self.assertTrue(ps.server_alive())

    def test_http_error_is_diagnosed_and_status_reset(self):
        API.chat_status = 400
        panel, output = self.connect([self.endpoint, "bad-id"])
        self.assertFalse(panel.connected)
        self.assertIn("400", output)
        self.assertIn("model unavailable", output)

    def test_connection_configuration_survives_new_process(self):
        panel, output = self.connect([self.endpoint, "actual-gemma-id"])
        self.assertTrue(panel.connected, output)
        settings = self.repo / ".git/push-shit/connection.json"
        self.assertTrue(settings.is_file(), "successful connect must persist target settings")
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["endpoint"], self.endpoint)
        self.assertEqual(data["model"], "actual-gemma-id")
        env = dict(self.env)
        env.pop("PUSH_SHIT_ENDPOINT", None)
        env.pop("PUSH_SHIT_MODEL", None)
        with patch.dict(self.env, env, clear=True):
            result = self.cli(data="quit\n")
        self.assertIn(self.endpoint, result.stdout)
        self.assertIn("actual-gemma-id", result.stdout)
        self.assertFalse((self.repo / ".git/push-shit/config.json").exists(),
                         "connecting alone must not arm the ghost")

    def test_switch_target_does_not_reuse_implicit_previous_settings(self):
        self.connect([self.endpoint, "actual-gemma-id"])
        other = self.repo / "other-target"
        other.mkdir()
        self.run_process(["git", "-C", other, "init"])
        # Restore the caller's explicit environment, not runtime connect mutations.
        with patch.dict(os.environ, self.env, clear=True):
            output = self.panel([f"target {other.as_posix()}", "quit"])
        self.assertNotIn(self.endpoint, output.split("◎")[-1])

    def test_saved_model_is_reused_by_bare_connect_with_multiple_models(self):
        self.connect([self.endpoint, "actual-gemma-id"])
        API.models = ["actual-gemma-id", "another-model"]
        env = dict(self.env)
        env.pop("PUSH_SHIT_ENDPOINT", None)
        env.pop("PUSH_SHIT_MODEL", None)
        with patch.dict(os.environ, env, clear=True):
            panel = ps._Panel()
            with patch.object(panel, "target", str(self.repo)):
                ps._panel_connection(panel)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    ps._panel_connect(panel, [])
            self.assertTrue(panel.connected, output.getvalue())
            self.assertEqual(panel.model, "actual-gemma-id")

    def test_saved_configuration_is_used_by_a_real_hook(self):
        self.connect([self.endpoint, "actual-gemma-id"])
        self.panel(["lang content en", "quit"])
        self.make_remote()
        self.install()
        env = dict(self.env)
        env.pop("PUSH_SHIT_ENDPOINT", None)
        env.pop("PUSH_SHIT_MODEL", None)
        API.calls = []
        with patch.dict(self.env, env, clear=True):
            result = self.run_process(["git", "push", "shit", "main"])
        self.assertEqual(result.returncode, 0, result.stderr)
        posts = [c for c in API.calls if c[0] == "POST"]
        self.assertTrue(posts, "hook must reuse the persisted endpoint")
        self.assertTrue(all(c[2]["model"] == "actual-gemma-id" for c in posts))
        self.assertFalse(ps.ledger_read(str(self.repo))[0]["silent"])
        self.assertEqual(ps.ledger_read(str(self.repo))[0].get("language"), "en")
        self.assertEqual(ps.ledger_read(str(self.repo))[0].get("source"), "model")

    def test_saved_configuration_is_used_by_detached_watcher_and_uninstall_stops_it(self):
        self.connect([self.endpoint, "actual-gemma-id"])
        self.panel(["lang content en", "quit"])
        ps.save_config(str(self.repo), {"lang": "zh", "probability": 1,
                                      "haunt_count": 0, "lifetime_hauntings": 0,
                                      "diary_path": None})
        children = []
        original_popen = subprocess.Popen

        def capture(*args, **kwargs):
            proc = original_popen(*args, **kwargs)
            if args and isinstance(args[0], list) and "watch" in args[0]:
                children.append(proc)
            return proc

        env = dict(self.env)
        env.pop("PUSH_SHIT_ENDPOINT", None)
        env.pop("PUSH_SHIT_MODEL", None)
        try:
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(ps.subprocess, "Popen", side_effect=capture):
                pid, error = ps._spawn_watcher(str(self.repo), 5)
            self.assertIsNone(error, error)
            self.assertTrue(pid)
            time.sleep(1)
            (self.repo / "README.md").write_text("# Human activity\n", encoding="utf-8")
            self.git("add", "README.md")
            self.git("commit", "-m", "human activity")
            deadline = time.monotonic() + 25
            cfg = None
            while time.monotonic() < deadline:
                cfg = ps.load_config(str(self.repo))
                if cfg and cfg.get("haunt_count") == 1:
                    break
                time.sleep(0.2)
            self.assertTrue(cfg and cfg.get("haunt_count") == 1)
            self.assertEqual(ps.ledger_read(str(self.repo))[0].get("language"), "en")
            self.assertTrue(any(c[0] == "POST" and c[2]["model"] == "actual-gemma-id" for c in API.calls))
            result = self.cli("uninstall")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNotNone(children[0].wait(timeout=8))
            self.assertFalse((self.repo / ".git/push-shit/watcher.pid").exists())
            self.assertFalse((self.repo / ".git/push-shit/watcher.json").exists())
        finally:
            for proc in children:
                if proc.poll() is None:
                    proc.terminate()
                proc.wait(timeout=8)
            ps._stop_watcher(str(self.repo))

    def test_explicit_environment_overrides_saved_target_settings(self):
        self.connect([self.endpoint, "actual-gemma-id"])
        with patch.dict(os.environ, {"PUSH_SHIT_ENDPOINT": "http://127.0.0.1:4567", "PUSH_SHIT_MODEL": "override-id"}):
            settings = ps.connection_settings(str(self.repo))
        self.assertEqual(settings, {"endpoint": "http://127.0.0.1:4567", "model": "override-id"})

    def test_reply_cleaning_preserves_quotes_around_the_first_word(self):
        values = ['“fix”只是表面，记录仍然留在审阅台。', "'src/app.py' still needs a review."]
        for value in values:
            with self.subTest(value=value), patch.object(ps, "model_request", return_value={
                    "choices": [{"message": {"content": value}}]}):
                self.assertEqual(ps.llm_chat("system", "user"), value)

    def test_non_http_endpoint_is_rejected(self):
        panel, output = self.connect(["file:///etc/passwd"])
        self.assertFalse(panel.connected)
        self.assertIn("http", output.lower())


if __name__ == "__main__":
    unittest.main()
