from __future__ import annotations

import unittest
from giftify.auth import parse_telegram_init_data, extract_user_id_from_init_data


class TestTelegramAuth(unittest.TestCase):
    def test_extract_user_id_from_raw_init_data(self) -> None:
        init_data = 'user=%7B%22id%22%3A123456789%2C%22first_name%22%3A%22Test%22%7D&auth_date=1600000000'
        user_id = extract_user_id_from_init_data(init_data)
        self.assertEqual(user_id, 123456789)

    def test_extract_user_id_empty(self) -> None:
        self.assertIsNone(extract_user_id_from_init_data(""))

    def test_extract_user_id_invalid(self) -> None:
        self.assertIsNone(extract_user_id_from_init_data("invalid_data"))


if __name__ == "__main__":
    unittest.main()
