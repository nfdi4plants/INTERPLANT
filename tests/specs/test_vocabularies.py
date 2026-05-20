"""vocabularies.yaml must stay consistent with the schemas that reference it."""
from __future__ import annotations


def test_omics_domain_keywords_match_schema_enum(schema_record, load_yaml, load_json):
    """Every omics_domain_keywords key must appear in the record-schema omics_domains enum.

    Catches typos like `omics_domain_keyword:` (singular) and divergence between
    the vocab file and the schema's $defs.OmicsDomain enum.
    """
    vocab = load_yaml("schemas/vocabularies.yaml")
    schema_dict, _registry = schema_record

    vocab_keys = set(vocab["omics_domain_keywords"].keys())
    schema_enum = set(schema_dict["$defs"]["OmicsDomain"]["enum"])

    assert vocab_keys <= schema_enum, (
        f"omics_domain_keywords keys not in OmicsDomain enum: {vocab_keys - schema_enum}"
    )


def test_experiment_context_matches_schema_enum(schema_record, load_yaml):
    """vocabularies.yaml:experiment_context must match the schema's experiment_context enum."""
    vocab = load_yaml("schemas/vocabularies.yaml")
    schema_dict, _registry = schema_record

    vocab_values = set(vocab["experiment_context"])
    properties = schema_dict["$defs"]["Properties"]["properties"]
    schema_enum = set(properties["experiment_context"]["enum"])

    assert vocab_values == schema_enum, (
        f"experiment_context mismatch: vocab={vocab_values}, schema={schema_enum}"
    )


def test_vocabularies_top_level_keys_present(load_yaml):
    """Defensive: catch typos in top-level keys (e.g. omics_domain_keyword: singular)."""
    vocab = load_yaml("schemas/vocabularies.yaml")
    expected = {
        "omics_domain_keywords",
        "platform",
        "acquisition_mode",
        "chromatography",
        "ion_mode",
        "trait_category",
        "image_format",
        "target_gene",
        "experiment_context",
        "growth_facility_map",
    }
    missing = expected - vocab.keys()
    assert not missing, f"vocabularies.yaml missing expected keys: {missing}"
