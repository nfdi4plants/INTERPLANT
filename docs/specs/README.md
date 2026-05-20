# INTERPLANT Specs

Contracts for WP1 + WP2. These are the authoritative references; the plan document at `docs/superpowers/specs/2026-04-21-interplant-wp1-wp2-design.md` is the upstream design this derives from.

## Spec documents

| Spec | Responsibility |
|------|----------------|
| [`record-schema.md`](record-schema.md) | L2 record structure (one record per ARC) |
| [`collection-schema.md`](collection-schema.md) | L1 collection descriptors + the 11 collections |
| [`portal-mapping.md`](portal-mapping.md) | Mapping from L2 record to the portal's `DocumentSchema.json` |
| [`harvester.md`](harvester.md) | Harvester behavior: enumeration, filter, parse, classify, upsert |

## Machine-enforceable contracts

| File | Validates |
|------|-----------|
| [`schemas/record.schema.json`](schemas/record.schema.json) | `examples/record-*.json` |
| [`schemas/collection-descriptor.schema.json`](schemas/collection-descriptor.schema.json) | `examples/collection-*.yaml` |
| [`schemas/portal-document-schema.json`](schemas/portal-document-schema.json) | `examples/portal-document-*.json` (pinned from AWI upstream) |
| [`schemas/vocabularies.yaml`](schemas/vocabularies.yaml) | Controlled vocabularies referenced by the record schema |

## Running the spec tests

```
uv run pytest tests/specs -v
```

Every example must validate against its schema. CI runs this on every commit.
