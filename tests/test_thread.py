import asyncio
import unittest
from unittest import mock

from aprsd import conf  # noqa: F401
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF


class TestTelegramThread(unittest.TestCase):
    def setUp(self):
        impl.TelegramUsers._instance = None
        self.plugin = mock.Mock()
        self.thread = impl.TelegramThread(self.plugin, "123:fake")

    def test_stop_sets_base_shutdown_event(self):
        self.thread.stop()
        self.assertTrue(self.thread._should_quit())

    def test_send_without_loop_does_not_raise(self):
        self.thread.send("walt", 42, "hello")

    def test_loop_returns_false_when_serve_exits(self):
        with mock.patch.object(
            impl.TelegramThread, "_serve", new=mock.AsyncMock(),
        ):
            self.assertFalse(self.thread.loop())

    def test_startup_failure_disables_plugin(self):
        self.thread.app = mock.Mock()
        self.thread.app.initialize = mock.AsyncMock(
            side_effect=RuntimeError("bad token"),
        )
        asyncio.run(self.thread._serve())
        self.assertFalse(self.plugin.enabled)

    def test_send_failure_reports_back_to_aprs(self):
        self.plugin.users.last_sender.return_value = "WB4BOR-7"
        future = mock.Mock()
        future.exception.return_value = RuntimeError("bot was blocked")
        with mock.patch.object(impl.tx, "send") as send:
            self.thread._send_done("walt", future)
        send.assert_called_once()
        self.assertEqual(
            "Telegram send failed: bot was blocked",
            send.call_args.args[0].message_text,
        )
