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
