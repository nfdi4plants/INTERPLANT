"""The fragments we hand AWI must stay consistent with what we actually emit.

Pure file checks, deliberately outside tests/portal/ so they run in CI without
a clone of the AWI harvester repo.
"""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree.ElementTree import fromstring

import yaml

from oai.mapping import ORGANISATIONS

PORTAL = Path(__file__).parent.parent.parent / "portal"
# Their config/harvest-repository-config.xml declares xmlns:c on the root element.
C_NS = "http://www.awi.de/harvester/config"


def test_xml_fragment_is_well_formed_and_targets_the_extern_index():
    raw = (PORTAL / "harvest-repository-config.xml.fragment").read_text(encoding="utf-8")
    element = fromstring(f'<c:wrap xmlns:c="{C_NS}">{raw}</c:wrap>')

    harvester = element.find(f"{{{C_NS}}}harvester")
    assert harvester is not None
    assert harvester.get("id") == "dataplant-arc-harvester"
    assert harvester.findtext(f"{{{C_NS}}}index") == "harvest-extern"
    assert harvester.findtext(f"{{{C_NS}}}mapping") == "EMPTY"
    assert harvester.findtext(f"{{{C_NS}}}class") == "de.awi.index.harvester.sh.ShellHarvester"
    assert (
        harvester.findtext(f"{{{C_NS}}}interceptor")
        == "de.awi.index.harvester.interceptors.PersonDomainInterceptor"
    )

    script = harvester.find(f'{{{C_NS}}}parameter[@name="script"]')
    assert script is not None
    assert "harvest-repository-dataplant-arcs.py" in script.text


def test_services_fragment_matches_the_mapper_organisations():
    """A reviewer seeing two different provider names would rightly reject the MR."""
    service = yaml.safe_load((PORTAL / "services.yaml.fragment").read_text(encoding="utf-8"))
    entry = service["interplant-dataplant"]

    assert entry["provider"]["abbreviation"] == ORGANISATIONS["provider"][0]["abbreviation"]
    assert entry["provider"]["name"] == ORGANISATIONS["provider"][0]["name"]
    assert entry["provider"]["url"] == ORGANISATIONS["provider"][0]["url"]
    assert entry["datacenter"]["abbreviation"] == ORGANISATIONS["datacenter"][0]["abbreviation"]
    assert entry["datacenter"]["name"] == ORGANISATIONS["datacenter"][0]["name"]
    assert entry["datacenter"]["url"] == ORGANISATIONS["datacenter"][0]["url"]


def test_endpoint_placeholder_is_identical_in_script_and_services():
    """The endpoint is one parameter; the two files must not drift apart."""
    script = (PORTAL / "harvest-repository-dataplant-arcs.py").read_text(encoding="utf-8")
    service = yaml.safe_load((PORTAL / "services.yaml.fragment").read_text(encoding="utf-8"))
    entry = service["interplant-dataplant"]

    match = re.search(r"^ENDPOINT = '([^']+)'", script, re.M)
    assert match is not None, "could not find ENDPOINT = '...' in the harvester script"
    endpoint = match.group(1)

    # Unconditional: this is the actual drift detector and must survive even
    # after the REPLACE-ME tripwire below is removed at deployment time.
    assert endpoint == entry["url"] == entry["provider"]["metadata"]["apiUrl"]

    assert "REPLACE-ME" in script, "the host is still unresolved; see portal/README.md"
    assert "REPLACE-ME" in entry["url"]
