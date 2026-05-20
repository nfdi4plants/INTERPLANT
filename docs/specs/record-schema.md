# L2 Record Schema

**Scope:** The structure of one INTERPLANT record. Each record represents exactly one ARC and carries assay-level content as structured sub-resources. This spec is the upstream contract for everything served at `/collections/{id}/items/*` and for the mapper that produces portal-facing `DocumentSchema.json` documents.

**Authoritative schema:** [`schemas/record.schema.json`](schemas/record.schema.json) (+ [`schemas/assay-extensions.schema.json`](schemas/assay-extensions.schema.json)).

**Canonical examples:** [`examples/record-complete.json`](examples/record-complete.json), [`examples/record-partial.json`](examples/record-partial.json), [`examples/record-fieldtrial.json`](examples/record-fieldtrial.json).

## 1. Top-level shape

A record is a GeoJSON Feature with OGC API Records extensions. Required top-level keys:

| Key | Type | Notes |
|---|---|---|
| `id`         | string | Slug unique within the catalog. `^[a-z0-9][a-z0-9-]*$`. Generated from ARC path. |
| `type`       | string | Always `"Feature"`. |
| `conformsTo` | array  | OGC API Records conformance URIs. |
| `time`       | object | `{ "interval": [start, end] }` - ISO 8601. Either bound may be `null`. |
| `geometry`   | object or `null` | GeoJSON geometry. `null` for lab-based ARCs and field/greenhouse ARCs with no ISA geometry. |
| `properties` | object | Record-level metadata (§ 2). |
| `links`      | array  | OGC API Records links (§ 4). |

## 2. Properties

Required: `title`, `description`, `created`, `updated`, `keywords`, `license`, `arc_source_uri`, `uniqueId`, `contacts`, `creators`, `publications`, `omics_domains`, `experiment_context`, `organism`, `project`, `studies`, `assays`, `record_quality`, `harvested_at`, `harvester_version`.

Optional: `doi`, `language`.

Notable structural choices:

- **`uniqueId` is a UUIDv5** derived from `arc_source_uri` by the harvester. Stable across harvests.
- **`doi` is optional** but strongly preferred - its absence causes `record_quality: "partial"`.
- **`license` is required.** If the ARC provides none, the harvester sets `"unknown"` and raises to `record_quality: "partial"`.
- **`keywords` is always present**, possibly empty.

## 3. Promoted facets (L3 queryables)

All four are required on every record. These are the only fields that drive collection membership and filter UX.

| Field | Values |
|---|---|
| `omics_domains`      | array of `transcriptomics`, `genomics`, `proteomics`, `metabolomics`, `phenotyping`, `imaging`, `microbiome`, `other`. At least one. |
| `experiment_context` | one of `field`, `greenhouse`, `lab`, `mixed`. |
| `organism`           | array of organism strings, normalized to NCBI Taxonomy where possible. May be empty for non-biological ARCs. |
| `project`            | array of consortium/project labels. May be empty. |

## 4. Links

Required `rel` values: `self`, `canonical`. Optional and expected: `cite-as` (DOI URL), `via` (arctrl raw JSON), `describedby` (this schema URL), `related` (WP3 viewer URLs).

## 5. Studies

An array of study objects. Each study has `id`, `title`, optional `design_type`, optional `factors`. Study metadata in ARCs lives in `isa.study.xlsx`; cross-assay study metadata is aggregated here.

## 6. Assays

An array of assay objects. Each assay combines:

- **Core fields:** `id`, `domain`, `technology_type`, `measurement_type`, `file_counts`.
- **Per-domain extension:** one of the eight profiles in `assay-extensions.schema.json`. Which extension is required is determined by `domain`.

Example (transcriptomics):

```json
{
  "id": "transcriptomics",
  "domain": "transcriptomics",
  "technology_type": "nucleic acid sequencing",
  "measurement_type": "transcription profiling",
  "library_strategy": "RNA-Seq",
  "platform": "ILLUMINA",
  "file_counts": { "raw": 24, "derived": 3 }
}
```

Per-domain required fields:

| Domain | Required extension fields |
|---|---|
| `transcriptomics`, `genomics` | `library_strategy`, `platform` |
| `proteomics`                  | `acquisition_mode` |
| `metabolomics`                | `chromatography`, `ion_mode` |
| `phenotyping`                 | `trait_category` |
| `imaging`                     | `image_format` |
| `microbiome`                  | `target_gene` |
| `other`                       | - (domain only) |

## 7. Provenance

`record_quality` (`complete` | `partial`), `harvested_at` (ISO datetime), `harvester_version` (semver) are required on every record. They are set exclusively by the harvester, never by content providers.

## 8. Versioning

This schema follows semver at the JSON Schema `$id` level. Additive changes (new optional fields, new enum values) are minor-version. Removing or renaming a required field, or tightening types, is a major-version break.

## 9. Validation

`tests/specs/test_record_schema.py` runs in CI and must pass for every commit.
