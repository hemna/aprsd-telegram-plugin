import asyncio
import threading
import unittest
from unittest import mock

from aprsd import conf  # noqa: F401
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF


def fake_app():
    app = mock.Mock()
    app.initialize = mock.AsyncMock()
    app.start = mock.AsyncMock()
    app.updater.start_polling = mock.AsyncMock()
    app.updater.stop = mock.AsyncMock()
    app.stop = mock.AsyncMock()
    app.shutdown = mock.AsyncMock()
    return app


class TestTelegramThread(unittest.TestCase):
    def setUp(self):
        impl.TelegramUsers._instance = None
        self.plugin = mock.Mock()
        self.plugin.enabled = True
        self.plugin.running = False
        self.thread = impl.TelegramThread(self.plugin, "123:fake")

    def _run_serve(self, timeout=10):
        worker = threading.Thread(
            target=lambda: asyncio.run(self.thread._serve()), daemon=True,
        )
        worker.start()
        worker.join(timeout)
        self.assertFalse(worker.is_alive(), "serve did not return")

    def test_stop_sets_base_shutdown_event(self):
        self.thread.stop()
        self.assertTrue(self.thread._should_quit())

    def test_stop_before_start_skips_polling(self):
        # All startup steps are awaitable, so nothing but the stop flag can
        # end _serve() early.
        self.thread.app = fake_app()
        self.thread.stop()
        self._run_serve()
        self.thread.app.initialize.assert_not_called()
        self.thread.app.updater.start_polling.assert_not_called()

    def test_send_without_loop_does_not_raise(self):
        self.thread.send("walt", 42, "hello", "WB4BOR-7")

    def test_loop_returns_false_and_clears_running(self):
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

    def test_startup_failure_leaves_app_untouched(self):
        self.thread.app = fake_app()
        self.thread.app.initialize.side_effect = RuntimeError("bad token")
        asyncio.run(self.thread._serve())
        self.assertFalse(self.plugin.running)
        self.assertTrue(self.plugin.enabled)
        self.thread.app.stop.assert_not_awaited()
        self.thread.app.shutdown.assert_not_awaited()

    def test_polling_failure_stops_and_shuts_down_started_app(self):
        self.thread.app = fake_app()
        self.thread.app.updater.start_polling.side_effect = RuntimeError("429")
        asyncio.run(self.thread._serve())
        self.assertFalse(self.plugin.running)
        self.thread.app.stop.assert_awaited_once()
        self.thread.app.shutdown.assert_awaited_once()

    def test_running_is_set_only_after_polling_starts(self):
        self.thread.app = fake_app()
        self.thread.app.updater.start_polling.side_effect = self.thread.stop
        asyncio.run(self.thread._serve())
        self.assertTrue(self.plugin.running)

    def test_send_failure_builds_aprs_packet(self):
        pkt = self.thread._failure_packet("WB4BOR-7", RuntimeError("blocked"))
        self.assertEqual("WB4BOR-7", pkt.to_call)
        self.assertEqual("Telegram send failed: blocked", pkt.message_text)
        self.assertIsNone(self.thread._failure_packet(None, RuntimeError("x")))

    def test_send_failure_is_dispatched_to_a_started_thread(self):
        future = mock.Mock()
        future.exception.return_value = RuntimeError("blocked")
        future.cancelled.return_value = False
        with mock.patch.object(impl, "threading") as threading:
            self.thread._send_done("walt", "WB4BOR-7", future)
        threading.Thread.assert_called_once()
        self.assertIs(impl.tx.send, threading.Thread.call_args.kwargs["target"])
        threading.Thread.return_value.start.assert_called_once()

    def test_send_failure_without_sender_does_not_spawn_a_thread(self):
        future = mock.Mock()
        future.exception.return_value = RuntimeError("blocked")
        future.cancelled.return_value = False
        with mock.patch.object(impl, "threading") as threading:
            self.thread._send_done("walt", None, future)
        threading.Thread.assert_not_called()

    def test_cancelled_send_reports_nothing(self):
        future = mock.Mock()
        future.cancelled.return_value = True
        with mock.patch.object(impl, "threading") as threading:
            self.thread._send_done("walt", "WB4BOR-7", future)
        threading.Thread.assert_not_called()
