import contextlib
import io
import unittest
from unittest.mock import patch

import push_shit as ps
from tests.support import RepoCase


class PanelTests(RepoCase):
    def test_tty_draw_does_not_erase_history(self):
        output = io.StringIO()
        output.write("previous command and result\n")
        panel = ps._Panel()
        with patch.object(panel, "target", str(self.repo)), \
                patch.object(output, "isatty", return_value=True), \
                contextlib.redirect_stdout(output):
            ps._panel_draw(panel)
        self.assertNotIn("\033[2J", output.getvalue())
        self.assertNotIn("\033[H", output.getvalue())
        self.assertIn("previous command and result", output.getvalue())

    def test_help_and_slash_help_have_detailed_equivalent_guidance(self):
        plain = self.panel(["help", "quit"])
        slash = self.panel(["/help", "quit"])
        # Piped-command echo differs; the actual help output must be identical.
        self.assertEqual(plain, slash.replace("\n/help\n", "\nhelp\n", 1))
        for word in ("示例", "uninstall", "默认", "停止", "不会"):
            self.assertIn(word, plain)

    def test_command_specific_help_has_example_and_side_effects(self):
        output = self.panel(["/help haunt", "quit"])
        self.assertIn("haunt bg", output)
        self.assertIn("提交", output)
        self.assertIn("示例", output)

    def test_help_distinguishes_request_budget_from_hard_wall_clock_limit(self):
        with patch.object(ps, "llm_chat", side_effect=AssertionError("help must not request a model")):
            zh = self.panel(["lang ui zh", "/help haunt", "quit"])
            en = self.panel(["lang ui en", "/help haunt", "quit"])
        self.assertIn("墙钟", zh)
        self.assertIn("wall-clock", en)
        self.assertIn("request-timeout", en)
        self.assertNotIn("share one deadline", en)
        self.assertFalse((self.repo / ".git/push-shit/config.json").exists())
        self.assertFalse((self.repo / ".git/hooks/pre-push").exists())

    def test_help_is_discoverable_on_startup(self):
        self.assertIn("/help", self.panel(["quit"]))

    def test_quoted_windows_target_with_spaces(self):
        path = self.repo / "folder with spaces"
        path.mkdir()
        seen = []

        def target(panel, rest):
            seen.append(rest)

        with patch.object(ps, "_panel_target", side_effect=target):
            self.panel([f'target "{path.as_posix()}"', "quit"])
        self.assertEqual(seen, [[path.as_posix()]])

    def test_bad_quote_is_a_recoverable_input_error(self):
        output = self.panel(['target "unfinished', "help", "quit"])
        self.assertIn("引号", output)
        self.assertIn("示例", output)

    def test_invalid_mutating_command_arguments_are_rejected(self):
        with patch.object(ps, "_panel_haunt") as haunt, \
                patch.object(ps, "_panel_arm") as arm, \
                patch.object(ps, "cmd_uninstall") as uninstall:
            output = self.panel(["haunt typo", "haunt bg nope", "haunt bg 1 2",
                                 "uninstall typo", "quit"])
        haunt.assert_not_called()
        arm.assert_not_called()
        uninstall.assert_not_called()
        self.assertIn("用法", output)

    def test_no_full_status_redraw_after_every_command(self):
        output = self.panel(["help", "help", "quit"])
        self.assertEqual(output.count("GIT PUSH SHIT — OPERATOR CONSOLE"), 1)


if __name__ == "__main__":
    unittest.main()
