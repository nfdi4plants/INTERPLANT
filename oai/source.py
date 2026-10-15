"""Postgres-backed record source for the OAI-PMH service.

Only this module imports psycopg. Records are read from the `records` table;
the OAI datestamp is `ingested_at`. Paging uses the full-precision ingested_at
(not the second-truncated display datestamp) to keep the cursor stable.

Author: Mohamed Abouzid m.abouzid@fz-juelich.de
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

_SECONDS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_DAY_FMT = "%Y-%m-%d"


def parse_oai_datetime(value: str) -> datetime:
    """Parse an OAI from/until argument in seconds or day granularity (UTC)."""
    for fmt in (_SECONDS_FMT, _DAY_FMT):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"invalid OAI datetime: {value!r}")


def format_oai_datetime(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(_SECONDS_FMT)


@dataclass(frozen=True)
class OaiRecord:
    identifier: str
    datestamp: str          # display, second granularity, trailing Z
    cursor_ts: datetime     # raw ingested_at, full precision, for paging
    payload: dict


def _to_record(row) -> OaiRecord:
    rid, ingested_at, payload = row
    return OaiRecord(
        identifier=rid,
        datestamp=format_oai_datetime(ingested_at),
        cursor_ts=ingested_at,
        payload=payload,
    )


class RecordSource:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def earliest_datestamp(self) -> str | None:
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT min(ingested_at) FROM records")
            (val,) = cur.fetchone()
        return format_oai_datetime(val) if val is not None else None

    def get(self, identifier: str) -> OaiRecord | None:
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, ingested_at, payload FROM records WHERE id = %s",
                (identifier,),
            )
            row = cur.fetchone()
        return _to_record(row) if row is not None else None

    def list(
        self,
        *,
        frm: datetime | None = None,
        until: datetime | None = None,
        after: tuple[datetime, str] | None = None,
        limit: int = 100,
    ) -> list[OaiRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if frm is not None:
            clauses.append("ingested_at >= %s")
            params.append(frm)
        if until is not None:
            clauses.append("ingested_at <= %s")
            params.append(until)
        if after is not None:
            clauses.append("(ingested_at, id) > (%s, %s)")
            params.extend(after)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        sql = (
            f"SELECT id, ingested_at, payload FROM records{where} "
            "ORDER BY ingested_at, id LIMIT %s"
        )
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_to_record(r) for r in rows]
