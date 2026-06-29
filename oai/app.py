"""Flask HTTP layer for the OAI-PMH service.

Single endpoint /oai dispatching on ?verb=. DSN comes from INTERPLANT_DSN.
"""
from __future__ import annotations

import os

from flask import Flask, Response, request

from oai.source import RecordSource
from oai.verbs import RepoConfig, handle

_DEFAULT_DSN = "postgresql://interplant:interplant@localhost:5432/interplant"

_DUP_MARKER = "__duplicateArgument__"


def _flatten_args(values) -> dict[str, str]:
    """Flatten the request MultiDict to a single-value dict. A repeated
    argument is a protocol error; signal it by carrying a marker key that
    oai.verbs.handle rejects via per-verb argument validation (no verb's
    allowed-argument set contains it), which renders a badArgument response.

    The first value of every key is kept (including a duplicated verb) so that
    a duplicate verb still dispatches far enough to reach argument validation,
    where the marker raises badArgument rather than collapsing to badVerb."""
    params: dict[str, str] = {}
    duplicate = False
    for key in values:
        vals = values.getlist(key)
        if len(vals) > 1:
            duplicate = True
        params[key] = vals[0]
    if duplicate:
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
