import asyncio
import types
import unittest
from unittest import mock

from aprsd import conf  # noqa: F401
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF
GROUP = "aprsd_telegram_plugin"


def _update(text, username="walt", chat_id=42, chat_type="private"):
    return types.SimpleNamespace(
        message=types.SimpleNamespace(
            text=text,
            chat=types.SimpleNamespace(
                type=chat_type, username=username, id=chat_id,
            ),
        ),
    )


class TestNormalise(unittest.TestCase):
    def test_flattens_newlines(self):
        self.assertEqual(
            "Telegram(walt): a b", impl.normalise("a\nb", "Telegram(walt): "),
        )

    def test_drops_non_ascii(self):
        self.assertEqual(
            "Telegram(walt): hi ",
            impl.normalise("hi \u263a", "Telegram(walt): "),
        )

    def test_truncates_to_aprs_budget(self):
        out = impl.normalise("x" * 200, "Telegram(walt): ")
        self.assertEqual(67, len(out))


class TestMessageHandler(unittest.TestCase):
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

    def tearDown(self):
        for name in ("enabled", "apiKey", "aliases", "allowed_callsigns"):
            CONF.clear_override(name, group=GROUP)
        for name in ("callsign", "enable_save"):
            CONF.clear_override(name)
        impl.TelegramUsers._instance = None

    def _run(self, update):
        asyncio.run(self.plugin.message_handler(update, None))

    def test_ignores_group_chats(self):
        with mock.patch.object(impl.tx, "send") as send:
            self._run(_update("hi", chat_type="group"))
        send.assert_not_called()

    def test_unknown_username_is_dropped_and_not_stored(self):
        with mock.patch.object(impl.tx, "send") as send:
            self._run(_update("hi", username="stranger"))
        send.assert_not_called()
        self.assertIsNone(self.plugin.users.chat_id("stranger"))

    def test_known_alias_with_no_sender_is_dropped(self):
        with mock.patch.object(impl.tx, "send") as send:
            self._run(_update("hi"))
        send.assert_not_called()

    def test_reply_goes_to_last_aprs_sender(self):
        self.plugin.users.set_last_sender("walt", "WB4BOR-7")
        with mock.patch.object(impl.tx, "send") as send:
            self._run(_update("hi back"))
        send.assert_called_once()
        pkt = send.call_args.args[0]
        self.assertEqual("WB4BOR", pkt.from_call)
        self.assertEqual("WB4BOR-7", pkt.to_call)
        self.assertEqual("Telegram(walt): hi back", pkt.message_text)
        self.assertEqual(42, self.plugin.users.chat_id("walt"))
