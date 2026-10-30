import unittest
from unittest import mock

from aprsd import conf  # noqa: F401
from aprsd import packets
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF
GROUP = "aprsd_telegram_plugin"


class TestTelegramChatPlugin(unittest.TestCase):
    def setUp(self):
        CONF.set_override("callsign", "WB4BOR")
        CONF.set_override("enabled", True, group=GROUP)
        CONF.set_override("apiKey", "123:fake", group=GROUP)
        CONF.set_override("aliases", ["wb=@walt"], group=GROUP)
        CONF.set_override("allowed_callsigns", ["WB4BOR"], group=GROUP)
        CONF.set_override("enable_save", False)
        impl.TelegramUsers._instance = None
        with mock.patch.object(
            impl.TelegramChatPlugin, "create_threads", return_value=[],
        ):
            self.plugin = impl.TelegramChatPlugin()
        self.plugin.running = True
        self.plugin.thread = mock.Mock()

    def tearDown(self):
        for name in ("enabled", "apiKey", "aliases", "allowed_callsigns"):
            CONF.clear_override(name, group=GROUP)
        CONF.clear_override("callsign")
        CONF.clear_override("enable_save")
        impl.TelegramUsers._instance = None

    def _packet(self, from_call="WB4BOR-7", text="tg wb hi there"):
        return packets.MessagePacket(
            from_call=from_call, to_call="WB4BOR", message_text=text,
        )

    def test_disabled_without_api_key(self):
        CONF.set_override("apiKey", "", group=GROUP)
        with mock.patch.object(
            impl.TelegramChatPlugin, "create_threads", return_value=[],
        ):
            plugin = impl.TelegramChatPlugin()
        self.assertFalse(plugin.enabled)

    def test_disabled_when_option_is_false(self):
        CONF.set_override("enabled", False, group=GROUP)
        with mock.patch.object(
            impl.TelegramChatPlugin, "create_threads", return_value=[],
        ):
            plugin = impl.TelegramChatPlugin()
        self.assertFalse(plugin.enabled)

    def test_unauthorized_callsign(self):
        self.assertEqual(
            "Unauthorized",
            self.plugin.process(self._packet(from_call="N0CALL")),
        )

    def test_too_few_words(self):
        self.assertEqual(
            "invalid request",
            self.plugin.process(self._packet(text="tg wb")),
        )

    def test_unknown_alias(self):
        self.assertEqual(
            "Unknown telegram alias 'zz'",
            self.plugin.process(self._packet(text="tg zz hi")),
        )

    def test_alias_user_never_messaged_bot(self):
        self.assertEqual(
            "Need a message from @walt on Telegram first",
            self.plugin.process(self._packet()),
        )

    def test_happy_path_delivers_and_records_sender(self):
        self.plugin.users.set_seen("walt", 42)
        result = self.plugin.process(self._packet())
        self.assertEqual(packets.NULL_MESSAGE, result)
        self.plugin.thread.send.assert_called_once_with(
            "walt", 42, "WB4BOR-7: hi there",
        )
        self.assertEqual("WB4BOR-7", self.plugin.users.last_sender("walt"))

    def test_not_running_when_thread_absent(self):
        self.plugin.users.set_seen("walt", 42)
        self.plugin.thread = None
        self.assertEqual(
            "Telegram plugin is not running",
            self.plugin.process(self._packet()),
        )

    def test_create_threads_marks_running(self):
        with mock.patch.object(impl, "TelegramThread") as thread:
            self.assertEqual([thread.return_value], self.plugin.create_threads())
        self.assertTrue(self.plugin.running)

    def test_not_running_after_startup_failure(self):
        self.plugin.users.set_seen("walt", 42)
        self.plugin.running = False
        self.assertEqual(
            "Telegram plugin is not running",
            self.plugin.process(self._packet()),
        )
