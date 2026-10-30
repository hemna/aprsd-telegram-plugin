# APRSD 5.x Telegram Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `aprsd-telegram-plugin` so APRS↔Telegram text bridging works on APRSD 5.x with an alias table and an allowlist.

**Architecture:** One plugin module. `TelegramChatPlugin` (regex command `^tg`) handles the APRS side synchronously on APRSD's packet thread; a single `TelegramThread` owns one asyncio event loop running `python-telegram-bot`'s `Application` in polling mode; the two talk through a non-blocking `send()` and through `tx.send()` from the async handler. Learned `username -> chat_id` and `last_sender` live in an `ObjectStoreMixin` JSON file so a restart does not forget who may receive.

**Tech Stack:** Python 3.12 (floor 3.11), `aprsd>=5.0`, `python-telegram-bot>=22,<23` (22.8 measured), `oslo.config`, `pbr`, `pytest` + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-10-29-telegram-aprsd5-design.md`

## Global Constraints

- `python-telegram-bot>=22,<23`. The `<20` pin in the current `requirements.txt` must go; 13.15 does not import on modern Python.
- Target `aprsd>=5.0`; on this machine that is the local checkout `~/devel/mine/hamradio/aprsd` (5.0.2.dev measured). PyPI still serves 4.2.4, so the dev venv installs aprsd from that checkout.
- Config group `aprsd_telegram_plugin`, options exactly: `enabled` (BoolOpt, default False), `apiKey` (StrOpt, `secret=True`), `aliases` (ListOpt, default `[]`), `allowed_callsigns` (ListOpt, default `[]`).
- APRS payload budget: 67 characters, ASCII only. APRSD truncates as a backstop; the plugin still normalises.
- APRS traffic produced by the plugin is always `from_call=CONF.callsign`. Never a Telegram-supplied callsign.
- No test may touch the network, use a real bot token, or write outside a tmp directory.
- Only `TelegramThread` may run an asyncio event loop.
- `CONF.aprs_network.login` does not exist in 5.x — use `CONF.callsign`.

## Review Focus

- A Telegram reply containing newlines, emoji, or more than ~50 characters of text — expected: arrives as one clean ASCII APRS line, clipped, not mangled or rejected.
- A Telegram account that is not a configured alias — expected: no APRS traffic, no reply, one log line.
- `tg` from an APRS callsign not on the allowlist — expected: `Unauthorized`, nothing delivered.
- An alias whose person has never messaged the bot — expected: `Need a message from @<user> on Telegram first`, nothing delivered.
- A bad/revoked bot token at startup — expected: plugin disables itself and logs once, no 1-second retry storm, `tg` returns `Telegram plugin is not running`.
- A Telegram reply when no APRS sender is recorded yet — expected: dropped and logged, no crash.

---

### Task 1: Dev environment, config options, pure helpers

**Files:**
- Modify: `requirements.txt`, `requirements-dev.txt`
- Modify: `aprsd_telegram_plugin/conf/telegram.py`
- Modify: `aprsd_telegram_plugin/telegram.py` (replace everything below the imports later; this task adds `parse_aliases` and `is_allowed`)
- Create: `tests/test_helpers.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `parse_aliases(raw: list[str]) -> dict[str, str]` — key = alias (casefolded), value = Telegram username (casefolded, no leading `@`).
  - `is_allowed(from_call: str, allowed: list[str], fallback: str) -> bool`.
  - `CONF.aprsd_telegram_plugin.{enabled, apiKey, aliases, allowed_callsigns}`.

- [ ] **Step 1: Pin dependencies**

`requirements.txt`:
```
pbr
oslo.config
python-telegram-bot>=22,<23
```

`requirements-dev.txt`:
```
pytest
```

- [ ] **Step 2: Build the dev venv and prove the plugin installs**

Run:
```bash
cd ~/devel/mine/hamradio/aprsd-plugins/archive/aprsd-telegram-plugin
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e . -r requirements-dev.txt -e ~/devel/mine/hamradio/aprsd
.venv/bin/python -c "import aprsd, aprsd_telegram_plugin, telegram; print(aprsd.__version__, telegram.__version__)"
```
Expected: prints an `aprsd` 5.x version and `22.8`.

- [ ] **Step 3: Write the failing tests**

`tests/test_helpers.py`:
```python
from aprsd_telegram_plugin.telegram import is_allowed, parse_aliases


def test_parse_aliases_strips_at_and_folds_case():
    assert parse_aliases(["WB=@Walt", " cl = craigerl "]) == {
        "wb": "walt",
        "cl": "craigerl",
    }


def test_parse_aliases_skips_malformed_entries():
    assert parse_aliases(["nope", "=@x", "kid="]) == {}


def test_is_allowed_accepts_exact_and_any_ssid():
    assert is_allowed("WB4BOR", ["WB4BOR"], "N0CALL")
    assert is_allowed("WB4BOR-7", ["WB4BOR"], "N0CALL")


def test_is_allowed_rejects_lookalike_prefix():
    assert not is_allowed("WB4BORX", ["WB4BOR"], "N0CALL")


def test_is_allowed_empty_list_falls_back_to_owner_callsign():
    assert is_allowed("WB4BOR-9", [], "WB4BOR")
    assert not is_allowed("N0CALL", [], "WB4BOR")
```

- [ ] **Step 4: Run the tests, expect failure**

Run: `.venv/bin/pytest tests/test_helpers.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_aliases'`.

- [ ] **Step 5: Write the options and the two helpers**

`conf/telegram.py` keeps `telegram_group`, `register_opts()`, `list_opts()` and replaces the option list with `enabled`, `apiKey`, `aliases`, `allowed_callsigns` (defaults as in Global Constraints; `apiKey` help mentions @BotFather; `aliases` help shows `wb=@walt, cl=@craigerl`; `allowed_callsigns` help says an SSID of a listed callsign is accepted and empty means `[DEFAULT] callsign` only).

`telegram.py`: `parse_aliases` splits each entry on the first `=`, strips whitespace, drops a leading `@`, casefolds both sides, and skips entries with a missing or empty side (log a warning listing the skipped entry). `is_allowed` lowercases for comparison, accepts `from_call == entry` or `from_call.startswith(entry + "-")`, and uses `[fallback]` when `allowed` is empty.

- [ ] **Step 6: Run the tests, expect pass**

Run: `.venv/bin/pytest tests/test_helpers.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt aprsd_telegram_plugin/conf/telegram.py aprsd_telegram_plugin/telegram.py tests/test_helpers.py
git commit -m "feat: config aliases/allowlist and helper parsing for aprsd 5"
```

---

### Task 2: Learned Telegram users store

**Files:**
- Modify: `aprsd_telegram_plugin/telegram.py`
- Create: `tests/test_users.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `TelegramUsers` singleton with
  - `set_seen(username: str, chat_id: int) -> None` (saves immediately)
  - `set_last_sender(username: str, callsign: str) -> None`
  - `chat_id(username: str) -> int | None`
  - `last_sender(username: str) -> str | None`
  - `data: dict[str, dict]` shape `{username: {"chat_id": int|None, "last_sender": str|None}}`, keys casefolded.
  - JSON file `<CONF.save_location>/telegramusers.json` via `objectstore.ObjectStoreMixin`.

- [ ] **Step 1: Write the failing tests**

`tests/test_users.py`:
```python
import json
import pathlib
import tempfile
import unittest

from aprsd import conf  # noqa: F401
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF


class TestTelegramUsers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        CONF.set_override("enable_save", True)
        CONF.set_override("save_location", self.tmp)
        impl.TelegramUsers._instance = None
        self.users = impl.TelegramUsers()

    def tearDown(self):
        CONF.clear_override("enable_save")
        CONF.clear_override("save_location")
        impl.TelegramUsers._instance = None

    def test_set_seen_is_readable_case_insensitively(self):
        self.users.set_seen("Walt", 42)
        self.assertEqual(42, self.users.chat_id("walt"))

    def test_set_seen_writes_json_immediately(self):
        self.users.set_seen("walt", 42)
        raw = json.loads(
            pathlib.Path(f"{self.tmp}/telegramusers.json").read_text(),
        )
        self.assertEqual({"walt": {"chat_id": 42}}, raw)

    def test_last_sender_roundtrip(self):
        self.users.set_last_sender("walt", "WB4BOR-7")
        self.assertEqual("WB4BOR-7", self.users.last_sender("walt"))

    def test_unknown_user_is_none(self):
        self.assertIsNone(self.users.chat_id("nobody"))
        self.assertIsNone(self.users.last_sender("nobody"))
```

- [ ] **Step 2: Run the tests, expect failure**

Run: `.venv/bin/pytest tests/test_users.py -v`
Expected: FAIL — old `TelegramUsers` raises on `_shortcuts is None` or lacks `chat_id`.

- [ ] **Step 3: Rewrite `TelegramUsers`**

Keep the singleton `__new__` (lock + `_init_store()`), drop `_shortcuts` and `__getitem__`/`__contains__`. `set_seen` creates or updates the record then calls `self.save()`; `set_last_sender` updates then returns without saving (the periodic stop-save covers it); readers use a dict `.get` under the lock and return `None` for unknown keys.

- [ ] **Step 4: Run the tests, expect pass**

Run: `.venv/bin/pytest tests/test_users.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add aprsd_telegram_plugin/telegram.py tests/test_users.py
git commit -m "feat: persist learned telegram chat ids as json"
```

---

### Task 3: Plugin setup and APRS→Telegram command

**Files:**
- Modify: `aprsd_telegram_plugin/telegram.py`
- Create: `tests/test_plugin.py`

**Interfaces:**
- Consumes: `parse_aliases`, `is_allowed` (Task 1); `TelegramUsers.chat_id` / `.set_last_sender` (Task 2).
- Produces: `TelegramChatPlugin` with attributes `enabled: bool`, `aliases: dict[str, str]`, `users: TelegramUsers`, `thread: TelegramThread | None`; methods `setup()`, `create_threads() -> list`, `process(packet)`, `help() -> str`. `thread.send(username: str, chat_id: int, text: str) -> None` is what Task 5 provides.

- [ ] **Step 1: Write the failing tests**

`tests/test_plugin.py`:
```python
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
        with mock.patch.object(impl.TelegramChatPlugin, "create_threads", return_value=[]):
            self.plugin = impl.TelegramChatPlugin()
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
        with mock.patch.object(impl.TelegramChatPlugin, "create_threads", return_value=[]):
            plugin = impl.TelegramChatPlugin()
        self.assertFalse(plugin.enabled)

    def test_disabled_when_option_is_false(self):
        CONF.set_override("enabled", False, group=GROUP)
        with mock.patch.object(impl.TelegramChatPlugin, "create_threads", return_value=[]):
            plugin = impl.TelegramChatPlugin()
        self.assertFalse(plugin.enabled)

    def test_unauthorized_callsign(self):
        self.assertEqual("Unauthorized", self.plugin.process(self._packet(from_call="N0CALL")))

    def test_too_few_words(self):
        self.assertEqual("invalid request", self.plugin.process(self._packet(text="tg wb")))

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
        self.plugin.thread.send.assert_called_once_with("walt", 42, "WB4BOR-7: hi there")
        self.assertEqual("WB4BOR-7", self.plugin.users.last_sender("walt"))

    def test_not_running_when_thread_absent(self):
        self.plugin.users.set_seen("walt", 42)
        self.plugin.thread = None
        self.assertEqual(
            "Telegram plugin is not running",
            self.plugin.process(self._packet()),
        )

    def test_not_running_after_startup_failure(self):
        self.plugin.users.set_seen("walt", 42)
        self.plugin.enabled = False
        self.assertEqual(
            "Telegram plugin is not running",
            self.plugin.process(self._packet()),
        )
```

- [ ] **Step 2: Run the tests, expect failure**

Run: `.venv/bin/pytest tests/test_plugin.py -v`
Expected: FAIL — message strings and `thread` attribute do not exist yet.

- [ ] **Step 3: Implement `setup()`, `create_threads()`, `process()`, `help()`**

`setup()`: `enabled = CONF.aprsd_telegram_plugin.enabled`, then require `apiKey`; store `self.aliases`, `self.users = TelegramUsers()` + `load()`, `self.thread = None`. `create_threads()` returns `[]` when disabled, else `[self.thread]` after constructing `TelegramThread(self, CONF.aprsd_telegram_plugin.apiKey)`. `process()` starts with `if not self.enabled or self.thread is None: return "Telegram plugin is not running"`, then follows the spec's remaining steps and returns the exact strings asserted above; delivery calls `self.thread.send(username, chat_id, f"{packet.from_call}: {text}")`. `help()` returns `"telegram: send 'tg <alias> <text>' to message a telegram user"`.

- [ ] **Step 4: Run the tests, expect pass**

Run: `.venv/bin/pytest tests/test_plugin.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add aprsd_telegram_plugin/telegram.py tests/test_plugin.py
git commit -m "feat: tg command delivers to telegram with allowlist and aliases"
```

---

### Task 4: Telegram→APRS handler and text normalisation

**Files:**
- Modify: `aprsd_telegram_plugin/telegram.py`
- Create: `tests/test_handler.py`

**Interfaces:**
- Consumes: `TelegramUsers` (Task 2), `TelegramChatPlugin.aliases` and `.users` (Task 3), `aprsd.threads.tx.send`.
- Produces: `normalise(text: str, prefix: str) -> str` (ASCII, newlines flattened, total length ≤ 67 including `prefix`) and `async message_handler(self, update, context) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_handler.py`:
```python
import asyncio
import types
import unittest
from unittest import mock

from aprsd import conf  # noqa: F401
from aprsd import packets
from oslo_config import cfg

from aprsd_telegram_plugin import telegram as impl

CONF = cfg.CONF
GROUP = "aprsd_telegram_plugin"


def _update(text, username="walt", chat_id=42, chat_type="private"):
    return types.SimpleNamespace(
        message=types.SimpleNamespace(
            text=text,
            chat=types.SimpleNamespace(type=chat_type, username=username, id=chat_id),
        ),
    )


class TestNormalise(unittest.TestCase):
    def test_flattens_newlines(self):
        self.assertEqual("Telegram(walt): a b", impl.normalise("a\nb", "Telegram(walt): "))

    def test_drops_non_ascii(self):
        self.assertEqual("Telegram(walt): hi ", impl.normalise("hi \u263a", "Telegram(walt): "))

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
        with mock.patch.object(impl.TelegramChatPlugin, "create_threads", return_value=[]):
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
```

- [ ] **Step 2: Run the tests, expect failure**

Run: `.venv/bin/pytest tests/test_handler.py -v`
Expected: FAIL — `normalise` and `message_handler` missing.

- [ ] **Step 3: Implement `normalise()` and `message_handler()`**

`normalise` replaces `\r\n\t` with spaces, collapses runs of spaces, encodes to ASCII with `errors="ignore"`, and returns `prefix + text[: 67 - len(prefix)]` right-stripped. `message_handler` follows the spec's five steps; the APRS send is `await asyncio.get_running_loop().run_in_executor(None, impl.tx.send, packet)`.

- [ ] **Step 4: Run the tests, expect pass**

Run: `.venv/bin/pytest tests/test_handler.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add aprsd_telegram_plugin/telegram.py tests/test_handler.py
git commit -m "feat: telegram replies return to the last APRS sender"
```

---

### Task 5: Telegram thread with asyncio lifecycle

**Files:**
- Modify: `aprsd_telegram_plugin/telegram.py`
- Create: `tests/test_thread.py`

**Interfaces:**
- Consumes: `TelegramChatPlugin` (Task 3) for `enabled` and `message_handler`.
- Produces: `TelegramThread(plugin: TelegramChatPlugin, token: str)` subclassing `aprsd.threads.APRSDThread` with `loop() -> bool`, `stop() -> None`, `send(chat_id: int, text: str) -> None`, `_send_done(username: str, future) -> None`, attributes `app`, `_loop`, `_async_stop`.

- [ ] **Step 1: Write the failing tests**

`tests/test_thread.py`:
```python
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
        with mock.patch.object(impl.TelegramThread, "_serve", new=mock.AsyncMock()):
            self.assertFalse(self.thread.loop())

    def test_startup_failure_disables_plugin(self):
        self.thread.app = mock.Mock()
        self.thread.app.initialize = mock.AsyncMock(side_effect=RuntimeError("bad token"))
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
```

- [ ] **Step 2: Run the tests, expect failure**

Run: `.venv/bin/pytest tests/test_thread.py -v`
Expected: FAIL — `TelegramThread.__init__` still takes only `updater`, `stop()` never sets the shutdown event.

- [ ] **Step 3: Implement the thread lifecycle**

`__init__`: `super().__init__("TelegramThread")`, store `plugin` and `token`, build `self.app = Application.builder().token(token).build()`, `self._loop = None`, `self._async_stop = None`.

`loop()`: `self._loop = asyncio.new_event_loop()`, `asyncio.set_event_loop(self._loop)`, `self._loop.run_until_complete(self._serve())`, `return False`, and close the loop in a `finally`.

`_serve()`: on `initialize`/`start`/`updater.start_polling` failure — log, `self.plugin.enabled = False`, return. Otherwise wait on `self._async_stop` (created inside the coroutine), then `updater.stop()`, `app.stop()`, `app.shutdown()`.

`stop()`: `super().stop()` first, then if `self._loop` and `self._async_stop`, `call_soon_threadsafe(self._async_stop.set)`.

- [ ] **Step 4: Run the lifecycle tests, expect the startup and stop tests to pass**

Run: `.venv/bin/pytest tests/test_thread.py -v -k "stop or startup"`
Expected: 2 passed. `test_send_without_loop_does_not_raise` and `test_send_failure_reports_back_to_aprs` still fail.

- [ ] **Step 5: Implement `send()` and `_send_done()`**

`send(username, chat_id, text)`: return early when `self._loop` is `None` or closed; else `asyncio.run_coroutine_threadsafe(self.app.bot.send_message(chat_id=chat_id, text=text), self._loop)` and attach `functools.partial(self._send_done, username)`.

`_send_done(username, future)`: return if `future.exception()` is `None`; else log it and `tx.send(packets.MessagePacket(from_call=CONF.callsign, to_call=self.plugin.users.last_sender(username), message_text=f"Telegram send failed: {reason}"))`, skipping the send when there is no recorded sender.

Register `MessageHandler(filters.TEXT & ~filters.COMMAND, self.plugin.message_handler)` on `self.app` in `__init__`.

- [ ] **Step 6: Run the thread tests, expect pass**

Run: `.venv/bin/pytest tests/test_thread.py tests/test_plugin.py -v`
Expected: all pass (plugin test updated in Step 5).

- [ ] **Step 7: Commit**

```bash
git add aprsd_telegram_plugin/telegram.py tests/test_thread.py
git commit -m "feat: asyncio telegram polling thread that stops cleanly"
```

---

### Task 6: Docs, cleanup, and a live check

**Files:**
- Modify: `README.rst`
- Create: `.gitignore`
- Delete: `tests/test_aprsd_telegram_plugin.py`, `telegramusers.p`, `watchlist.p`, `seenlist.p`
- Modify: `ChangeLog`, `setup.cfg` (classifiers: drop 3.7/3.8/3.9)

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Rewrite the README config section**

Replace the `shortcuts`/`callsign` block with the `enabled`, `apiKey`, `aliases`, `allowed_callsigns` block from the spec, the sentence that a Telegram user must message the bot once before they can receive, that `tg` must be addressed to the APRSD callsign exactly, and the install/dev commands from Task 1 Step 2.

- [ ] **Step 2: Add a `.gitignore` before anything else**

The repo has none, and the working tree holds a live bot token in `telegram.conf`, an APRS-IS password in `aprsd-telegram.yml`, and stale pickles. Write:
```
.venv/
__pycache__/
*.pyc
*.egg-info/
.idea/
.envrc
Makefile.venv
telegram.conf
aprsd-telegram.yml
aprsd-telegram-video.yml
sample.conf
*.p
```

- [ ] **Step 3: Delete the stub test and stale runtime state**

```bash
git rm tests/test_aprsd_telegram_plugin.py
rm -f telegramusers.p watchlist.p seenlist.p
rmdir devel 2>/dev/null; rm -rf -- '~/devel' 2>/dev/null
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/pytest -v`
Expected: all tests pass, no network access, no new files in the repo root (`git status --short` shows only intended changes).

- [ ] **Step 5: Commit — explicit paths only, never `git add -A`**

```bash
git add .gitignore README.rst ChangeLog setup.cfg tests/ docs/
git status --short
git commit -m "docs: document aliases, allowlist and dev setup for aprsd 5"
```
Confirm the staged list contains no `telegram.conf`, no `aprsd-telegram.yml`, no `.p` files.

- [ ] **Step 6: Live check (needs the real bot and a radio, run by the operator)**

1. Put a freshly rotated token and `aliases = wb=@<your telegram username>` in the aprsd config, `enabled = true`.
2. Start aprsd, confirm one log line showing the poller started.
3. From the radio send `tg wb test one`; expect `WB4BOR-7: test one` in Telegram.
4. Reply in Telegram; expect `Telegram(<username>): <reply>` on APRS.
5. Send your Telegram account a message containing a newline and an emoji; confirm one clean clipped APRS line.
