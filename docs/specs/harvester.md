# Harvester Spec

**Scope:** The behavior contract of the INTERPLANT harvester — the Python job that reads public ARCs from DataPLANT Data Hubs and writes L2 records into the catalog store. This document defines *what* the harvester does and the contracts between its stages. Implementation details (libraries, error-class hierarchy, logging format) are chosen in the harvester implementation plan.

**Upstream design:** `docs/superpowers/specs/2026-04-21-interplant-wp1-wp2-design.md` § 9 (P1). (Local scratch; not in the public repo.)

## 1. Pipeline

The harvester runs five stages in sequence. Each stage takes a structured input and emits a structured output; each stage is independently testable.

1. **Enumerate** — list candidate ARCs from DataPLANT GitLab.
2. **Filter** — apply quality and dedup rules.
3. **Parse** — read ISA investigation + studies + assays.
4. **Classify** — compute `omics_domains` and `experiment_context`.
5. **Upsert** — write the L2 record into Postgres.

## 2. Stage 1 — Enumerate

### Input
- GitLab instance URL (config).
- Optional: project-id allow-list (override for testing).

### Behavior
- Paginate over `GET /api/v4/projects?visibility=public&archived=false`.
- For each project, attempt `GET /api/v4/projects/:id/repository/files/isa.investigation.xlsx/raw?ref=<default_branch>`.
- An ARC is any project whose root contains `isa.investigation.xlsx`.

### Output
Per-project records of the shape `{project_id, path_with_namespace, default_branch, web_url, last_activity_at}`.

### Contract
- Must not require authentication (public projects only).
- Must respect GitLab pagination semantics (follow `Link` header).
- Network failure for a single project is logged but does not abort enumeration.

## 3. Stage 2 — Filter

### Input
The enumerate-stage output.

### Rules
Applied in order; first rule that excludes wins. Each excluded ARC is emitted to the audit log with the rule name.

1. **Empty:** ARC has no entries under `assays/` in the GitLab tree listing → exclude.
2. **Template:** any assay folder name matches `^(yourAssayName|Assay[0-9]*|measurement[0-9]*)$` (case-insensitive) AND the ARC has no other non-template assays → exclude.
3. **QC-only:** every assay folder matches a QC-only pattern (`nanodrop`, `bioanalyzer`, `fastqc`, `qrtpcr`, `qc`) → exclude.
4. **Duplicate:** two or more ARCs share a normalized title or investigation DOI → keep one (preference order: has DOI > most recent `last_activity_at` > lexicographically first namespace).

Normalized title = lowercase, strip whitespace, replace punctuation with `-`, collapse consecutive `-`.

### Output
The same record shape as enumerate, less filtered ARCs.

### Contract
- Stable under reruns — same input set must produce the same kept / excluded partition.
- Dedup policy is logged per kept ARC with the list of suppressed duplicates.

## 4. Stage 3 — Parse

### Input
An ARC record. The stage retrieves:
- `isa.investigation.xlsx`
- `studies/<slug>/isa.study.xlsx` for each studies-dir entry
- `assays/<slug>/isa.assay.xlsx` for each assays-dir entry

### Behavior
- Prefer `arctrl` if stable; otherwise read XLSX directly via `openpyxl`.
- Extract structured ISA blocks: investigation, contacts, publications; per-study: title, design_type, factors; per-assay: technology_type, measurement_type, platform, library_strategy, instrument_name, image_format, etc.

### Output
```python
ParsedARC(
    investigation=Investigation(title, description, created, updated, doi, license, contacts, publications, ...),
    studies=[Study(id, title, design_type, factors)],
    assays=[ParsedAssay(id, domain_raw, technology_type, measurement_type, file_counts, **domain_fields)],
)
```

`file_counts` is derived from a tree listing of each assay folder (counts of files under `dataset/` vs `protocols/derived/`) — set here so Upsert (§ 6) doesn't have to re-walk the tree.

### Contract
- Missing required ISA fields are replaced with `None` and flagged in the quality audit; the stage does not raise.
- Per-assay fields unknown to the schema (beyond core) are retained in a `raw_extras` blob — never dropped. (Named `raw_extras` rather than `raw` to avoid overload with `file_counts.raw`.)
- Encoding edge cases (BOM, UTF-16) are handled.

## 5. Stage 4 — Classify

### Input
A `ParsedARC`.

### Omics classification
- For each assay, look up its folder name against `vocabularies.yaml:omics_domain_keywords` (substring, case-insensitive).
- Assay → zero or more canonical domains.
- ARC `omics_domains` = union over all its assays. Deduplicated, sorted stable.
- If an assay matched nothing, emit `domain: other` for that assay and include `other` in the ARC's `omics_domains` only if no other domain was matched.

### Experiment-context classification
Apply the priority rules from `collection-schema.md` § 3.2. Emit:
- The chosen context (`field` / `greenhouse` / `lab` / `mixed`).
- A confidence score (1.0 for MIAPPE or `GROWTH FACILITY`; 0.7 for substring match; 0.5 for domain-default).
- A signal list (which rule fired).

### Output
`ClassifiedARC(parsed, omics_domains, experiment_context, classifier_signals)`.

### Contract
- Fully deterministic given the vocabularies file and the parsed input.
- Must not raise on unknown vocabulary values — record them in the audit and proceed with "other" / "lab" defaults.

## 6. Stage 5 — Upsert

### Input
A `ClassifiedARC`.

### Behavior
- Compute `uniqueId` as `UUIDv5(arc_source_uri)` (DNS namespace) — stable, derivable.
- Build the L2 record per `record-schema.md`, including provenance fields (`record_quality`, `harvested_at`, `harvester_version`).
- Serialize to JSON, upsert into `arc_records`:
  ```sql
  INSERT INTO arc_records (id, unique_id, body, harvested_at)
  VALUES ($1, $2, $3::jsonb, $4)
  ON CONFLICT (id) DO UPDATE SET
    unique_id = EXCLUDED.unique_id,
    body = EXCLUDED.body,
    harvested_at = EXCLUDED.harvested_at;
  ```

### Quality determination
- `record_quality = complete` when: DOI present, license present, ≥ 1 assay with core fields complete (`id`, `domain`, `technology_type`, `measurement_type`, `file_counts` — see `record-schema.md` § 2.5 `AssayCore`), ≥ 1 study, at least one contact with ORCID.
- Otherwise `record_quality = partial`.

### Contract
- Idempotent on the same input.
- Must validate the record against `record.schema.json` before upsert. Invalid records go to an `arc_errors` table and are NOT written to `arc_records`.
- Transaction boundaries: one transaction per ARC (a single record failure does not roll back the run).

## 7. Run modes

- **Full:** process every public ARC; intended for nightly CI.
- **Single:** process one project by `path_with_namespace` (for debugging).
- **Dry-run:** do everything up to but not including the upsert; emit the candidate records to stdout as JSON.

## 8. Observability

For each run:
- `arc_errors` table captures per-ARC failures with stage, error class, message, stacktrace.
- `arc_runs` table captures one row per run: start/end timestamps, totals (enumerated/filtered/kept), classifier coverage metrics.

The CI job is considered successful if: at least 90 % of enumerated ARCs reached the upsert stage, and at least 95 % of attempted upserts succeeded. Thresholds are tunable; first crossing of either triggers a CI failure email.

## 9. Configuration surface

All configuration via environment variables (no config files):
- `INTERPLANT_GITLAB_URL` — defaults to `https://git.nfdi4plants.org`.
- `INTERPLANT_PG_DSN` — Postgres DSN.
- `INTERPLANT_MODE` — `full` | `single` | `dry-run`.
- `INTERPLANT_SINGLE_PROJECT` — required when `MODE=single`.
- `INTERPLANT_LOG_LEVEL` — `INFO` default; `DEBUG` available.

## 10. What this spec does NOT define (deferred to impl plan)

- Concrete library choices for ISA parsing (`arctrl` vs. direct XLSX).
- Concrete Postgres DDL (lives in the catalog-API implementation plan).
- Retries / backoff policy for GitLab API calls.
- Exact error-class hierarchy.
- Log format (structured JSON vs. human).

These are picked during harvester implementation with the constraints defined above.
