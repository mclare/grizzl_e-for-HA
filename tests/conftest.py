# Load pytest plugins if available to avoid CI import errors when dev
# dependencies are not installed. CI should install test deps (see
# the workflow snippet in the README or below), but this makes the
# test suite more robust when pytest-asyncio isn't present.
pytest_plugins = []

try:
	import pytest_asyncio  # type: ignore

	pytest_plugins.append("pytest_asyncio")
except Exception:
	# pytest_asyncio not installed; skip adding it so pytest won't error
	# when importing plugins listed in `pytest_plugins`.
	pass

pytest_plugins.append("pytest_homeassistant_custom_component")