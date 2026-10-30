import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from aprsd import conf  # noqa: F401
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF


class TestTelegramUsers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        CONF.set_override("enable_save", True)
        CONF.set_override("save_location", self.tmp.name)
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
            pathlib.Path(f"{self.tmp.name}/telegramusers.json").read_text(),
        )
        self.assertEqual({"walt": {"chat_id": 42}}, raw)

    def test_last_sender_roundtrip(self):
        self.users.set_last_sender("walt", "WB4BOR-7")
        self.assertEqual("WB4BOR-7", self.users.last_sender("walt"))

    def test_set_last_sender_is_persisted(self):
        self.users.set_last_sender("walt", "WB4BOR-7")
        raw = json.loads(
            pathlib.Path(f"{self.tmp.name}/telegramusers.json").read_text(),
        )
        self.assertEqual("WB4BOR-7", raw["walt"]["last_sender"])

    def test_lock_is_reentrant(self):
        self.assertTrue(self.users.lock.acquire(blocking=False))
        self.assertTrue(self.users.lock.acquire(blocking=False))
        self.users.lock.release()
        self.users.lock.release()

    def test_load_existing_file_does_not_deadlock(self):
        # objectstore.load() takes self.lock and then len(self), which takes
        # it again. A plain Lock hangs every APRSD start after the first.
        pathlib.Path(f"{self.tmp.name}/telegramusers.json").write_text(
            '{"walt": {"chat_id": 42}}',
        )
        script = (
            "from aprsd import conf;"  # noqa: F401 - registers the core opts
            "from oslo_config import cfg;"
            "cfg.CONF.set_override('enable_save', True);"
            f"cfg.CONF.set_override('save_location', {self.tmp.name!r});"
            "from aprsd_telegram_plugin.telegram import TelegramUsers;"
            "users = TelegramUsers();"
            "users.load();"
            "print(users.chat_id('walt'))"
        )
        out = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual("42", out.stdout.strip(), out.stderr)

    def test_unknown_user_is_none(self):
        self.assertIsNone(self.users.chat_id("nobody"))
        self.assertIsNone(self.users.last_sender("nobody"))
