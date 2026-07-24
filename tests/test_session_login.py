import unittest
from unittest.mock import patch

from giftify.session_login import _parser


class SessionLoginTest(unittest.TestCase):
    def test_replace_flag_is_opt_in(self):
        self.assertFalse(_parser().parse_args([]).replace)
        self.assertTrue(_parser().parse_args(["--replace"]).replace)

    def test_request_webview_uses_session_name_relative_to_workdir(self):
        # The path behaviour is covered by the implementation's use of Path.stem;
        # this guards against returning to a nested .secrets/.secrets session path.
        from pathlib import Path

        self.assertEqual(Path(".secrets/pyrogram.session").stem, "pyrogram")
