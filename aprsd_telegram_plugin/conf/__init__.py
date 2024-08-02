from aprsd_telegram_plugin.conf import telegram
from oslo_config import cfg


CONF = cfg.CONF
telegram.register_opts(CONF)
