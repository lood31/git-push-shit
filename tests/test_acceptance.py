"""Acceptance tooling must fail closed; an offline marker is never a model pass."""
import json
import subprocess
import sys
from unittest.mock import patch

from tests import playground_qa as qa
from tests.support import RepoCase


class AcceptanceHarnessTests(RepoCase):
    def test_connection_failure_in_successful_panel_process_is_rejected(self):
        with self.assertRaises(AssertionError):
            qa.validate_connection(self.repo, {"endpoint": "http://127.0.0.1:9931", "model": "gemma"},
                                   "○ 接通失败：服务不可达\n")

    def test_saved_endpoint_and_model_must_match(self):
        private = self.repo / ".git/push-shit"
        private.mkdir(exist_ok=True)
        (private / "connection.json").write_text(json.dumps({"endpoint": "http://127.0.0.1:1", "model": "wrong"}),
                                                encoding="utf-8")
        with self.assertRaises(AssertionError):
            qa.validate_connection(self.repo, {"endpoint": "http://127.0.0.1:9931", "model": "gemma"}, "● connected")

    def test_timeout_retains_partial_stdout_and_stderr(self):
        captured = []
        error = subprocess.TimeoutExpired(["fake"], 1, output=b"partial stdout", stderr=b"partial stderr")
        with patch.object(qa.subprocess, "run", side_effect=error), \
                patch.object(qa, "record_failure", side_effect=captured.append), self.assertRaises(subprocess.TimeoutExpired):
            qa.command(self.repo, ["fake"])
        self.assertEqual(captured[0]["stdout"], "partial stdout")
        self.assertEqual(captured[0]["stderr"], "partial stderr")
        self.assertEqual(captured[0]["status"], "timeout")

    def test_setup_failure_has_a_batch_failure_record(self):
        captured = []
        output = self.repo / ".git/qa-evidence"
        argv = ["qa", "--setup", "--batch", "setup-failed", "--target", str(self.repo / "new"), "--output", str(output)]
        with patch.object(sys, "argv", argv), patch.object(qa, "BASE", output), \
                patch.object(qa, "setup", side_effect=RuntimeError("setup failed")), \
                patch.object(qa, "save", side_effect=lambda _path, row: captured.append(dict(row))), \
                patch.object(qa, "record_failure"), self.assertRaises(RuntimeError):
            qa.main()
        self.assertTrue(any("setup failed" in row.get("failure", "") for row in captured))

    def test_unavailable_model_does_not_even_create_a_sandbox(self):
        target = self.repo / "new-playground"
        with patch.object(qa, "HOME", target), patch.object(qa, "ready_model", side_effect=RuntimeError("model unavailable")), self.assertRaises(RuntimeError):
            qa.setup(target, "unavailable-test")
        self.assertFalse(target.exists())
