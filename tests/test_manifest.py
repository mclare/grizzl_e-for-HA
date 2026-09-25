import json
import re
import warnings
from pathlib import Path
import pytest
from awesomeversion import AwesomeVersion

MANIFEST_PATH = Path("custom_components/grizzl_e/manifest.json")
HACS_PATH = Path("hacs.json")
CHANGELOG_PATH = Path("CHANGELOG.md")

VALID_INTEGRATION_TYPES = {
    "device", "entity", "hardware", "helper", "hub", "service", "system", "virtual"
}

VALID_IOT_CLASSES = {
    "assumed_state", "cloud_polling", "cloud_push", "local_polling", "local_push"
}

@pytest.fixture
def manifest():
    assert MANIFEST_PATH.exists(), f"Manifest file not found at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def test_domain_rules(manifest):
    domain = manifest.get("domain")
    assert isinstance(domain, str) and domain, "Domain must be a non-empty string"
    assert re.match(r"^[a-z0-9_]+$", domain), f"Domain '{domain}' contains invalid characters"
    assert MANIFEST_PATH.parent.name == domain, f"Domain '{domain}' must match directory name '{MANIFEST_PATH.parent.name}'"

def test_integration_type(manifest):
    integration_type = manifest.get("integration_type")
    assert integration_type in VALID_INTEGRATION_TYPES, f"Invalid integration_type '{integration_type}'"

def test_iot_class(manifest):
    iot_class = manifest.get("iot_class")
    assert iot_class in VALID_IOT_CLASSES, f"Invalid iot_class '{iot_class}'"

def test_version_format(manifest):
    version = manifest.get("version")
    assert version is not None, "Version key is missing"
    assert AwesomeVersion(version).valid, f"Version '{version}' is not valid AwesomeVersion format"

def test_codeowners(manifest):
    codeowners = manifest.get("codeowners")
    assert isinstance(codeowners, list) and len(codeowners) > 0, "codeowners must be a non-empty list"
    for handle in codeowners:
        assert isinstance(handle, str) and handle.startswith("@"), f"Invalid codeowner handle format: '{handle}'"

def test_hacs_manifest_consistency(manifest):
    """Ensure any keys defined in both manifest.json and hacs.json have identical values."""
    if not HACS_PATH.exists():
        pytest.skip("hacs.json not present in repository root")
        
    with open(HACS_PATH, "r", encoding="utf-8") as f:
        hacs = json.load(f)

    common_keys = set(manifest.keys()) & set(hacs.keys())
    for key in common_keys:
        assert manifest[key] == hacs[key], (
            f"Mismatch for shared key '{key}': "
            f"manifest.json has '{manifest[key]}', hacs.json has '{hacs[key]}'"
        )

def test_changelog_heading_warning(manifest):
    """Warn (without failing) if CHANGELOG.md lacks an H2 header for the manifest version."""
    if not CHANGELOG_PATH.exists():
        warnings.warn(UserWarning("CHANGELOG.md not found in root; skipping heading check."))
        return

    version = manifest.get("version")
    if not version:
        return

    changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")
    
    # Matches '## 1.6', '## v1.6', '## [1.6]', '## [v1.6.0]', etc.
    pattern = rf"^##\s+.*?v?{re.escape(version)}"
    has_heading = bool(re.search(pattern, changelog_text, re.MULTILINE | re.IGNORECASE))

    if not has_heading:
        warnings.warn(
            UserWarning(
                f"CHANGELOG.md is missing an '##' heading for version '{version}' "
                f"(expected format like '## {version}' or '## v{version}')."
            )
        )