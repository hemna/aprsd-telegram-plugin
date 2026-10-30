import asyncio
import threading
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
        self.plugin.enabled = True
        self.thread = impl.TelegramThread(self.plugin, "123:fake")

    def test_stop_sets_base_shutdown_event(self):
        self.thread.stop()
        self.assertTrue(self.thread._should_quit())

    def test_stop_before_start_skips_polling(self):
        self.thread.app = mock.Mock()
        self.thread.app.updater.start_polling = mock.AsyncMock()
        self.thread.stop()
        worker = threading.Thread(
            target=lambda: asyncio.run(self.thread._serve()), daemon=True,
        )
        worker.start()
        worker.join(10)
        self.assertFalse(worker.is_alive())
        self.thread.app.updater.start_polling.assert_not_called()

    def test_send_without_loop_does_not_raise(self):
        self.thread.send("walt", 42, "hello")

    def test_loop_returns_false_when_serve_exits(self):
        self.plugin.running = True
        with mock.patch.object(
            impl.TelegramThread, "_serve", new=mock.AsyncMock(),
        ):
            self.assertFalse(self.thread.loop())
        self.assertFalse(self.plugin.running)

    def test_each_loop_gets_a_fresh_stop_event(self):
        first = self.thread._async_stop
        with mock.patch.object(
            impl.TelegramThread, "_serve", new=mock.AsyncMock(),
        ):
            self.thread.loop()
        self.assertIsNot(first, self.thread._async_stop)

    def test_startup_failure_marks_not_running_but_stays_enabled(self):
        self.thread.app = mock.Mock()
        self.thread.app.initialize = mock.AsyncMock(
            side_effect=RuntimeError("bad token"),
        )
        asyncio.run(self.thread._serve())
        self.assertFalse(self.plugin.running)
        self.assertTrue(self.plugin.enabled)

    def test_send_failure_builds_aprs_packet(self):
        self.plugin.users.last_sender.return_value = "WB4BOR-7"
        pkt = self.thread._failure_packet("walt", RuntimeError("blocked"))
        self.assertEqual("WB4BOR-7", pkt.to_call)
        self.assertEqual("Telegram send failed: blocked", pkt.message_text)

    def test_send_failure_without_sender_builds_nothing(self):
        self.plugin.users.last_sender.return_value = None
        self.assertIsNone(
            self.thread._failure_packet("walt", RuntimeError("blocked")),
        )

    def test_send_failure_never_touches_the_aprs_tx_lock_inline(self):
        self.plugin.users.last_sender.return_value = "WB4BOR-7"
        future = mock.Mock()
        future.exception.return_value = RuntimeError("blocked")
        future.cancelled.return_value = False
        with mock.patch.object(impl, "threading") as threading:
            self.thread._send_done("walt", future)
        threading.Thread.assert_called_once()
        self.assertIs(impl.tx.send, threading.Thread.call_args.kwargs["target"])

    def test_cancelled_send_reports_nothing(self):
        future = mock.Mock()
        future.cancelled.return_value = True
        with mock.patch.object(impl, "threading") as threading:
            self.thread._send_done("walt", future)
        threading.Thread.assert_not_called()
