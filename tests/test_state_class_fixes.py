"""Tests for state_class and device info fixes. - Thanks Gemini"""
import pytest
from custom_components.grizzl_e.const import port_key
from custom_components.grizzl_e.device import GrizzleEDevice
from unittest.mock import Mock


def test_device_info_string_conversion():
    """Test that device info fields are properly converted to strings."""
    # Mock coordinator with numeric data to test string conversion
    coordinator = Mock()
    coordinator.data = {
        "model": 123,  # numeric instead of string
        "verFWMain": 456,  # numeric instead of string
        "serialNum": 789,  # numeric instead of string
    }
    
    # Mock config entry
    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.title = "Test Grizzl-E"
    entry.data = {"host": "192.168.1.1"}
    
    device = GrizzleEDevice(coordinator, entry)
    device_info = device.device_info
    
    # All fields should be strings
    assert isinstance(device_info["model"], str)
    assert device_info["model"] == "123"
    
    assert isinstance(device_info["sw_version"], str)
    assert device_info["sw_version"] == "456"
    
    assert isinstance(device_info["serial_number"], str)
    assert device_info["serial_number"] == "789"


def test_device_info_with_none_values():
    """Test that device info handles None values correctly."""
    coordinator = Mock()
    coordinator.data = {}
    
    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.title = "Test Grizzl-E"
    entry.data = {"host": "192.168.1.1"}
    
    device = GrizzleEDevice(coordinator, entry)
    device_info = device.device_info
    
    # None values should remain None
    assert device_info["sw_version"] is None
    assert device_info["serial_number"] is None
    
    # Model should fall back to default string
    assert isinstance(device_info["model"], str)


def test_device_info_whitespace_trimming():
    """Test that sw_version whitespace is trimmed."""
    coordinator = Mock()
    coordinator.data = {
        "verFWMain": "  1.2.3  ",  # with whitespace
    }
    
    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.title = "Test Grizzl-E"
    entry.data = {"host": "192.168.1.1"}
    
    device = GrizzleEDevice(coordinator, entry)
    device_info = device.device_info
    
    # Whitespace should be trimmed
    assert device_info["sw_version"] == "1.2.3"


def test_port_key_backward_compatibility():
    """Test that port_key maintains backward compatibility for port 1."""
    # Port 1 should use original keys for backward compatibility
    assert port_key("current", 1) == "curMeas1"
    assert port_key("voltage", 1) == "voltMeas1"
    assert port_key("power", 1) == "powerMeas"
    assert port_key("state", 1) == "state"
    assert port_key("pilot", 1) == "pilot"
    assert port_key("session_energy", 1) == "sessionEnergy"
    assert port_key("total_energy", 1) == "totalEnergy"
    assert port_key("session_time", 1) == "sessionTime"
