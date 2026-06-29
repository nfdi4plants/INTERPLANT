"""Flask HTTP layer for the OAI-PMH service.

Single endpoint /oai dispatching on ?verb=. DSN comes from INTERPLANT_DSN.
"""
from __future__ import annotations

import os

from flask import Flask, Response, request

from oai.source import RecordSource
from oai.verbs import DUP_VERB_MARKER, RepoConfig, handle

_DEFAULT_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"

_DUP_MARKER = "__duplicateArgument__"


def _flatten_args(values) -> dict[str, str]:
    """Flatten the request MultiDict to a single-value dict. A repeated
    argument is a protocol error. A repeated `verb` is badVerb per OAI-PMH 2.0,
    signalled with DUP_VERB_MARKER; any other repeated argument is badArgument,
    signalled with a marker key that no verb's allowed-argument set contains, so
    oai.verbs.handle rejects it via per-verb argument validation.

    The first value of every key is kept (including a duplicated verb) so a
    duplicated verb still dispatches far enough to reach the badVerb check."""
    params: dict[str, str] = {}
    dup_keys: list[str] = []
    for key in values:
        vals = values.getlist(key)
        if len(vals) > 1:
            dup_keys.append(key)
        params[key] = vals[0]
    if "verb" in dup_keys:
        params[DUP_VERB_MARKER] = ""
    elif dup_keys:
        params[_DUP_MARKER] = ""
    return params


def create_app() -> Flask:
    app = Flask(__name__)
    source = RecordSource(os.environ.get("INTERPLANT_DSN", _DEFAULT_DSN))
    config = RepoConfig()

    @app.route("/oai", methods=["GET", "POST"])
    def oai() -> Response:
        params = _flatten_args(request.values)
        base_url = request.base_url
        body = handle(params, base_url=base_url, source=source, config=config)
        return Response(body, mimetype="text/xml")

    return app


app = create_app()
