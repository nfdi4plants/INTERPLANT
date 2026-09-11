"""Pin oai.mapping's duplicated tier table against harvester.extractors.location's.

oai/mapping.py duplicates _TIER_BY_ROLE / tier_of from harvester.extractors.location
because harvester/ is not part of the oai container image (see the comment on
oai.mapping._TIER_BY_ROLE). This test lives in tests/specs/, not the oai image, so
it may import both modules and catch drift the image split would otherwise hide
silently: a new institution-tier role added only to harvester would make the oai
copy fall through to its "extracted" default, filtering the point out of every
study with no exception and no log line (L2).
"""
from __future__ import annotations

import json
from pathlib import Path

from harvester.extractors import location as harvester_location
from oai import mapping as oai_mapping

SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "docs" / "specs" / "schemas" / "record.schema.json"
)


def _location_roles() -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    return schema["$defs"]["Properties"]["properties"]["locations"]["items"][
        "properties"
    ]["role"]["enum"]


def test_oai_and_harvester_tier_tables_agree_on_every_role():
    roles = _location_roles()
    assert roles, "record.schema.json's location role enum must not be empty"
    for role in roles:
        harvester_tier = harvester_location.tier_of(role)
        oai_tier = oai_mapping._tier_of(role)
        assert harvester_tier == oai_tier, (
            f"role {role!r} disagrees between harvester.extractors.location.tier_of "
            f"({harvester_tier!r}) and oai.mapping._tier_of ({oai_tier!r}) - "
            "the duplicated tier tables have drifted"
        )


def test_oai_and_harvester_agree_on_the_precedence_order():
    # M1's per-study chain duplicated _TIER_ORDER as well as the role map, so
    # the same silent-drift argument applies to it: a reordering on one side
    # alone would pick a different winning tier for a study than the record
    # geometry picks, with no exception and no log line.
    assert harvester_location._TIER_ORDER == oai_mapping._TIER_ORDER, (
        f"tier precedence order disagrees between harvester.extractors.location "
        f"({harvester_location._TIER_ORDER!r}) and oai.mapping "
        f"({oai_mapping._TIER_ORDER!r}) - the duplicated tier tables have drifted"
    )
