"""Tests for multi-port (Grizzl-E Duo) field mapping.

Regression tests for issue #23: the Duo reports its second cable through a
different set of /main JSON keys than the naive ``curMeas2``/``voltMeas2``.
"""
import pytest

from custom_components.grizzl_e.const import port_key


# Real /main payloads captured from a Grizzl-E Duo (issue #23), trimmed to the
# fields relevant to per-cable reporting.
PORT1_CHARGING = {
    "curMeas1": 22.17, "curMeas2": 0, "voltMeas1": 236, "voltMeas2": 0,
    "powerMeas": 5234, "state": 4, "pilot": 2, "sessionStarted": 1,
    "curMeas1C2": 0, "powerMeas2": 0, "state2": 2, "pilot2": 0, "sessionStarted2": 0,
}
PORT2_CHARGING = {
    "curMeas1": 0, "curMeas2": 0, "voltMeas1": 236, "voltMeas2": 0,
    "powerMeas": 0, "state": 2, "pilot": 0, "sessionStarted": 0,
    "curMeas1C2": 22.39, "powerMeas2": 5286, "state2": 4, "pilot2": 2, "sessionStarted2": 1,
}
BOTH_CHARGING = {
    "curMeas1": 20.52, "voltMeas1": 239, "powerMeas": 4905,
    "curMeas1C2": 20.47, "powerMeas2": 4893,
}


def test_port1_keys_are_unchanged():
    """Port 1 must keep the original keys (backward compatibility)."""
    assert port_key("current", 1) == "curMeas1"
    assert port_key("voltage", 1) == "voltMeas1"
    assert port_key("power", 1) == "powerMeas"
    assert port_key("state", 1) == "state"
    assert port_key("pilot", 1) == "pilot"
    assert port_key("session_started", 1) == "sessionStarted"


def test_port2_uses_duo_specific_keys():
    """Port 2 uses the Duo's non-standard keys (the bug in issue #23)."""
    assert port_key("current", 2) == "curMeas1C2"   # NOT curMeas2 (always 0)
    assert port_key("voltage", 2) == "voltMeas1"     # shared circuit, NOT voltMeas2
    assert port_key("power", 2) == "powerMeas2"
    assert port_key("state", 2) == "state2"
    assert port_key("pilot", 2) == "pilot2"
    assert port_key("session_started", 2) == "sessionStarted2"


def test_port3_generalizes_pattern():
    assert port_key("current", 3) == "curMeas1C3"
    assert port_key("voltage", 3) == "voltMeas1"
    assert port_key("power", 3) == "powerMeas3"


@pytest.mark.parametrize(
    "data, field, port, expected",
    [
        (PORT1_CHARGING, "current", 1, 22.17),
        (PORT1_CHARGING, "power", 1, 5234),
        (PORT1_CHARGING, "voltage", 2, 236),   # cable 2 shares cable 1 voltage
        (PORT2_CHARGING, "current", 1, 0),
        (PORT2_CHARGING, "current", 2, 22.39),  # would have been curMeas2 == 0
        (PORT2_CHARGING, "voltage", 2, 236),    # would have been voltMeas2 == 0
        (PORT2_CHARGING, "power", 2, 5286),
        (PORT2_CHARGING, "state", 2, 4),
        (PORT2_CHARGING, "session_started", 2, 1),
        (BOTH_CHARGING, "current", 1, 20.52),
        (BOTH_CHARGING, "current", 2, 20.47),
        (BOTH_CHARGING, "power", 1, 4905),
        (BOTH_CHARGING, "power", 2, 4893),
    ],
)
def test_reading_through_port_key(data, field, port, expected):
    assert data.get(port_key(field, port)) == expected


def test_old_keys_were_always_zero_for_cable2():
    """Documents why the old mapping failed: curMeas2/voltMeas2 stay 0."""
    assert PORT2_CHARGING["curMeas2"] == 0
    assert PORT2_CHARGING["voltMeas2"] == 0
