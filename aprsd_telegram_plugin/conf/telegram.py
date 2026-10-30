from oslo_config import cfg


telegram_group = cfg.OptGroup(
    name="aprsd_telegram_plugin",
    title="APRSD Telegram Plugin settings",
)

telegram_opts = [
    cfg.BoolOpt(
        "enabled",
        default=False,
        help="Enable the Telegram plugin?",
    ),
    cfg.StrOpt(
        "apiKey",
        secret=True,
        help="Telegram bot token from @BotFather.",
    ),
    cfg.ListOpt(
        "aliases",
        default=[],
        help="alias=@telegram_username pairs, comma separated. "
        "For example: wb=@walt, cl=@craigerl. The alias is what you type "
        "after 'tg' on APRS.",
    ),
    cfg.ListOpt(
        "allowed_callsigns",
        default=[],
        help="APRS callsigns allowed to use the plugin. Any SSID of a "
        "listed callsign is accepted. Empty means only the [DEFAULT] "
        "callsign may use it.",
    ),
]

ALL_OPTS = (telegram_opts)


def register_opts(cfg):
    cfg.register_group(telegram_group)
    cfg.register_opts(ALL_OPTS, group=telegram_group)


def list_opts():
    return {
        telegram_group.name: ALL_OPTS,
    }
