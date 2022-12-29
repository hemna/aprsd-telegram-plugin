import logging

from aprsd_twitter_plugin.conf import twitter
from oslo_config import cfg


CONF = cfg.CONF

twitter.register_opts(CONF)
