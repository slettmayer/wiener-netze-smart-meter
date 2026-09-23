"""The manifest and hacs.json must stay consistent with the code."""

import json
from pathlib import Path

from awesomeversion import AwesomeVersion

from custom_components.wiener_netze_smart_meter.const import DOMAIN

MANIFEST = Path("custom_components/wiener_netze_smart_meter/manifest.json")
HACS = Path("hacs.json")


def test_manifest_domain_matches_const():
    assert json.loads(MANIFEST.read_text())["domain"] == DOMAIN


def test_hacs_filename_matches_domain():
    hacs = json.loads(HACS.read_text())
    assert hacs["filename"] == f"{DOMAIN}.zip"
    assert hacs["zip_release"] is True


def test_hacs_requires_the_core_version_the_statistics_code_needs():
    """`StatisticMetaData(unit_class=...)` only exists from core 2025.11.0 on.

    Without this floor HACS offers the integration to installs where setup dies
    on an ImportError or writes metadata the recorder does not understand.
    """
    hacs = json.loads(HACS.read_text())
    assert AwesomeVersion(hacs["homeassistant"]) >= AwesomeVersion("2025.11.0")
