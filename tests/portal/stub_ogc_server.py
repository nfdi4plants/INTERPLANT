"""A minimal OGC API Records items endpoint that can misbehave on purpose.

Records the full request path including the query string, because the
"never sends q" and "never filters" tests are assertions about the query.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


class StubOGC:
    def __init__(self, total=25, page_size=10, mode="next", features=None):
        self.total = total if features is None else len(features)
        self.page_size = page_size
        self.mode = mode  # next | offset_only | stuck_next | foreign_next | fail_midway
        self.omit_number_matched = False
        self.features = features
        self.requests: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.requests.append(self.path)
                qs = parse_qs(urlparse(self.path).query)
                offset = int(qs.get("offset", ["0"])[0])
                limit = int(qs.get("limit", [str(outer.page_size)])[0])

                if outer.mode == "fail_midway" and offset > 0:
                    self._send(500, {"code": "NoApplicableCode"})
                    return

                items = outer._items(offset, limit)
                body = {"type": "FeatureCollection", "features": items,
                        "numberReturned": len(items), "links": outer._links(offset, limit)}
                if not outer.omit_number_matched:
                    body["numberMatched"] = outer.total
                self._send(200, body)

            def _send(self, status, body):
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/geo+json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self._server.server_port}"

    def _items(self, offset, limit):
        if self.features is not None:
            return self.features[offset:offset + limit]
        return [
            {"type": "Feature", "id": f"rec{i:02d}", "geometry": None,
             "properties": {"title": f"Title {i}", "created": "2026-06-24T00:00:00Z"}}
            for i in range(offset, min(offset + limit, self.total))
        ]

    def _links(self, offset, limit):
        links = [{"rel": "self", "href": f"{self.base}/collections/c/items"}]
        nxt = offset + limit
        if self.mode == "offset_only" or nxt >= self.total:
            return links
        if self.mode == "stuck_next":
            href = f"{self.base}/collections/c/items?f=json&limit={limit}&offset={offset}"
        elif self.mode == "foreign_next":
            href = f"https://evil.example/collections/c/items?f=json&limit={limit}&offset={nxt}"
        else:
            href = f"{self.base}/collections/c/items?f=json&limit={limit}&offset={nxt}"
        links.append({"rel": "next", "href": href})
        return links

    def __enter__(self):
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()