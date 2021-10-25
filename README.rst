aprsd-telegram-plugin
=====================

|PyPI| |Status| |Python Version| |License|

|Read the Docs| |Tests| |Codecov|

|pre-commit|


Features
--------

* Have a 2 way chat with users of Telegram messenger `http://telegram.org`

Requirements
------------

* You have to create a telegram bot and start the bot
* Telegram users have to add that bot and then /start
* Telegram user can then message the bot
* Only after a telegram user has successfully completed the above
  can you then message a telegram user from an APRS enabled HAM Radio.

Installation
------------

You can install *aprsd-telegram-plugin* via pip_ from PyPI_:

.. code:: console

   $ pip install aprsd-telegram-plugin


Now edit your aprsd.yml config file and add the plugin

.. code:: yaml

    aprsd:
      enabled_plugins:
        - aprsd_telegram_plugin.telegram.TelegramChatPlugin

    services:
      telegram:
        apiKey: <Your Telegram bot APIkey>
        shortcuts:
          'wb': hemna6969



Usage
-----

Please see the `Command-line Reference <Usage_>`_ for details.


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
