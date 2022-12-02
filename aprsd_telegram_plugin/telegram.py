import datetime
import logging
import threading
import time

from aprsd import messaging, objectstore, plugin, threads
from telegram.ext import Filters, MessageHandler, Updater

import aprsd_telegram_plugin


LOG = logging.getLogger("APRSD")


class TelegramUsers(objectstore.ObjectStoreMixin):
    """Class to automatically store telegram user ids between starts.

    Telegram doesn't provide an API for looking up an userid from
    username, so we have to save it off for better user experience.

    Unfortunately, we can't get the userid, until the telegram user
    sends a message to the bot FIRST.
    """
    _instance = None
    data = {}
    config = None
    _shortcuts = {}

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.lock = threading.Lock()
            cls._instance.config = kwargs["config"]
            cls._instance.data = {}
            if kwargs["config"].exists("services.telegram.shortcuts"):
                cls._instance._shortcuts = kwargs["config"].get("services.telegram.shortcuts")
            else:
                cls._instance._shortcuts = None
            cls._instance._init_store()
        return cls._instance

    def __getitem__(self, item):
        with self.lock:
            if item in self._shortcuts:
                item = self._shortcuts[item]
            return self.data[item]

    def __setitem__(self, item, value):
        with self.lock:
            self.data[item] = value

    def __delitem__(self, item):
        del self.data[item]

    def __contains__(self, item):
        if item in self._shortcuts:
            item = self._shortcuts[item]

        if item in self.data:
            return True
        else:
            return False

    def get_shortcuts(self):
        return self._shortcuts


class TelegramChatPlugin(plugin.APRSDRegexCommandPluginBase):

    version = aprsd_telegram_plugin.__version__
    # Look for any command that starts with w or W
    command_regex = "^[tT][gG]"
    # the command is for ?
    command_name = "telegram"

    enabled = False
    users = None

    def help(self):
        _help = [
            "telegram: Chat with a user on telegram Messenger.",
            "telegram: username has to message you first."
            "tg: Send tg <username> <message>",
        ]
        return _help

    def setup(self):
        self.enabled = True
        # Do some checks here?
        try:
            self.config.check_option(["services", "telegram", "apiKey"])
        except Exception as ex:
            LOG.error(f"Failed to find config telegram:apiKey {ex}")
            self.enabled = False
            return

        token = self.config.get("services.telegram.apiKey")

        self.users = TelegramUsers(config=self.config)
        self.users.load()

        # self.bot = telegram.Bot(token=token)
        # LOG.info(self.bot.get_me())
        LOG.info("Starting up Updater")
        try:
            self.updater = Updater(
                token=token,
                use_context=True,
                persistence=False,
            )
        except Exception as ex:
            self.enabled = False
            LOG.exception(ex)
        LOG.info("Starting up Dispatcher")

        try:
            self.dispatcher = self.updater.dispatcher
            self.dispatcher.add_handler(
                MessageHandler(
                    Filters.text & (~Filters.command),
                    self.message_handler,
                ),
            )
        except Exception as ex:
            self.enabled = False
            LOG.exception(ex)

    def message_handler(self, update, context):
        """This is called when a telegram users texts the bot."""
        LOG.info(f"{self.__class__.__name__}: Got message {update.message.text}")
        # LOG.info(f"Text {update.message.text}")
        # LOG.info(f"Chat {update.message.chat}")
        # LOG.info(f"From {update.message.from.username} : ")
        fromcall = self.config.get("aprs.login")
        tocall = self.config.get("ham.callsign")

        if update.message.chat.type == "private":
            LOG.info(f"Username {update.message.chat.username} - ID {update.message.chat.id}")
            message = "Telegram({}): {}".format(
                update.message.chat.username,
                update.message.text,
            )
            self.users[update.message.chat.username] = update.message.chat.id
            # LOG.debug(self.users)
            # LOG.info(f"{message}")
            msg = messaging.TextMessage(fromcall, tocall, message)
            msg.send()
        elif update.message.chat.type == "group":
            group_name = "noidea"
            message = "TelegramGroup({}): {}".format(
                group_name,
                update.message.text,
            )
            msg = messaging.TextMessage(fromcall, tocall, message)
            msg.send()

    def create_threads(self):
        if self.enabled:
            LOG.info("Starting TelegramThread")
            return TelegramThread(self.config, self.updater)

    def process(self, packet):
        """This is called when a received packet matches self.command_regex."""
        LOG.info("TelegramChatPlugin Plugin")

        from_callsign = packet.get("from")
        message = packet.get("message_text", None)

        if self.enabled:
            # Now we can process
            # Only allow aprsd owner to use this.
            mycall = self.config["ham"]["callsign"]

            # Only allow the owner of aprsd to send a tweet
            if not from_callsign.startswith(mycall):
                return "Unauthorized"

            # Always should have format of
            # <command> <username> <message>
            parts = message.split(" ")
            LOG.info(parts)

            if len(parts) < 3:
                return "invalid request"
            # parts[0] is the command
            username = parts[1]
            msg = " ".join(parts[2:])
            if username not in self.users:
                # Unfortunately there is no way to lookup a user ID
                # from a username right now.
                return f"Need a message from {username} first"

            bot = self.updater.bot
            bot.sendMessage(
                chat_id=self.users[username],
                text=msg,
            )

            return messaging.NULL_MESSAGE
        else:
            LOG.warning("TelegramChatPlugin is disabled.")
            return messaging.NULL_MESSAGE


class TelegramThread(threads.APRSDThread):
    def __init__(self, config, updater):
        super().__init__(self.__class__.__name__)
        self.config = config
        self.past = datetime.datetime.now()
        self.updater = updater

    def stop(self):
        self.thread_stop = True
        self.updater.stop()
        TelegramUsers(config=self.config).save()

    def loop(self):
        """We have to loop, so we can stop the thread upon CTRL-C"""
        try:
            self.updater.start_polling(
                timeout=2,
                drop_pending_updates=True,
            )
        except Exception as ex:
            LOG.exception(ex)
            return False
        # So we don't eat 100% CPU
        time.sleep(1)
        # so we can continue looping
        return True
