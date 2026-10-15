"""The OGC registration we hand AWI must be internally consistent, and must
never be pasted alongside the parked OAI registration by accident.
Pure file checks; runs in CI without the AWI clone."""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree.ElementTree import fromstring

import pytest
import yaml

from oai.mapping import ORGANISATIONS

PORTAL = Path(__file__).resolve().parents[2] / "portal"
OGC = PORTAL / "ogc"
pytestmark = pytest.mark.skipif(
    not PORTAL.is_dir(), reason="portal/ is kept outside the repo (local-only)"
)
C_NS = "http://www.awi.de/harvester/config"
LIVE = "https://www.plabipd.de/ogc"


def _script() -> str:
    return (OGC / "harvest-repository-dataplant-arcs-ogc.py").read_text(encoding="utf-8")


def _harvester_element(path: Path):
    raw = path.read_text(encoding="utf-8")
    return fromstring(f'<c:wrap xmlns:c="{C_NS}">{raw}</c:wrap>').find(f"{{{C_NS}}}harvester")


def test_endpoint_is_identical_in_script_and_services():
    """services.yaml entries are matched to a harvester by exact URL."""
    endpoint = re.search(r"^ENDPOINT = '([^']+)'", _script(), re.M).group(1)
    entry = yaml.safe_load((OGC / "services.yaml.fragment").read_text(encoding="utf-8"))[
        "interplant-dataplant-ogc"]
    assert endpoint == entry["url"] == entry["provider"]["metadata"]["apiUrl"] == LIVE
    assert entry["provider"]["metadata"]["apiType"] == "OGC API - Records"


def test_only_arc_records_is_harvested():
    match = re.search(r"^COLLECTIONS = (\[[^\]]*\])", _script(), re.M)
    assert match is not None and match.group(1) == "['arc-records']"


def test_xml_fragment_targets_the_ogc_script_and_the_extern_index():
    harvester = _harvester_element(OGC / "harvest-repository-config.xml.fragment")
    assert harvester.get("id") == "dataplant-arc-ogc-harvester"
    assert harvester.findtext(f"{{{C_NS}}}index") == "harvest-extern"
    assert harvester.findtext(f"{{{C_NS}}}mapping") == "EMPTY"
    script = harvester.find(f'{{{C_NS}}}parameter[@name="script"]')
    assert script.text.endswith("harvest-repository-dataplant-arcs-ogc.py")


def test_ogc_and_oai_registrations_are_distinct():
    ogc = _harvester_element(OGC / "harvest-repository-config.xml.fragment")
    oai = _harvester_element(PORTAL / "harvest-repository-config.xml.fragment")
    assert ogc.get("id") != oai.get("id")


def test_services_fragment_matches_the_mapper_organisations():
    entry = yaml.safe_load((OGC / "services.yaml.fragment").read_text(encoding="utf-8"))[
        "interplant-dataplant-ogc"]
    assert entry["provider"]["name"] == ORGANISATIONS["provider"][0]["name"]
    assert entry["datacenter"]["name"] == ORGANISATIONS["datacenter"][0]["name"]