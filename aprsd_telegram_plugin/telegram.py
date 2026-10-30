import asyncio
import functools
import logging
import threading

from aprsd import packets, plugin, threads
from aprsd.threads import tx
from aprsd.utils import objectstore
from oslo_config import cfg
from telegram.ext import Application, MessageHandler, filters

import aprsd_telegram_plugin
from aprsd_telegram_plugin import conf  # noqa: F401


CONF = cfg.CONF
LOG = logging.getLogger("APRSD")


def parse_aliases(raw):
    """Turn ["wb=@walt"] into {"wb": "walt"}."""
    aliases = {}
    for entry in raw or []:
        alias, sep, username = entry.partition("=")
        alias = alias.strip().casefold()
        username = username.strip().lstrip("@").casefold()
        if not sep or not alias or not username:
            LOG.warning(f"Ignoring malformed telegram alias entry: {entry!r}")
            continue
        aliases[alias] = username
    return aliases


def is_allowed(from_call, allowed, fallback):
    """Is this APRS callsign allowed to use the plugin? Any SSID is fine."""
    allowed = [c.strip().upper() for c in (allowed or [])] or [fallback.upper()]
    call = (from_call or "").upper()
    return any(call == entry or call.startswith(entry + "-") for entry in allowed)


def normalise(text, prefix):
    """Flatten text to one ASCII APRS line inside the 67 char budget."""
    text = " ".join(text.split())
    text = text.encode("ascii", "ignore").decode()
    return prefix + text[: max(0, 67 - len(prefix))]


class TelegramUsers(objectstore.ObjectStoreMixin):
    """Remembers each telegram username's chat id and last APRS sender.

    Telegram has no username -> id lookup, so the id is learned the first
    time that account messages the bot and kept on disk between restarts.
    """

    _instance = None
    data = {}

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # objectstore.load() takes the lock, then len(self) takes it again.
            cls._instance.lock = threading.RLock()
            cls._instance.data = {}
            cls._instance._init_store()
        return cls._instance

    def _record(self, username):
        return self.data.setdefault(username.casefold(), {})

    def set_seen(self, username, chat_id):
        with self.lock:
            self._record(username)["chat_id"] = chat_id
        self.save()

    def set_last_sender(self, username, callsign):
        with self.lock:
            self._record(username)["last_sender"] = callsign
        self.save()

    def chat_id(self, username):
        with self.lock:
            return self.data.get(username.casefold(), {}).get("chat_id")

    def last_sender(self, username):
        with self.lock:
            return self.data.get(username.casefold(), {}).get("last_sender")


class TelegramChatPlugin(plugin.APRSDRegexCommandPluginBase):
    """Bridges APRS messages to Telegram and back."""

    command_regex = "^[tT][gG]"
    command_name = "telegram"

    enabled = False
    running = False
    thread = None
    aliases = {}
    users = None

    def help(self):
        return (
            "telegram: send 'tg <alias> <text>' to message a telegram user"
        )

    def setup(self):
        self.enabled = False
        if not CONF.aprsd_telegram_plugin.enabled:
            LOG.warning("Telegram plugin is disabled in config")
            return
        if not CONF.aprsd_telegram_plugin.apiKey:
            LOG.error("Failed to find config aprsd_telegram_plugin.apiKey")
            return
        self.aliases = parse_aliases(CONF.aprsd_telegram_plugin.aliases)
        self.users = TelegramUsers()
        self.users.load()
        self.enabled = True

    def create_threads(self):
        if not self.enabled:
            return []
        self.thread = TelegramThread(
            self, CONF.aprsd_telegram_plugin.apiKey,
        )
        self.running = True
        return [self.thread]

    def process(self, packet):
        if not self.running or self.thread is None:
            return "Telegram plugin is not running"

        if not is_allowed(
            packet.from_call,
            CONF.aprsd_telegram_plugin.allowed_callsigns,
            CONF.callsign,
        ):
            return "Unauthorized"

        parts = (packet.message_text or "").split()
        if len(parts) < 3:
            return "invalid request"

        username = self.aliases.get(parts[1].casefold())
        if username is None:
            return f"Unknown telegram alias '{parts[1]}'"

        chat_id = self.users.chat_id(username)
        if chat_id is None:
            return f"Need a message from @{username} on Telegram first"

        self.users.set_last_sender(username, packet.from_call)
        self.thread.send(
            username, chat_id, f"{packet.from_call}: {' '.join(parts[2:])}",
        )
        return packets.NULL_MESSAGE

    async def message_handler(self, update, context):
        """Called when a telegram user messages the bot."""
        chat = update.message.chat
        if chat.type != "private":
            LOG.info(f"Ignoring telegram {chat.type} chat {chat.id}")
            return

        username = (chat.username or "").casefold()
        if username not in self.aliases.values():
            LOG.info(
                f"Ignoring telegram message from unknown user @{chat.username}",
            )
            return

        if self.users.chat_id(username) is None:
            self.users.set_seen(username, chat.id)
            LOG.info(f"Learned telegram @{username} chat_id={chat.id}")

        sender = self.users.last_sender(username)
        if sender is None:
            LOG.info(f"No APRS sender for @{username} yet, dropping reply")
            return

        pkt = packets.MessagePacket(
            from_call=CONF.callsign,
            to_call=sender,
            message_text=normalise(
                update.message.text, f"Telegram({username}): ",
            ),
        )
        await asyncio.get_running_loop().run_in_executor(None, tx.send, pkt)


class TelegramThread(threads.APRSDThread):
    """Owns the telegram polling loop and keeps it stoppable."""

    def __init__(self, plugin, token):
        super().__init__("TelegramThread")
        self.plugin = plugin
        self.app = Application.builder().token(token).build()
        self.app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, plugin.message_handler,
            ),
        )
        self._loop = None
        # Created here, not in _serve(), so stop() can never miss the window
        # where the thread exists but the coroutine has not run yet.
        self._async_stop = asyncio.Event()

    def loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()
            asyncio.set_event_loop(None)
            self._loop = None
        return False

    async def _serve(self):
        if self._async_stop.is_set():
            return
        try:
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling()
        except Exception:
            LOG.exception("Telegram bot failed to start, disabling plugin")
            self.plugin.running = False
            return

        LOG.info("Telegram bot is polling")
        await self._async_stop.wait()
        LOG.info("Telegram bot is stopping")
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

    def stop(self):
        super().stop()
        if self._loop is None or self._loop.is_closed():
            self._async_stop.set()
            return
        try:
            self._loop.call_soon_threadsafe(self._async_stop.set)
        except RuntimeError:
            # Loop closed between the check and the call; nothing is polling.
            self._async_stop.set()

    def send(self, username, chat_id, text):
        if self._loop is None or self._loop.is_closed():
            LOG.warning(f"No telegram loop running, dropping message to {username}")
            return
        future = asyncio.run_coroutine_threadsafe(
            self.app.bot.send_message(chat_id=chat_id, text=text),
            self._loop,
        )
        future.add_done_callback(functools.partial(self._send_done, username))

    def _failure_packet(self, username, ex):
        sender = self.plugin.users.last_sender(username)
        if sender is None:
            return None
        return packets.MessagePacket(
            from_call=CONF.callsign,
            to_call=sender,
            message_text=f"Telegram send failed: {ex}",
        )

    def _send_done(self, username, future):
        if future.cancelled():
            return
        ex = future.exception()
        if ex is None:
            return
        LOG.error(f"Telegram send to @{username} failed: {ex!r}")
        pkt = self._failure_packet(username, ex)
        if pkt is None:
            return
        # tx.send blocks and retries, so keep it off the telegram loop; the
        # loop may also already be gone by the time this callback runs.
        threading.Thread(target=tx.send, args=(pkt,), daemon=True).start()
