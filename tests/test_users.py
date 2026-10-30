import json
import pathlib
import tempfile
import unittest

from aprsd import conf  # noqa: F401
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF


class TestTelegramUsers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        CONF.set_override("enable_save", True)
        CONF.set_override("save_location", self.tmp)
        impl.TelegramUsers._instance = None
        self.users = impl.TelegramUsers()

    def tearDown(self):
        CONF.clear_override("enable_save")
        CONF.clear_override("save_location")
        impl.TelegramUsers._instance = None

    def test_set_seen_is_readable_case_insensitively(self):
        self.users.set_seen("Walt", 42)
        self.assertEqual(42, self.users.chat_id("walt"))

    def test_set_seen_writes_json_immediately(self):
        self.users.set_seen("walt", 42)
        raw = json.loads(
            pathlib.Path(f"{self.tmp}/telegramusers.json").read_text(),
        )
        self.assertEqual({"walt": {"chat_id": 42}}, raw)

    def test_last_sender_roundtrip(self):
        self.users.set_last_sender("walt", "WB4BOR-7")
        self.assertEqual("WB4BOR-7", self.users.last_sender("walt"))

    def test_unknown_user_is_none(self):
        self.assertIsNone(self.users.chat_id("nobody"))
        self.assertIsNone(self.users.last_sender("nobody"))
