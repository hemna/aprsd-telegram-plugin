aprsd-telegram-plugin
=====================

|PyPI| |Status| |Python Version| |License|

|Read the Docs| |Tests| |Codecov|

|pre-commit|


Features
--------

* Have a 2 way chat with users of Telegram messenger `http://telegram.org`

How it works
------------

* You message a Telegram user from APRS with ``tg <alias> <text>``.
* Their reply comes back to the APRS callsign that last messaged them.

Requirements
------------

* Python 3.10+ and aprsd 5.0 or newer.
* You have to create a telegram bot with @BotFather and get its token.
* Every Telegram user you want to talk to must find that bot, press
  ``/start`` and send it one normal text message. That first message is how
  the plugin learns their chat id, because Telegram has no username to id
  lookup. Commands (anything starting with ``/``) are ignored.
* If a user changes their Telegram username, update the alias and have them
  message the bot again.
* Only a private chat with the bot is used; group chats are ignored.

Installation
------------

You can install *aprsd-telegram-plugin* via pip_ from PyPI_:

.. code:: console

   $ pip install aprsd-telegram-plugin

Then enable the plugin in your ``aprsd.conf``:

.. code:: ini

    [DEFAULT]
    enabled_plugins = aprsd_telegram_plugin.telegram.TelegramChatPlugin
    callsign = WB4BOR

    [aprsd_telegram_plugin]

    # Turn the plugin on. Without this nothing runs and `tg` is not answered.
    enabled = true

    # Bot token from @BotFather, not the api_id/api_hash.
    apiKey = 123456:ABC-DEF...

    # alias=@telegram_username pairs. The alias is what you type after `tg`.
    aliases = wb=@walt, cl=@craigerl

    # APRS callsigns allowed to send `tg`. Any SSID of a listed callsign
    # works (WB4BOR-7 matches WB4BOR). Empty means only the [DEFAULT]
    # callsign may use the plugin.
    allowed_callsigns = WB4BOR, N0CALL

Usage
-----

Address the message to your APRSD callsign exactly (``WB4BOR``, not
``WB4BOR-7`` and not a tactical alias), then:

.. code:: text

    tg wb see you at the repeater at 8

The Telegram user ``@walt`` receives ``WB4BOR-7: see you at the repeater at 8``.
When they reply in Telegram, the plugin sends it back to ``WB4BOR-7``, the
callsign that last sent them a message:

.. code:: text

    Telegram(walt): sounds good

Every reply is flattened to one line, stripped to ASCII and clipped to the
67 character APRS message limit. Anything longer is cut, not split.

Development
-----------

.. code:: console

   $ uv venv .venv --python 3.12
   $ uv pip install --python .venv/bin/python -e . -r requirements-dev.txt
   $ .venv/bin/pytest -q


Contributing
------------

Contributions are very welcome.
To learn more, see the `Contributor Guide`_.


License
-------

Distributed under the terms of the `MIT license`_,
*aprsd-telegram-plugin* is free and open source software.


Issues
------

If you encounter any problems,
please `file an issue`_ along with a detailed description.


Credits
-------

This project was generated from `@hemna`_'s `APRSD Plugin Python Cookiecutter`_ template.

.. _@hemna: https://github.com/hemna
.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _MIT license: https://opensource.org/licenses/MIT
.. _PyPI: https://pypi.org/
.. _APRSD Plugin Python Cookiecutter: https://github.com/hemna/cookiecutter-aprsd-plugin
.. _file an issue: https://github.com/hemna/aprsd-telegram-plugin/issues
.. _pip: https://pip.pypa.io/
.. github-only
.. _Contributor Guide: CONTRIBUTING.rst
.. _Usage: https://aprsd-telegram-plugin.readthedocs.io/en/latest/usage.html


.. badges

.. |PyPI| image:: https://img.shields.io/pypi/v/aprsd-telegram-plugin.svg
   :target: https://pypi.org/project/aprsd-telegram-plugin/
   :alt: PyPI
.. |Status| image:: https://img.shields.io/pypi/status/aprsd-telegram-plugin.svg
   :target: https://pypi.org/project/aprsd-telegram-plugin/
   :alt: Status
.. |Python Version| image:: https://img.shields.io/pypi/pyversions/aprsd-telegram-plugin
   :target: https://pypi.org/project/aprsd-telegram-plugin
   :alt: Python Version
.. |License| image:: https://img.shields.io/pypi/l/aprsd-telegram-plugin
   :target: https://opensource.org/licenses/MIT
   :alt: License
.. |Read the Docs| image:: https://img.shields.io/readthedocs/aprsd-telegram-plugin/latest.svg?label=Read%20the%20Docs
   :target: https://aprsd-telegram-plugin.readthedocs.io/
   :alt: Read the documentation at https://aprsd-telegram-plugin.readthedocs.io/
.. |Tests| image:: https://github.com/hemna/aprsd-telegram-plugin/workflows/Tests/badge.svg
   :target: https://github.com/hemna/aprsd-telegram-plugin/actions?workflow=Tests
   :alt: Tests
.. |Codecov| image:: https://codecov.io/gh/hemna/aprsd-telegram-plugin/branch/main/graph/badge.svg
   :target: https://codecov.io/gh/hemna/aprsd-telegram-plugin
   :alt: Codecov
.. |pre-commit| image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white
   :target: https://github.com/pre-commit/pre-commit
   :alt: pre-commit
