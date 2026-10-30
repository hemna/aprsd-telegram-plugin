# aprsd-telegram-plugin for APRSD 5.x — design

Date: 2026-10-29
Status: draft for approval
Repo: `~/devel/mine/hamradio/aprsd-plugins/archive/aprsd-telegram-plugin`

## Intent

Two-way text bridge between APRS and Telegram, for one operator and a small
set of named people:

- APRS to Telegram: the operator sends `tg <alias> <text>` to the APRSD
  callsign; the plugin delivers `<text>` to that alias's Telegram account.
- Telegram to APRS: the person replies in Telegram; the reply arrives on APRS
  addressed to the callsign that last messaged that Telegram account.

The alias is a short nickname configured in `aprsd.conf`, the same idea as
the email plugin's `email_shortcuts` (`wb=walt@walt.com`).

## Why now

Measured on 2026-10-29 against `aprsd` 5.0.2.dev1+j6e6cf4b0b (repo
`~/devel/mine/hamradio/aprsd`), the current plugin cannot do either direction:

| Probe | Result |
|---|---|
| `import aprsd_telegram_plugin.telegram` + instantiate plugin | OK (aprsd 5 API still matches) |
| `message_handler()` (Telegram to APRS) | `NoSuchOptError no such option login in group [aprs_network]` |
| `"user" in TelegramUsers()` with `shortcuts` unset (default) | `TypeError argument of type 'NoneType' is not iterable` |
| `TelegramThread.stop()` then `_should_quit()` | `False` — thread never exits |
| `pip install "python-telegram-bot<20"` (py3.12) | 13.15: `import telegram` only after `urllib3<2`, then `telegram.ext` fails on `pkg_resources` |
| same (py3.15) | `import telegram` fails: `ModuleNotFoundError: No module named 'imghdr'` |

So this is a rewrite of the Telegram side, not a patch.

## Goals

1. `tg <alias> <text>` from an allowed APRS callsign delivers to that alias's
   Telegram account.
2. A Telegram reply from an alias's account delivers to the APRS callsign that
   last messaged that account, as a message from the APRSD callsign.
3. Aliases and allowed callsigns are plain text lists in `aprsd.conf`.
4. Any number of aliases and allowed callsigns; conversations do not cross.
5. Unauthorized APRS senders are refused; unknown Telegram accounts cannot
   inject APRS traffic.
6. Works on APRSD 5.x with current Python (3.12 and newer) and the current
   Telegram library.
7. No runtime state kept in a pickle; nothing in the repo that a restart needs.

## Non-goals

- Telegram group chats, channels, media, video, stickers, inline keyboards.
  (The old `aprsd-telegram-video.yml` and the half-written `group` branch go.)
- Sending to a Telegram user who has never messaged the bot.
- Message history, message ids, delivery receipts, rate limiting of APRS.
- Multi-bot or multi-token support.
- Renaming the package or moving the repo out of `archive/`.

## Anti-goals

- A Telegram account must never be able to choose which APRS callsign its
  traffic appears to come from; that is always the APRSD callsign.
- A Telegram account must never reach an APRS callsign other than the one that
  last messaged it.
- An APRS callsign not on the allowlist must never reach Telegram.

## Constraints

- **Library**: `python-telegram-bot` 22.8 is current on PyPI (measured:
  `requires_python >=3.10`). Version 22 is async-only: `Application`,
  `filters`, `MessageHandler`, coroutine handlers, and `bot.send_message()` is
  an `async def`. The `<20` pin resolves to 13.15, which does not import on
  modern Python.
- **Threading**: APRSD 5 is thread-based. `threads.APRSDThread` gives
  `loop()`, `wait()`, `stop()` (which sets `_shutdown_event`) and a repeated
  `run()` loop that calls `loop()` and stops when `loop()` returns falsy.
  Anything that blocks inside `loop()` must still be interruptible, so a
  long-lived asyncio loop needs an explicit stop hand-off.
- **Config**: oslo.config group `aprsd_telegram_plugin`, registered by
  importing `aprsd_telegram_plugin.conf`. Measured: values in the ini file for
  this group survive late group registration (parse tolerates unknown groups,
  and the values became readable once the group was registered), so
  registration at plugin-load time is fine.
- **APRSD callsign**: `CONF.callsign` in `[DEFAULT]`. `CONF.aprs_network.login`
  does not exist in 5.x.
- **Inbound filter**: `APRSDRegexCommandPluginBase.filter()` calls
  `process()` only for messages whose `to_call == CONF.callsign`.
- **Outbound APRS**: `aprsd.threads.tx.send(packets.MessagePacket(...))`.
  APRSD truncates message text to 67 characters itself
  (`aprsd/packets/core.py`), so the plugin does not.
- **Persistence**: `objectstore.ObjectStoreMixin` writes
  `<save_location>/<classname>.json` when `CONF.enable_save` is set.
- **Telegram identifier reachability** (decided because the operator does not
  know numeric ids): the Bot API accepts a numeric `chat_id` for a private
  user, or `@channelusername` only for public channels/supergroups. There is no
  username-to-id lookup. So config stores `@username`, and the plugin learns
  and persists each `username -> chat_id` the first time that account messages
  the bot.

## Decided (operator's words or confirmed)

- One operator, several allowed APRS callsigns, several Telegram aliases.
- Alias table in `aprsd.conf`, shaped like the email plugin's shortcuts.
- Reply goes to the APRS sender carried in the packet, not to a fixed callsign.
- Alias values are Telegram usernames (`@walt`), because numeric ids are
  unknown; ids are learned when the person first messages the bot.

## Design

### Config

```ini
[DEFAULT]
callsign = WB4BOR
enabled_plugins = aprsd_telegram_plugin.telegram.TelegramChatPlugin

[aprsd_telegram_plugin]

# Turn the plugin on. Defaults to false so an installed plugin does nothing
# until it is configured.
enabled = true

# Bot token from @BotFather. Required.
apiKey = 123456:ABC...

# alias=@telegram_username, comma separated.
aliases = wb=@walt, cl=@craigerl, kid=@junior

# APRS callsigns allowed to use `tg`. A call with any SSID of a listed
# callsign is accepted (WB4BOR matches WB4BOR-7). Empty means only
# [DEFAULT] callsign may use the plugin.
allowed_callsigns = WB4BOR, N0CALL
```

`aliases` and `allowed_callsigns` are `cfg.ListOpt` (oslo splits on commas),
matching the email plugin's shortcut style so the generated sample config looks
familiar.

### Components

`aprsd_telegram_plugin/conf/telegram.py`
- `cfg.StrOpt("apiKey", secret=True)`
- `cfg.ListOpt("aliases")`
- `cfg.ListOpt("allowed_callsigns")`
- `cfg.BoolOpt("enabled", default=False)`
- Drop `callsign` and `shortcuts` (replaced by `allowed_callsigns` and
  `aliases`).

`aprsd_telegram_plugin/telegram.py`

1. `parse_aliases(raw) -> dict[str, str]`
   `"wb=@walt"` becomes `{"wb": "walt"}`; leading `@` stripped and both sides
   lowercased, because Telegram usernames and typed commands vary in case.
   Entries without `=` or with an empty side are skipped with a warning. Pure
   function, unit tested.

2. `is_allowed(callsign, allowed) -> bool`
   Exact match, or `callsign.startswith(entry + "-")` so SSIDs work. Empty
   allowlist means `CONF.callsign` only. Pure function, unit tested.

3. `TelegramUsers(objectstore.ObjectStoreMixin)`
   Singleton holding `{username: {"chat_id": int, "last_sender": str}}`,
   loaded in `setup()` and saved when the thread stops. Written to
   `telegramusers.json`. No shortcuts inside it, so the `None` iteration bug
   cannot come back. `set_seen(username, chat_id)` and
   `set_last_sender(username, callsign)` are the only mutators.

4. `TelegramChatPlugin(plugin.APRSDRegexCommandPluginBase)`
   `command_regex = "^[tT][gG]"`, `command_name = "telegram"`.
   - `setup()`: return disabled if `enabled` is false or `apiKey` is empty;
     build `self.aliases = parse_aliases(...)`; construct `TelegramUsers()` and
     `load()` it. No Telegram client is built here, so importing or
     constructing the plugin never touches the network.
   - `create_threads()`: return `[TelegramThread(self, token)]` — a list, which
     is what `APRSDPluginBase` expects — and keep it as `self.thread`. The
     thread builds the `Application` (offline) in its constructor.
   - `process(packet)`: sync, runs on the APRSD RX thread.
     1. `is_allowed(packet.from_call)` else return `"Unauthorized"`.
     2. Split `packet.message_text`; fewer than 3 parts returns
        `"invalid request"`.
     3. `alias -> @username` lookup; unknown returns
        `"Unknown telegram alias '<x>'"`.
     4. Resolve `chat_id` from `TelegramUsers`; if the person never messaged
        the bot, return `"Need a message from @<username> on Telegram first"`.
     5. Record `last_sender = packet.from_call`.
     6. Deliver through the thread's non-blocking send, text
        `"<from_call>: <text>"`; failures come back later as an APRS message.
     7. Return `packets.NULL_MESSAGE`.
   - `message_handler(update, context)`: `async def`, runs on the asyncio
     thread.
     1. Ignore non-private chats.
     2. If the sender's username is not a configured alias, log and drop. No
        APRS output, no reply to the Telegram user.
     3. Otherwise record `username -> chat_id` (first time only, saved
        immediately) and log it once at INFO so the operator can see it.
     4. If no `last_sender` for that username, log and drop.
     5. Normalise the text, then `tx.send(packets.MessagePacket(
        from_call=CONF.callsign, to_call=last_sender,
        message_text="Telegram(<username>): <text>"))` via
        `run_in_executor`.

5. `TelegramThread(threads.APRSDThread)`
   - Owns one `asyncio` event loop created inside `loop()`.
   - `loop()`: `asyncio.run(self._serve())`, then return `False` so the base
     loop exits. `_serve()` does `await app.initialize()`,
     `await app.start()`, `await updater.start_polling(...)`,
     `await self._async_stop.wait()`, then `updater.stop()`, `app.stop()`,
     `app.shutdown()` in that order.
   - `stop()`: `super().stop()` (sets `_shutdown_event`, fixing the measured
     hang) then `self._loop.call_soon_threadsafe(self._async_stop.set)`.
   - `send(chat_id, text)`: schedules
   `self.app.bot.send_message(...)` on the loop with
   `asyncio.run_coroutine_threadsafe` and returns immediately; a failure
   callback logs it and sends `"Telegram send failed: <reason>"` to the APRS
   sender. Does nothing but log if the loop is absent or closed.

### Data flow

```
APRS  WB4BOR-7 > APRSD : "tg wb hello"
        filter() -> process() -> allowlist -> alias -> chat_id -> thread.send()
Telegram  bot -> @walt : "WB4BOR-7: hello"
        reply "hi back"
Telegram  @walt -> bot : "hi back"
        message_handler() -> username -> last_sender WB4BOR-7
APRS  APRSD > WB4BOR-7 : "Telegram(walt): hi back"
```

### Failure behaviour

Every refusal on the APRS side returns a short APRS reply to the sender; every
drop on the Telegram side is logged and silent, so an unknown Telegram account
gets no signal that a bot exists.

- **Startup**: if the token is missing, rejected, or `Application.initialize()`
  raises, the plugin logs the reason, sets `enabled = False`, and the thread
  exits (`loop()` returns `False`). No retry loop — `APRSDThread.run()` would
  otherwise re-run a failing startup every second forever. A later `tg`
  returns `"Telegram plugin is not running"`.
- **Send to Telegram**: fire-and-forget. `process()` schedules the send on the
  asyncio loop and returns `NULL_MESSAGE` immediately, so a slow or throttled
  Telegram call never holds the APRSD packet thread. If the send fails, the
  error is logged and a short `"Telegram send failed: <reason>"` goes back to
  the APRS sender through `tx.send`.
- **Send to APRS from the bot thread**: `tx.send` internally sleeps on retry,
  so it runs through `run_in_executor` and never blocks the Telegram event
  loop.
- **Reply with nowhere to go** (not an alias, or no `last_sender` yet): logged
  and dropped.
- **Learned ids**: `set_seen()` writes the store immediately for a first-seen
  alias, because the thread is a daemon and a `kill -9` would otherwise lose
  it.

### Text normalisation

APRS payloads are ASCII and 67 characters, and `Telegram(<username>): ` spends
part of that budget. On the APRS-bound path the plugin therefore flattens
newlines to spaces, drops non-ASCII characters, and truncates the person's text
so the finished payload fits; no splitting into multiple packets.
`_filter_for_send()` then applies APRSD's own 67-character cut as a backstop.

### Addressing

`tg` is accepted only when the packet is addressed to `CONF.callsign` exactly.
`APRSDRegexCommandPluginBase.filter()` enforces that, so a message sent to
`WB4BOR-9` does not reach the plugin. The README says so. The *sender* may use
any SSID of an allowed callsign.

## What is left to the builder

- Exact `Application`/`Updater` call sequence for `python-telegram-bot` 22.8
  (`initialize`/`start`/`start_polling` vs `run_polling`) as long as it is
  interruptible from `stop()`.
- Whether `allowed_updates=["message"]` and `drop_pending_updates=True` are
  worth setting.
- Logging wording and levels.
- `pyproject.toml` versus keeping `setup.cfg` + `pbr`; either is fine if
  `pip install -e .` works and the version still resolves (current package is
  0.1.3 via pbr).
- File layout inside the package, as long as `conf/` keeps the
  `list_opts()`/`register_opts()` contract that the existing sample-config
  generation relies on.

## Tests

`pytest`, no network, no real bot token. Fake `Application`/`Bot` recording
calls; fake `tx.send` capturing packets.

- `parse_aliases`: normal, `@` stripped, missing `=`, empty halves, spaces.
- `is_allowed`: exact, SSID suffix, prefix-similar-but-not-equal
  (`WB4BORX` must fail), empty allowlist falls back to `CONF.callsign`.
- `process()`: unauthorized callsign, too few words, unknown alias,
  alias whose user has not messaged the bot, happy path (bot scheduled with the
  right chat id and text, `last_sender` recorded), send failure path.
- `normalise`: newlines flattened, non-ASCII dropped, payload capped at 67
  including the `Telegram(<username>): ` prefix.
- `setup()`: missing token and a raising `Application.initialize()` both leave
  `enabled == False` without raising.
- `message_handler()`: private chat records id, non-alias username dropped with
  no `tx.send`, no `last_sender` dropped, happy path sends to the last sender
  with `from_call = CONF.callsign`.
- `TelegramThread.stop()` sets the shutdown event (regression test for the
  measured hang).

## Migration / cleanup

- Delete the runtime pickles from the repo root: `telegramusers.p`,
  `watchlist.p`, `seenlist.p`, `seenlist`/`watchlist` leftovers.
- `telegram.conf` in the repo root holds a live bot token
  (`2055416085:AAE...`) and an `app_api_hash`; `aprsd-telegram.yml` holds an
  APRS-IS password. Both are untracked. Rotate the token with @BotFather and
  keep secrets out of the tree.
- `requirements.txt`: `python-telegram-bot>=22,<23`, `oslo.config`, `pbr`.
- README: replace the `shortcuts`/`callsign` config block with `aliases` and
  `allowed_callsigns`, and state that a Telegram user must message the bot
  once before they can receive.

## Assumptions made by me (not agreed, veto freely)

- Work happens in place in `archive/` under the existing package name.
- Delivered Telegram text is prefixed with the APRS sender
  (`WB4BOR-7: ...`), and APRS replies are prefixed `Telegram(<username>):`.
- Only private Telegram chats are supported.
- The APRS-side allowlist defaults to `CONF.callsign` when unset, keeping the
  old "only the owner" behaviour safe by default.
- A failed Telegram startup disables the plugin instead of retrying forever.
- Telegram sends never block the APRSD packet thread; failures are reported to
  the APRS sender as a separate message.
- Only configured aliases are persisted, so a stranger who finds the bot is
  never stored.
- Long or non-ASCII Telegram replies are flattened and truncated to one APRS
  packet rather than split.
- `tg` is answered only when addressed to `CONF.callsign` exactly.
