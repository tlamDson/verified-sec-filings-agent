"""A stand-in for the Next.js app, for the simulated-user driver's tests (no network).

It plays the Auth.js endpoints the driver signs in with (csrf, credentials callback,
session) and forwards /api/chat and /api/feedback to the in-process API with the signed-in
account's identity, as the real route handlers do. The accounts are simulated test
accounts and the password is made up for the tests.
"""

import json
from typing import Any
from urllib.parse import parse_qs

import httpx
from api_kit import Api, auth

from sec_agent.api.identity import Identity

BASE_URL = "https://web.test"
PASSWORD = "simulated-test-password"
CSRF = "csrf-0123"


class FakeWebApp:
    def __init__(self, api: Api | None = None, *, session_cohort: str = "simulated") -> None:
        self.api = api
        self.session_cohort = session_cohort
        self.paths: list[str] = []
        self.sign_ins: list[str] = []
        self.chat_status: int | None = None
        """When set, /api/chat answers this status with an error body instead."""

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=BASE_URL, transport=self.transport())

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(f"{request.method} {path}")
        email = _session_email(request)
        if path == "/api/auth/csrf":
            return httpx.Response(
                200,
                json={"csrfToken": CSRF},
                headers={"set-cookie": "next-auth.csrf-token=c1; Path=/"},
            )
        if path == "/api/auth/callback/simulated":
            return self._callback(request)
        if path == "/api/auth/session":
            if email is None:
                return httpx.Response(200, json={})
            identity = {"id": f"sim:{email}", "cohort": self.session_cohort}
            return httpx.Response(200, json={"identity": identity})
        if email is None:
            return httpx.Response(401, json={"error": {"code": "unauthorized", "message": "x"}})
        if path == "/api/chat" and self.chat_status is not None:
            body = {"error": {"code": "daily_limit", "message": "limit"}}
            return httpx.Response(self.chat_status, json=body)
        if path in ("/api/chat", "/api/feedback"):
            return self._forward(path.removeprefix("/api"), request, email)
        return httpx.Response(404)

    def _callback(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        cookies = request.headers.get("cookie", "")
        good = (
            form.get("csrfToken") == CSRF
            and "next-auth.csrf-token=c1" in cookies
            and form.get("password") == PASSWORD
            and form.get("json") == "true"
        )
        if not good:
            return httpx.Response(200, json={"url": f"{BASE_URL}/?error=CredentialsSignin"})
        self.sign_ins.append(form["email"])
        return httpx.Response(
            200,
            json={"url": BASE_URL},
            headers={"set-cookie": f"next-auth.session-token={form['email']}; Path=/"},
        )

    def _forward(self, path: str, request: httpx.Request, email: str) -> httpx.Response:
        assert self.api is not None, "this fake has no API behind it"
        identity = Identity(user_id=f"sim:{email}", cohort="simulated")
        body: Any = json.loads(request.content)
        upstream = self.api.client.post(f"/v1{path}", json=body, headers=auth(identity))
        headers = {"content-type": upstream.headers.get("content-type", "application/json")}
        return httpx.Response(upstream.status_code, content=upstream.content, headers=headers)


def _session_email(request: httpx.Request) -> str | None:
    for part in request.headers.get("cookie", "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == "next-auth.session-token" and value:
            return value
    return None
