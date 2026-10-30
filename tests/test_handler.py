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
    message = types.SimpleNamespace(
        text=text,
        chat=types.SimpleNamespace(
            type=chat_type, username=username, id=chat_id,
        ),
    )
    return types.SimpleNamespace(
        message=message, effective_message=message,
    )


class TestNormalise(unittest.TestCase):
    def test_flattens_newlines(self):
        self.assertEqual(
            "Telegram(walt): a b", impl.normalise("a\nb", "Telegram(walt): "),
        )

    def test_drops_non_ascii(self):
        self.assertEqual(
            "Telegram(walt): hi",
            impl.normalise("hi \u263a", "Telegram(walt): "),
        )

    def test_truncates_to_aprs_budget(self):
        out = impl.normalise("x" * 200, "Telegram(walt): ")
        self.assertEqual(67, len(out))

    def test_strips_control_characters(self):
        self.assertEqual(
            "Telegram(walt): a[31mb",
            impl.normalise("a\x1b[31mb\x00", "Telegram(walt): "),
        )


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

    def test_update_without_a_message_is_ignored(self):
        update = types.SimpleNamespace(message=None, effective_message=None)
        with mock.patch.object(impl.tx, "send") as send:
            self._run(update)
        send.assert_not_called()

    def test_changed_chat_id_rebinds_and_drops_the_old_route(self):
        self.plugin.users.set_seen("walt", 41)
        self.plugin.users.set_last_sender("walt", "WB4BOR-7")
        with mock.patch.object(impl.tx, "send") as send:
            self._run(_update("different account", chat_id=42))
        self.assertEqual(42, self.plugin.users.chat_id("walt"))
        self.assertIsNone(self.plugin.users.last_sender("walt"))
        send.assert_not_called()
