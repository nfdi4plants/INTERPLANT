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

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
PAGE_SIZE = 100
_VALID_PREFIXES = ("oai_dc", "documentschema")

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

_NO_ARG_VERBS = {"Identify", "ListMetadataFormats", "ListSets",
                 "ListIdentifiers", "ListRecords", "GetRecord"}


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
        if verb not in _NO_ARG_VERBS:
            raise OaiError("badVerb", "illegal or missing verb")
        # echo request args only once we know the verb is legal
        for key, value in params.items():
            request.set(key, value)
        _dispatch(root, verb, params, source=source, config=config, base_url=base_url)
    except OaiError as err:
        # On protocol arg/verb errors, do not echo attributes (spec rule).
        if err.code in ("badVerb", "badArgument"):
            request.attrib.clear()
        SubElement(root, f"{{{OAI_NS}}}error", {"code": err.code}).text = err.message
    return tostring(root, encoding="utf-8", xml_declaration=True)


def _list_records(root, verb, params, *, source, config):  # implemented in Task 5
    raise OaiError("badArgument", "not yet implemented")


def _get_record(root, params, *, source, config):  # implemented in Task 5
    raise OaiError("badArgument", "not yet implemented")
