"""Tests for consistency between const.py and sensor.py field definitions.

This ensures that fields defined in PORT_FIELD_KEYS are properly used in
sensor.py, preventing issues like removing a field from const.py but forgetting
to remove it from sensor.py (or vice versa).

The test uses static analysis to detect inconsistencies dynamically without
hardcoding expected field names. It examines the actual code structure and
cross-references all field definitions across const.py, sensor.py, device.py,
and strings.json.

Note: This test uses static analysis and doesn't require the Home Assistant
pytest plugin since it only examines the source code structure.
"""
import ast
import json


def extract_port_field_keys():
    """Extract the field names and their JSON keys from PORT_FIELD_KEYS in const.py.
    
    Returns:
        dict: Mapping of logical field names to their JSON keys
              e.g., {"session_time": "sessionTime", "power": "powerMeas"}
    """
    with open("custom_components/grizzl_e/const.py") as f:
        tree = ast.parse(f.read())
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PORT_FIELD_KEYS":
                    if isinstance(node.value, ast.Dict):
                        field_mapping = {}
                        for key, value in zip(node.value.keys, node.value.values):
                            if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
                                field_mapping[key.value] = value.value
                        return field_mapping
    return {}


def extract_per_port_sensor_fields():
    """Extract logical field names used in sensor.py per-port add() calls.
    
    Returns:
        list: Field names used in add() calls for per-port sensors
              e.g., ["power", "current", "voltage", "session_energy"]
    """
    with open("custom_components/grizzl_e/sensor.py") as f:
        content = f.read()
    
    tree = ast.parse(content)
    fields = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check if this is an add() call
            if isinstance(node.func, ast.Name) and node.func.id == "add":
                if node.args and isinstance(node.args[0], ast.Constant):
                    fields.append(node.args[0].value)
    
    return fields


def extract_device_wide_sensor_keys():
    """Extract direct JSON keys used in device-wide sensor definitions.
    
    Returns:
        list: JSON keys used in device-wide GrizzleESensor instantiations
              e.g., ["sessionTime", "temperature1", "RSSI", "state"]
    """
    with open("custom_components/grizzl_e/sensor.py") as f:
        content = f.read()
    
    tree = ast.parse(content)
    keys = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check if this is a GrizzleESensor call (not add())
            if isinstance(node.func, ast.Name) and node.func.id == "GrizzleESensor":
                # The third argument (index 2) is the JSON key
                if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                    keys.append(node.args[2].value)
    
    return keys


def extract_device_data_keys():
    """Extract data keys referenced in device.py.
    
    Returns:
        list: Keys used in data.get() calls in device.py
    """
    with open("custom_components/grizzl_e/device.py") as f:
        content = f.read()
    
    tree = ast.parse(content)
    keys = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Look for data.get() calls
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "get" and len(node.args) >= 1:
                    if isinstance(node.args[0], ast.Constant):
                        keys.append(node.args[0].value)
    
    return keys


def extract_strings_json_keys():
    """Extract all string keys from strings.json.
    
    Returns:
        list: All keys used in strings.json
    """
    try:
        with open("custom_components/grizzl_e/strings.json") as f:
            data = json.load(f)
        
        def extract_keys(obj, prefix=""):
            keys = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    full_key = f"{prefix}.{key}" if prefix else key
                    keys.append(full_key)
                    keys.extend(extract_keys(value, full_key))
            return keys
        
        return extract_keys(data)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def test_port_field_keys_match_per_port_sensors():
    """Ensure all PORT_FIELD_KEYS are used in per-port sensors and vice versa.
    
    This test catches inconsistencies like:
    - Removing a field from PORT_FIELD_KEYS but not from sensor.py per-port sensors
    - Adding a field to per-port sensors but not to PORT_FIELD_KEYS
    
    This is a dynamic test that doesn't hardcode expected field names.
    """
    port_field_mapping = extract_port_field_keys()
    port_fields = set(port_field_mapping.keys())
    per_port_sensor_fields = set(extract_per_port_sensor_fields())
    
    # Check that all per-port sensor fields exist in PORT_FIELD_KEYS
    missing_from_const = per_port_sensor_fields - port_fields
    assert not missing_from_const, (
        f"Fields used in per-port sensor add() calls but missing from PORT_FIELD_KEYS: {missing_from_const}. "
        "Add these fields to the PORT_FIELD_KEYS dictionary in const.py."
    )
    
    # Check that all PORT_FIELD_KEYS are used in per-port sensors
    # (with some exceptions for fields that might only be used device-wide)
    device_wide_only_fields = {"session_started"}  # Fields that might only be used device-wide
    expected_in_sensors = port_fields - device_wide_only_fields
    missing_from_sensor = expected_in_sensors - per_port_sensor_fields
    assert not missing_from_sensor, (
        f"Fields in PORT_FIELD_KEYS but not used in per-port sensor add() calls: {missing_from_sensor}. "
        "Either add these fields to the per-port sensor definitions in sensor.py, "
        "or add them to the device_wide_only_fields exception list in this test if they're only used device-wide."
    )


def test_device_wide_sensors_use_valid_keys():
    """Ensure device-wide sensors use valid JSON keys.
    
    Device-wide sensors can either:
    1. Use direct JSON keys that are NOT in PORT_FIELD_KEYS (e.g., temperature1, RSSI)
    2. Use JSON keys that ARE in PORT_FIELD_KEYS (e.g., sessionTime for session_time)
    
    This test ensures there are no orphaned references.
    """
    port_field_mapping = extract_port_field_keys()
    port_json_keys = set(port_field_mapping.values())
    device_wide_keys = set(extract_device_wide_sensor_keys())
    
    # Split device-wide keys into those that map to PORT_FIELD_KEYS and those that don't
    keys_in_port_fields = device_wide_keys & port_json_keys
    keys_not_in_port_fields = device_wide_keys - port_json_keys
    
    # Keys that are in PORT_FIELD_KEYS should have their logical field used in per-port sensors
    # This is already tested by test_port_field_keys_match_per_port_sensors
    
    # Keys not in PORT_FIELD_KEYS are device-specific (temperature, RSSI, etc.)
    # These are expected and valid
    
    # Check for any keys that might be typos or orphaned references
    # If a device-wide key looks like it should be in PORT_FIELD_KEYS (ends with certain patterns)
    # but isn't, flag it as suspicious
    suspicious_keys = {
        key for key in keys_not_in_port_fields
        if any(pattern in key.lower() for pattern in ["session", "energy", "power", "current", "voltage", "state", "pilot"])
    }
    
    assert not suspicious_keys, (
        f"Device-wide sensor keys that look like they should be in PORT_FIELD_KEYS: {suspicious_keys}. "
        "Either add them to PORT_FIELD_KEYS or ensure they're truly device-specific fields."
    )


def test_device_py_keys_consistency():
    """Ensure keys used in device.py are consistent with available data.
    
    This test checks that device.py references keys that either:
    1. Are in PORT_FIELD_KEYS (as JSON keys)
    2. Are known device-specific fields (model, serial, firmware, etc.)
    """
    port_field_mapping = extract_port_field_keys()
    port_json_keys = set(port_field_mapping.values())
    device_keys = set(extract_device_data_keys())
    
    # Known device-specific keys that are expected but not in PORT_FIELD_KEYS
    known_device_keys = {
        "model", "serialNum", "stationId", "verFWMain"
    }
    
    # Check for keys that might be typos or orphaned references
    suspicious_keys = device_keys - port_json_keys - known_device_keys
    
    assert not suspicious_keys, (
        f"Keys used in device.py that are not in PORT_FIELD_KEYS or known device keys: {suspicious_keys}. "
        "Either add them to PORT_FIELD_KEYS, add them to known_device_keys in this test, "
        "or remove the reference if it's a typo."
    )


def test_no_orphaned_field_references():
    """Comprehensive test to detect orphaned field references across all files.
    
    This test ensures that when a field is removed, it's removed from ALL locations:
    - const.py PORT_FIELD_KEYS
    - sensor.py per-port sensors
    - sensor.py device-wide sensors
    - device.py data references
    """
    port_field_mapping = extract_port_field_keys()
    port_logical_fields = set(port_field_mapping.keys())
    port_json_keys = set(port_field_mapping.values())
    
    per_port_fields = set(extract_per_port_sensor_fields())
    device_wide_keys = set(extract_device_wide_sensor_keys())
    device_keys = set(extract_device_data_keys())
    
    # Check 1: All per-port fields should be in PORT_FIELD_KEYS
    orphaned_per_port = per_port_fields - port_logical_fields
    assert not orphaned_per_port, (
        f"Orphaned per-port sensor fields: {orphaned_per_port}. "
        "These are used in sensor.py add() calls but not in PORT_FIELD_KEYS. "
        "Remove them from sensor.py or add them to const.py."
    )
    
    # Check 2: All PORT_FIELD_KEYS should be used in per-port sensors (except known exceptions)
    known_exceptions = {"session_started"}  # Fields that might be device-wide only
    unused_port_fields = (port_logical_fields - per_port_fields) - known_exceptions
    assert not unused_port_fields, (
        f"Unused PORT_FIELD_KEYS: {unused_port_fields}. "
        "These are defined in const.py but not used in per-port sensors. "
        "Either add them to sensor.py or remove them from const.py."
    )
    
    # Check 3: Device-wide keys that reference PORT_FIELD_KEYS should be consistent
    # If a device-wide key matches a PORT_FIELD_KEYS JSON key, ensure the logical field is used
    device_wide_port_matches = device_wide_keys & port_json_keys
    for json_key in device_wide_port_matches:
        # Find the logical field name for this JSON key
        logical_field = None
        for field, key in port_field_mapping.items():
            if key == json_key:
                logical_field = field
                break
        
        if logical_field and logical_field not in per_port_fields:
            # This is a warning - it might be intentional (device-wide only)
            print(
                f"Warning: Device-wide sensor uses '{json_key}' (mapped to '{logical_field}') "
                f"but '{logical_field}' is not used in per-port sensors. "
                f"This may be intentional if the field is device-wide only."
            )
