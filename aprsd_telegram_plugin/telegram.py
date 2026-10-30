import logging
import threading

from aprsd import packets, plugin, threads  # noqa: F401
from aprsd.threads import tx  # noqa: F401
from aprsd.utils import objectstore
from oslo_config import cfg


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
            cls._instance.lock = threading.Lock()
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

    def chat_id(self, username):
        with self.lock:
            return self.data.get(username.casefold(), {}).get("chat_id")

    def last_sender(self, username):
        with self.lock:
            return self.data.get(username.casefold(), {}).get("last_sender")
