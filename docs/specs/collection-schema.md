# L1 Collection Schema

**Scope:** The shape of one L1 collection descriptor, the list of the 11 shipped collections, and the classifier rules that map ARCs onto the two axes.

**Authoritative schema:** [`schemas/collection-descriptor.schema.json`](schemas/collection-descriptor.schema.json).

**Canonical examples:** [`examples/collection-proteomics.yaml`](examples/collection-proteomics.yaml), [`examples/collection-fieldtrials.yaml`](examples/collection-fieldtrials.yaml).

## 1. Descriptor shape

Every collection is described by one YAML file. Required keys:

| Key | Type | Notes |
|---|---|---|
| `id`         | string | `^dataplant-[a-z][a-z0-9-]*$`. Stable; referenced in URLs. |
| `title`      | string | Portal-displayed name. |
| `description`| string | One-paragraph abstract, ≥ 20 chars. |
| `keywords`   | array  | At least one keyword. |
| `license`    | string | SPDX identifier preferred. |
| `axis`       | enum   | `omics` or `experiment_context`. Identifies which collection axis this belongs to. |
| `provider`   | object | `{ name, url }`. Usually DataPLANT. |
| `extent`     | object | `spatial.bbox` + `temporal.interval`. The bbox stays world-wide and is NOT narrowed: a bbox is a superset hint, and one computed from a past harvest can exclude an ARC harvested later, causing a client to skip a collection that does contain matching records. |
| `links`      | array  | `describedby`, `items`, `related` at minimum. |
| `query_rule` | string | SQL `WHERE` fragment over `arc_records.properties`. |

Optional: `featured` (array of record ids), `narrative` (Markdown for overview page).

This schema, including the required `query_rule` and the `axis` enum, governs
only the `dataplant-*` omics/experiment_context descriptors below.
`catalog/collections/arc-locations.yaml` is a geodata descriptor outside this
schema: it has no `query_rule` (arc-locations is a fixed view, not a filtered
one) and uses `axis: geo`, which is not in the enum. `scripts/generate_catalog.py`'s
schema validation and `tests/specs/test_collection_descriptors.py` both glob
`dataplant-*.yaml`, so neither ever sees arc-locations.yaml; that glob is what
draws the line. `generate_catalog.py` still reads arc-locations.yaml
separately (`LOCATIONS_DESCRIPTOR`) to emit its own `arc_locations` view and
pygeoapi resource, just without the schema check or the query_rule machinery.

## 2. The 11 collections

**Axis: omics (8 collections)**

| id | query_rule | est. |
|---|---|---|
| `dataplant-transcriptomics` | `'transcriptomics' = ANY(omics_domains)` | ~45 |
| `dataplant-genomics`        | `'genomics' = ANY(omics_domains)`        | ~30 |
| `dataplant-proteomics`      | `'proteomics' = ANY(omics_domains)`      | ~35 |
| `dataplant-metabolomics`    | `'metabolomics' = ANY(omics_domains)`    | ~30 |
| `dataplant-phenotyping`     | `'phenotyping' = ANY(omics_domains)`     | ~30 |
| `dataplant-imaging`         | `'imaging' = ANY(omics_domains)`         | ~20 |
| `dataplant-microbiome`      | `'microbiome' = ANY(omics_domains)`      | ~8  |
| `dataplant-multi-omics`     | `array_length(omics_domains, 1) >= 2`    | ~67 |

**Axis: experiment_context (3 collections)**

| id | query_rule | est. |
|---|---|---|
| `dataplant-field-trials` | `experiment_context IN ('field','mixed')`      | ~25  |
| `dataplant-greenhouse`   | `experiment_context IN ('greenhouse','mixed')` | ~20  |
| `dataplant-lab`          | `experiment_context IN ('lab','mixed')`        | ~110 |

ARCs appear in as many collections as they satisfy rules for. Example: `Ru_ChlamyHeatstress` — 4 omics domains + `experiment_context: lab` — appears in 6 collections (4 single-domain + multi-omics + lab).

## 3. Classifier rules

### 3.1 `omics_domains`

Inputs: the set of assay-folder names under `assays/` in each ARC. Each folder name is normalized via the vocabulary lookup in `schemas/vocabularies.yaml` (see § 4) and mapped to zero or more canonical domains. An ARC's `omics_domains` is the union over all its assay folders.

- No match → the assay contributes nothing (but is still described as `domain: other`).
- All assays unmatched → `omics_domains: ["other"]`.

### 3.2 `experiment_context`

Applied in priority order. First rule to match wins:

1. Any study is annotated as MIAPPE observation-unit → `field`.
2. ISA `GROWTH FACILITY` field present → map directly (`field` / `greenhouse` / `lab`).
3. Assay-name substrings (`drone`, `flyover`, `field` → `field`; `greenhouse`, `gh-` → `greenhouse`).
4. ARC has assays in more than one of the above → `mixed`.
5. Fallback: ARCs where all assays are `mass spectrometry`, `microscopy`, or `nucleic acid sequencing` default to `lab`.

The classifier emits a confidence score and a list of signals used, both captured in the harvester log.

## 4. Vocabularies

Controlled vocabularies live in [`schemas/vocabularies.yaml`](schemas/vocabularies.yaml). The harvester validates known terms during ingest, ingests records with unknown terms verbatim (see design doc § 6.4), and logs unknowns for curation. Vocabularies covered:

- Omics domain keywords (assay-folder substring → domain).
- ENA library strategy values.
- Sequencing platforms.
- Acquisition modes (DDA/DIA/SRM/PRM).
- Chromatography and ion modes.
- Trait categories (phenotyping).
- Image formats.
- Target genes (microbiome).

## 5. Overview-page usage

The `narrative` field is the content that populates the "About this collection" section of the Earth Data Portal overview page (see design doc § 8). Hand-written in Markdown; reviewed by PR; rendered by the portal plugin directly.

## 6. Validation

`tests/specs/test_collection_descriptor.py` runs in CI. Add one new example for every new collection.
