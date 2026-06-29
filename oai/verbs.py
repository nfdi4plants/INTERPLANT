"""OAI-PMH 2.0 protocol layer: envelope, errors, verb dispatch.

Pure given a `source` object (RecordSource or a fake). Generates XML with
ElementTree. Resumption/list verbs are added in a later step but dispatch is
wired here so unknown verbs return badVerb.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring

from oai.formats import (
    AWI_NS,
    DOCSCHEMA_REF,
    OAI_DC_NS,
    documentschema_element,
    oai_dc_element,
)
from oai.mapping import map_record
from oai.source import parse_oai_datetime

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
PAGE_SIZE = 100
_VALID_PREFIXES = ("oai_dc", "documentschema")

# Sentinel injected by the HTTP layer (oai.app) when the `verb` argument is
# repeated; per OAI-PMH 2.0 a repeated verb is badVerb, not badArgument.
DUP_VERB_MARKER = "__duplicateVerb__"

register_namespace("", OAI_NS)
register_namespace("xsi", XSI_NS)


@dataclass
class RepoConfig:
    repository_name: str = "INTERPLANT"
    admin_email: str = "m.abouzid@fz-juelich.de"
    repository_identifier: str = "interplant"
    earliest_default: str = "2020-01-01T00:00:00Z"


class OaiError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _root() -> Element:
    return Element(
        f"{{{OAI_NS}}}OAI-PMH",
        {f"{{{XSI_NS}}}schemaLocation": f"{OAI_NS} {OAI_NS}OAI-PMH.xsd"},
    )


def _oai_id(config: RepoConfig, local_id: str) -> str:
    return f"oai:{config.repository_identifier}:{local_id}"


def _strip_oai_id(config: RepoConfig, identifier: str) -> str:
    prefix = f"oai:{config.repository_identifier}:"
    if not identifier.startswith(prefix):
        raise OaiError("idDoesNotExist", identifier)
    return identifier[len(prefix):]


def _header(parent: Element, config: RepoConfig, rec) -> None:
    header = SubElement(parent, f"{{{OAI_NS}}}header")
    SubElement(header, f"{{{OAI_NS}}}identifier").text = _oai_id(config, rec.identifier)
    SubElement(header, f"{{{OAI_NS}}}datestamp").text = rec.datestamp


def _metadata(parent: Element, prefix: str, rec) -> None:
    meta = SubElement(parent, f"{{{OAI_NS}}}metadata")
    if prefix == "oai_dc":
        meta.append(oai_dc_element(rec.payload))
    else:
        meta.append(documentschema_element(map_record(rec.payload)))


def encode_token(state: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(state, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def decode_token(token: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any corruption is a bad token
        raise OaiError("badResumptionToken", "invalid resumptionToken") from exc


# --- verb implementations -------------------------------------------------

def _identify(root: Element, source, config: RepoConfig, base_url: str) -> None:
    el = SubElement(root, f"{{{OAI_NS}}}Identify")
    SubElement(el, f"{{{OAI_NS}}}repositoryName").text = config.repository_name
    SubElement(el, f"{{{OAI_NS}}}baseURL").text = base_url
    SubElement(el, f"{{{OAI_NS}}}protocolVersion").text = "2.0"
    SubElement(el, f"{{{OAI_NS}}}adminEmail").text = config.admin_email
    SubElement(el, f"{{{OAI_NS}}}earliestDatestamp").text = (
        source.earliest_datestamp() or config.earliest_default
    )
    SubElement(el, f"{{{OAI_NS}}}deletedRecord").text = "no"
    SubElement(el, f"{{{OAI_NS}}}granularity").text = "YYYY-MM-DDThh:mm:ssZ"


def _list_metadata_formats(root: Element, source, config: RepoConfig, params: dict) -> None:
    if "identifier" in params:
        local = _strip_oai_id(config, params["identifier"])
        if source.get(local) is None:
            raise OaiError("idDoesNotExist", params["identifier"])
    el = SubElement(root, f"{{{OAI_NS}}}ListMetadataFormats")
    for prefix, schema, ns in (
        ("oai_dc", f"{OAI_DC_NS}".rstrip("/") + ".xsd", OAI_DC_NS),
        ("documentschema", DOCSCHEMA_REF, AWI_NS),
    ):
        fmt = SubElement(el, f"{{{OAI_NS}}}metadataFormat")
        SubElement(fmt, f"{{{OAI_NS}}}metadataPrefix").text = prefix
        SubElement(fmt, f"{{{OAI_NS}}}schema").text = schema
        SubElement(fmt, f"{{{OAI_NS}}}metadataNamespace").text = ns


# --- dispatch + envelope --------------------------------------------------

_VALID_VERBS = {"Identify", "ListMetadataFormats", "ListSets",
                "ListIdentifiers", "ListRecords", "GetRecord"}

# Per OAI-PMH 2.0, the arguments each verb accepts besides "verb". Any other
# argument is badArgument. (Resumption-token exclusivity and required-prefix
# rules are enforced inside the verb implementations.)
_VERB_ARGS: dict[str, set[str]] = {
    "Identify": set(),
    "ListSets": set(),
    "ListMetadataFormats": {"identifier"},
    "ListIdentifiers": {"from", "until", "set", "metadataPrefix", "resumptionToken"},
    "ListRecords": {"from", "until", "set", "metadataPrefix", "resumptionToken"},
    "GetRecord": {"identifier", "metadataPrefix"},
}


def _validate_args(verb: str, params: dict) -> None:
    allowed = _VERB_ARGS[verb]
    for key in params:
        if key != "verb" and key not in allowed:
            raise OaiError("badArgument", f"illegal argument {key!r} for {verb}")


def _dispatch(root: Element, verb: str, params: dict, *, source, config, base_url) -> None:
    if verb == "Identify":
        _identify(root, source, config, base_url)
    elif verb == "ListMetadataFormats":
        _list_metadata_formats(root, source, config, params)
    elif verb == "ListSets":
        raise OaiError("noSetHierarchy", "this repository does not support sets")
    elif verb in ("ListIdentifiers", "ListRecords"):
        _list_records(root, verb, params, source=source, config=config)
    elif verb == "GetRecord":
        _get_record(root, params, source=source, config=config)
    else:
        raise OaiError("badVerb", "illegal or missing verb")


def handle(params: dict, *, base_url: str, source, config: RepoConfig) -> bytes:
    root = _root()
    SubElement(root, f"{{{OAI_NS}}}responseDate").text = _now_utc()
    request = SubElement(root, f"{{{OAI_NS}}}request")
    request.text = base_url
    verb = params.get("verb")
    try:
        if DUP_VERB_MARKER in params or verb not in _VALID_VERBS:
            raise OaiError("badVerb", "illegal or missing verb")
        _validate_args(verb, params)
        # echo request args only once the verb and its arguments are legal
        for key, value in params.items():
            request.set(key, value)
        _dispatch(root, verb, params, source=source, config=config, base_url=base_url)
    except OaiError as err:
        # On protocol arg/verb errors, do not echo attributes (spec rule).
        if err.code in ("badVerb", "badArgument"):
            request.attrib.clear()
        SubElement(root, f"{{{OAI_NS}}}error", {"code": err.code}).text = err.message
    return tostring(root, encoding="utf-8", xml_declaration=True)


def _parse_window(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_oai_datetime(value)
    except ValueError as exc:
        raise OaiError("badArgument", f"bad date: {value!r}") from exc


def _parse_until(value: str | None) -> datetime | None:
    """Like _parse_window, but a day-granularity until is inclusive of the
    whole UTC day (bumped to 23:59:59Z) so same-day records are not dropped."""
    if value is None:
        return None
    try:
        dt = parse_oai_datetime(value)
    except ValueError as exc:
        raise OaiError("badArgument", f"bad date: {value!r}") from exc
    if "T" not in value:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt


def _list_records(root: Element, verb: str, params: dict, *, source, config) -> None:
    token = params.get("resumptionToken")
    if token is not None:
        if any(k in params for k in ("metadataPrefix", "from", "until", "set")):
            raise OaiError("badArgument", "resumptionToken must be the only argument")
        state = decode_token(token)
        try:
            prefix = state["p"]
            frm = datetime.fromisoformat(state["f"]) if state.get("f") else None
            until = datetime.fromisoformat(state["u"]) if state.get("u") else None
            after = (datetime.fromisoformat(state["ats"]), state["aid"])
        except (KeyError, ValueError) as exc:
            raise OaiError("badResumptionToken", "invalid resumptionToken") from exc
    else:
        if "set" in params:
            raise OaiError("noSetHierarchy", "this repository does not support sets")
        prefix = params.get("metadataPrefix")
        if not prefix:
            raise OaiError("badArgument", "metadataPrefix is required")
        frm = _parse_window(params.get("from"))
        until = _parse_until(params.get("until"))
        after = None
    if prefix not in _VALID_PREFIXES:
        raise OaiError("cannotDisseminateFormat", prefix)

    rows = source.list(frm=frm, until=until, after=after, limit=PAGE_SIZE + 1)
    has_more = len(rows) > PAGE_SIZE
    page = rows[:PAGE_SIZE]
    if not page and after is None:
        raise OaiError("noRecordsMatch", "no records match the request")

    container = SubElement(root, f"{{{OAI_NS}}}{verb}")
    for rec in page:
        if verb == "ListIdentifiers":
            _header(container, config, rec)
        else:
            record_el = SubElement(container, f"{{{OAI_NS}}}record")
            _header(record_el, config, rec)
            _metadata(record_el, prefix, rec)

    if has_more:
        last = page[-1]
        next_state = {
            "p": prefix,
            "f": frm.isoformat() if frm else None,
            "u": until.isoformat() if until else None,
            "ats": last.cursor_ts.isoformat(),
            "aid": last.identifier,
        }
        SubElement(container, f"{{{OAI_NS}}}resumptionToken").text = encode_token(next_state)
    elif token is not None:
        # Issued a token earlier in the sequence: close it with an empty token.
        SubElement(container, f"{{{OAI_NS}}}resumptionToken").text = ""


def _get_record(root: Element, params: dict, *, source, config) -> None:
    identifier = params.get("identifier")
    prefix = params.get("metadataPrefix")
    if not identifier or not prefix:
        raise OaiError("badArgument", "identifier and metadataPrefix are required")
    if prefix not in _VALID_PREFIXES:
        raise OaiError("cannotDisseminateFormat", prefix)
    local = _strip_oai_id(config, identifier)
    rec = source.get(local)
    if rec is None:
        raise OaiError("idDoesNotExist", identifier)
    container = SubElement(root, f"{{{OAI_NS}}}GetRecord")
    record_el = SubElement(container, f"{{{OAI_NS}}}record")
    _header(record_el, config, rec)
    _metadata(record_el, prefix, rec)
