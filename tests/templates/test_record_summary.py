"""The record summary used by the meta description and the Dataset JSON-LD.

41 of 157 production records carry an empty description, which left the
schema.org Dataset block with "description": "" and made those records
ineligible for dataset search.
"""
from __future__ import annotations

import html as html_module
import re

from .builders import ITEM_TPL, dataset_jsonld, item_data

BOILERPLATE = "is an Annotated Research Context (ARC) published on the DataPLANT DataHUB"


def _meta_description(html: str) -> str:
    match = re.search(r'<meta name="description" content="([^"]*)"', html)
    assert match, "no meta description"
    return html_module.unescape(match.group(1))


def test_real_description_is_used_unchanged(render):
    html = render(ITEM_TPL, item_data(description="Flavonoids play a central role."))
    assert dataset_jsonld(html)["description"] == "Flavonoids play a central role."
    assert BOILERPLATE not in html


def test_empty_description_is_composed_from_domains_and_organism(render):
    html = render(
        ITEM_TPL,
        item_data(
            title="Subcellular metabolomics and proteomics data",
            description="",
            omics_domains=["metabolomics", "proteomics"],
            organism=["Arabidopsis thaliana"],
        ),
    )
    assert dataset_jsonld(html)["description"] == (
        "Subcellular metabolomics and proteomics data is an Annotated Research "
        "Context (ARC) published on the DataPLANT DataHUB, covering metabolomics "
        "and proteomics data from Arabidopsis thaliana."
    )


def test_other_domain_is_dropped(render):
    html = render(
        ITEM_TPL,
        item_data(
            title="amaranth_seed_color", description="", omics_domains=["other"], organism=[]
        ),
    )
    assert dataset_jsonld(html)["description"] == (
        "amaranth_seed_color is an Annotated Research Context (ARC) published on "
        "the DataPLANT DataHUB."
    )


def test_organism_without_domains(render):
    html = render(
        ITEM_TPL,
        item_data(
            title="Maize panel", description="", omics_domains=["other"], organism=["Zea mays"]
        ),
    )
    assert dataset_jsonld(html)["description"] == (
        "Maize panel is an Annotated Research Context (ARC) published on the "
        "DataPLANT DataHUB, with data from Zea mays."
    )


def test_several_domains_are_joined_readably(render):
    html = render(
        ITEM_TPL,
        item_data(
            title="Three",
            description="",
            omics_domains=["genomics", "other", "imaging", "proteomics"],
            organism=[],
        ),
    )
    assert dataset_jsonld(html)["description"] == (
        "Three is an Annotated Research Context (ARC) published on the DataPLANT "
        "DataHUB, covering genomics, imaging and proteomics data."
    )


def test_several_organisms_are_joined_readably(render):
    html = render(
        ITEM_TPL,
        item_data(
            title="Two",
            description="",
            omics_domains=["genomics"],
            organism=["Zea mays", "Oryza sativa"],
        ),
    )
    assert dataset_jsonld(html)["description"] == (
        "Two is an Annotated Research Context (ARC) published on the DataPLANT "
        "DataHUB, covering genomics data from Zea mays and Oryza sativa."
    )


def test_null_description_never_renders_none(render):
    html = render(
        ITEM_TPL,
        item_data(title="Nulled", description=None, omics_domains=["other"], organism=[]),
    )
    assert "None" not in html
    assert dataset_jsonld(html)["description"].startswith("Nulled ")


def test_composed_description_clears_the_google_minimum(render):
    """schema.org Dataset descriptions must be at least 50 characters."""
    html = render(
        ITEM_TPL, item_data(title="x", description="", omics_domains=["other"], organism=[])
    )
    assert len(dataset_jsonld(html)["description"]) >= 50


def test_meta_description_matches_the_dataset_description(render):
    html = render(
        ITEM_TPL,
        item_data(
            title="Maize panel", description="", omics_domains=["other"], organism=["Zea mays"]
        ),
    )
    assert _meta_description(html) == dataset_jsonld(html)["description"]


def test_composed_summary_is_never_shown_as_an_abstract(render):
    html = render(ITEM_TPL, item_data(description="", omics_domains=["other"], organism=[]))
    assert 'id="dp-abstract"' not in html


def test_real_abstract_is_still_shown(render):
    html = render(ITEM_TPL, item_data(description="A real abstract."))
    assert 'id="dp-abstract"' in html


def test_special_characters_survive_into_the_json_ld(render):
    html = render(
        ITEM_TPL,
        item_data(title='A & B "quoted"', description="", omics_domains=["other"], organism=[]),
    )
    assert dataset_jsonld(html)["description"].startswith('A & B "quoted" is an')
