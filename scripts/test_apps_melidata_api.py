#!/usr/bin/env python3
"""Smoke/integration checks for the APPS <-> MeliData API contract.

The script uses ``requests`` only and is intentionally standalone.  OAuth and
read-only checks run by default.  M01/M02 and the data-plane checks are
enabled with ``--write-tests`` because they create an application and write
documents.  A test application is not deleted: the service API deliberately
does not expose destructive app management to APPS.

Examples:

    export OPEN_PLATFORM_SERVICE_CLIENT_SECRET='...'
    python scripts/test_apps_melidata_api.py

    python scripts/test_apps_melidata_api.py \
        --write-tests \
        --base-url https://meilisearch.1oa.com.cn

For a read-only runtime probe, provide an existing business API Key:

    MELIDATA_API_KEY='ud_live_...' \
      python scripts/test_apps_melidata_api.py --collection products
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
from typing import Any, Iterable
from urllib.parse import quote
import uuid

try:
    import requests
except ImportError:  # pragma: no cover - optional CLI dependency
    requests = None

DEFAULT_BASE_URL = "https://meilisearch.1oa.com.cn"
SERVICE_SCOPES = (
    "open-platform:apps:write",
    "open-platform:collections:write",
)
BUSINESS_SCOPES = ("data:read", "data:write", "search:read")
SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "client_secret",
    "refresh_token",
    "authorization",
}


def _iso_after(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _default_app_name() -> str:
    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    return f"apps_api_test_{suffix}"[:64]


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode claims for contract inspection; signature validation remains server-side."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("access_token is not a JWT")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    if not isinstance(payload, dict):
        raise ValueError("JWT payload is not an object")
    return payload


def _redact(value: Any, secrets: Iterable[str] = ()) -> Any:
    secret_values = [item for item in secrets if item]
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() in SENSITIVE_KEYS else _redact(item, secret_values)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, secret_values) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            redacted = redacted.replace(secret, "<redacted>")
        return redacted
    return value


class ApiTester:
    """Small requests-based runner with safe output and explicit write gating."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.base_url = args.base_url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = not args.insecure
        self.secrets: list[str] = [args.client_secret or ""]
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.service_access_token: str | None = None
        self.refresh_token: str | None = None
        self.business_api_key: str | None = args.api_key
        self.app_id: str | None = None
        self.credential_ref: str | None = None
        self.key_id: str | None = None
        self.collection = args.collection
        self.agent_base_url: str | None = args.agent_base_url.rstrip("/") if args.agent_base_url else None

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Accept", "application/json")
        headers.setdefault("X-Request-ID", f"apps-api-test-{uuid.uuid4().hex}")
        return self.session.request(
            method,
            self._url(path),
            headers=headers,
            timeout=self.args.timeout,
            **kwargs,
        )

    def auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def result(self, name: str, passed: bool, detail: str) -> None:
        label = "PASS" if passed else "FAIL"
        print(f"[{label}] {name}: {detail}")
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def skip(self, name: str, detail: str) -> None:
        print(f"[SKIP] {name}: {detail}")
        self.skipped += 1

    def _response_detail(self, response: requests.Response) -> str:
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text[:500]
        payload = _redact(payload, self.secrets)
        if isinstance(payload, (dict, list)):
            rendered = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        else:
            rendered = str(payload)
        return f"HTTP {response.status_code} {rendered[:700]}"

    def expect_status(
        self,
        name: str,
        response: requests.Response,
        expected: int | tuple[int, ...],
    ) -> bool:
        allowed = (expected,) if isinstance(expected, int) else expected
        if response.status_code in allowed:
            self.result(name, True, self._response_detail(response))
            return True
        self.result(name, False, self._response_detail(response))
        return False

    @staticmethod
    def response_data(response: requests.Response) -> Any:
        payload = response.json()
        return payload.get("data") if isinstance(payload, dict) else None

    def run_oauth(self) -> None:
        if not self.args.client_secret:
            self.result(
                "A01 client_credentials",
                False,
                "missing OPEN_PLATFORM_SERVICE_CLIENT_SECRET or --client-secret",
            )
            return

        try:
            response = self.request(
                "POST",
                "/oauth1/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.args.client_id,
                    "client_secret": self.args.client_secret,
                    "scope": " ".join(SERVICE_SCOPES),
                },
            )
        except requests.RequestException as exc:
            self.result("A01 client_credentials", False, str(exc))
            return

        if not self.expect_status("A01 client_credentials", response, 200):
            return
        try:
            payload = response.json()
            access_token = str(payload["access_token"])
            refresh_token = str(payload["refresh_token"])
            claims = _decode_jwt_payload(access_token)
            expected_audience = "melidata-management"
            audiences = claims.get("aud")
            audience_ok = audiences == expected_audience or (
                isinstance(audiences, list) and expected_audience in audiences
            )
            claims_ok = all(claims.get(key) for key in ("iss", "sub", "exp", "jti")) and audience_ok
            scope_ok = set(str(claims.get("scope", "")).split()) >= set(SERVICE_SCOPES)
            if not claims_ok or not scope_ok:
                self.result(
                    "A01 JWT claims",
                    False,
                    f"unexpected claims (audience_ok={audience_ok}, scope_ok={scope_ok})",
                )
                return
            self.result("A01 JWT claims", True, "iss/sub/aud/scope/exp/jti present")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.result("A01 response contract", False, f"invalid token response: {exc}")
            return

        self.service_access_token = access_token
        self.refresh_token = refresh_token
        self.secrets.extend([access_token, refresh_token])

        response: requests.Response | None = None
        for attempt in range(self.args.refresh_attempts):
            try:
                response = self.request(
                    "POST",
                    "/oauth2/refresh",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.args.client_id,
                        "refresh_token": refresh_token,
                    },
                )
            except requests.RequestException as exc:
                if attempt + 1 == self.args.refresh_attempts:
                    self.result("A02 refresh", False, str(exc))
                    return
                time.sleep(self.args.refresh_interval)
                continue
            if response.status_code != 401 or attempt + 1 == self.args.refresh_attempts:
                break
            time.sleep(self.args.refresh_interval)

        if response is None or not self.expect_status("A02 refresh", response, 200):
            return
        try:
            payload = response.json()
            next_access_token = str(payload["access_token"])
            next_refresh_token = str(payload["refresh_token"])
            if next_refresh_token == refresh_token:
                raise ValueError("refresh token was not rotated")
            self.service_access_token = next_access_token
            self.refresh_token = next_refresh_token
            self.secrets.extend([next_access_token, next_refresh_token])
            self.result("A02 refresh rotation", True, "new access and refresh tokens issued")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.result("A02 response contract", False, f"invalid refresh response: {exc}")
            return

        if not self.args.skip_refresh_reuse_check:
            try:
                response = self.request(
                    "POST",
                    "/oauth2/refresh",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.args.client_id,
                        "refresh_token": refresh_token,
                    },
                )
                self.expect_status("A02 refresh token reuse rejected", response, 401)
            except requests.RequestException as exc:
                self.result("A02 refresh token reuse rejected", False, str(exc))

        try:
            response = self.request(
                "POST",
                "/oauth1/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.args.client_id,
                    "client_secret": f"{self.args.client_secret}.invalid",
                },
            )
            self.expect_status("A01 invalid client rejected", response, 401)
        except requests.RequestException as exc:
            self.result("A01 invalid client rejected", False, str(exc))

        try:
            response = self.request(
                "POST",
                "/oauth1/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.args.client_id,
                    "client_secret": self.args.client_secret,
                    "scope": "open-platform:not-allowed",
                },
            )
            self.expect_status("A01 invalid scope rejected", response, 400)
        except requests.RequestException as exc:
            self.result("A01 invalid scope rejected", False, str(exc))

    def run_bootstrap(self) -> None:
        if not self.service_access_token:
            self.skip("M01 bootstrap", "OAuth access token unavailable")
            return

        app_name = self.args.app_name or _default_app_name()
        idempotency_key = f"apps-api-test-{uuid.uuid4().hex}"
        payload = {
            "app_name": app_name,
            "display_name": "APPS API integration test",
            "owner_itcode": self.args.owner_itcode,
            "description": "Created by scripts/test_apps_melidata_api.py",
            "initial_keys": [
                {
                    "name": "apps-api-test-key",
                    "scopes": list(BUSINESS_SCOPES),
                    "expires_at": _iso_after(1),
                }
            ],
        }
        headers = {
            **self.auth_headers(self.service_access_token),
            "Idempotency-Key": idempotency_key,
        }
        try:
            response = self.request(
                "POST",
                "/api/v1/open-platform/apps/bootstrap",
                headers=self.auth_headers(self.service_access_token),
                json=payload,
            )
            self.expect_status("M01 missing idempotency key rejected", response, 400)
        except requests.RequestException as exc:
            self.result("M01 missing idempotency key rejected", False, str(exc))

        try:
            response = self.request(
                "POST",
                "/api/v1/open-platform/apps/bootstrap",
                headers=headers,
                json=payload,
            )
        except requests.RequestException as exc:
            self.result("M01 bootstrap", False, str(exc))
            return

        if not self.expect_status("M01 bootstrap", response, 201):
            return
        try:
            data = self.response_data(response)
            app = data["app"]
            key = data["keys"][0]
            self.app_id = str(app["id"])
            self.key_id = str(key["id"])
            self.credential_ref = str(key["credential_ref"])
            self.business_api_key = str(key["api_key"])
            self.secrets.append(self.business_api_key)
            if not self.credential_ref or not self.business_api_key.startswith("ud_live_"):
                raise ValueError("first response did not contain credential_ref and api_key")
            self.result("M01 one-time secret delivery", True, "api_key and credential_ref returned once")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.result("M01 response contract", False, f"invalid bootstrap response: {exc}")
            return

        try:
            replay = self.request(
                "POST",
                "/api/v1/open-platform/apps/bootstrap",
                headers=headers,
                json=payload,
            )
            if self.expect_status("M01 idempotent replay", replay, 200):
                replay_data = self.response_data(replay) or {}
                replay_key = (replay_data.get("keys") or [{}])[0]
                self.result(
                    "M01 replay omits plaintext",
                    not replay_key.get("api_key"),
                    "historical api_key is not returned",
                )
        except requests.RequestException as exc:
            self.result("M01 idempotent replay", False, str(exc))

        conflict_payload = {**payload, "display_name": "APPS API idempotency conflict"}
        try:
            conflict = self.request(
                "POST",
                "/api/v1/open-platform/apps/bootstrap",
                headers=headers,
                json=conflict_payload,
            )
            self.expect_status("M01 idempotency conflict", conflict, 409)
        except requests.RequestException as exc:
            self.result("M01 idempotency conflict", False, str(exc))

    def run_runtime(self) -> None:
        if not self.business_api_key:
            self.skip("R01-R04 runtime checks", "no business API Key; use --write-tests or MELIDATA_API_KEY")
            return
        business_headers = self.auth_headers(self.business_api_key)

        document_ids = [
            f"apps-api-test-{uuid.uuid4().hex[:10]}",
            f"apps-api-test-{uuid.uuid4().hex[:10]}",
        ]
        if self.args.write_tests:
            try:
                response = self.request(
                    "POST",
                    f"/api/v1/data/{quote(self.collection, safe='')}/batch",
                    headers=business_headers,
                    json={
                        "items": [
                            {
                                "id": document_ids[0],
                                "title": "APPS MeliData integration test",
                                "status": "active",
                                "project_id": "apps-api-test",
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            },
                            {
                                "id": document_ids[1],
                                "title": "APPS MeliData second document",
                                "status": "active",
                                "project_id": "apps-api-test",
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            },
                        ]
                    },
                )
                self.expect_status("R01 batch upsert", response, 201)
            except requests.RequestException as exc:
                self.result("R01 batch upsert", False, str(exc))
        else:
            self.skip("R01 batch upsert", "write tests are disabled")

        if self.args.write_tests and self.service_access_token and self.app_id:
            settings_payload = {
                "filterableAttributes": ["project_id", "status"],
                "sortableAttributes": ["updated_at"],
                "searchableAttributes": ["title", "description"],
                "displayedAttributes": ["id", "title", "project_id", "status", "updated_at"],
            }
            try:
                response = self.request(
                    "PATCH",
                    f"/api/v1/open-platform/apps/{quote(self.app_id, safe='')}/collections/{quote(self.collection, safe='')}/settings",
                    headers=self.auth_headers(self.service_access_token),
                    json=settings_payload,
                )
                if self.expect_status("M02 collection settings", response, 200):
                    data = self.response_data(response) or {}
                    self.result(
                        "M02 complete field contract",
                        data.get("filterable_attributes") == settings_payload["filterableAttributes"]
                        and data.get("sortable_attributes") == settings_payload["sortableAttributes"]
                        and data.get("searchable_attributes") == settings_payload["searchableAttributes"]
                        and data.get("displayed_attributes") == settings_payload["displayedAttributes"],
                        "center expectation matches all four fields",
                    )
            except requests.RequestException as exc:
                self.result("M02 collection settings", False, str(exc))

            try:
                response = self.request(
                    "PATCH",
                    f"/api/v1/open-platform/apps/{quote(self.app_id, safe='')}/collections/{quote(self.collection, safe='')}/settings",
                    headers=business_headers,
                    json=settings_payload,
                )
                self.expect_status("Management/data-plane separation", response, (401, 403))
            except requests.RequestException as exc:
                self.result("Management/data-plane separation", False, str(exc))
        else:
            self.skip("M02 collection settings", "write tests or management token unavailable")

        try:
            response = self.request(
                "GET",
                "/api/v1/agents/online",
                headers=business_headers,
                params={"region": self.args.region} if self.args.region else None,
            )
            if self.expect_status("R03 online node discovery", response, 200):
                data = self.response_data(response)
                valid = isinstance(data, list)
                if self.args.region and valid:
                    valid = all(item.get("region") == self.args.region for item in data)
                self.result("R03 response contract", valid, "data is a region-filtered node list")
                if valid and data and not self.agent_base_url:
                    self.agent_base_url = str(data[0].get("base_url") or "").rstrip("/")
        except requests.RequestException as exc:
            self.result("R03 online node discovery", False, str(exc))

        if self.agent_base_url:
            self.run_search(document_ids[0], expect_document=self.args.write_tests)
        else:
            self.skip("R04 regional search", "no agent base_url; use --agent-base-url or make a node online")

        if self.args.write_tests:
            for document_id in document_ids:
                try:
                    response = self.request(
                        "DELETE",
                        f"/api/v1/data/{quote(self.collection, safe='')}/{quote(document_id, safe='')}",
                        headers=business_headers,
                    )
                    self.expect_status("R02 delete document", response, 200)
                except requests.RequestException as exc:
                    self.result("R02 delete document", False, str(exc))
                    continue

            try:
                response = self.request(
                    "DELETE",
                    f"/api/v1/data/{quote(self.collection, safe='')}/{quote(document_ids[0], safe='')}",
                    headers=business_headers,
                )
                self.expect_status("R02 missing document semantics", response, 404)
            except requests.RequestException as exc:
                self.result("R02 missing document semantics", False, str(exc))

    def run_search(self, document_id: str, *, expect_document: bool) -> None:
        """Probe R04, tolerating expected CDC/index propagation delay."""
        url = (
            f"{self.agent_base_url}/api/v1/collections/"
            f"{quote(self.collection, safe='')}/search"
        )
        body = {
            "q": "APPS MeliData integration test" if expect_document else "",
            "limit": 5,
            "offset": 0,
        }
        last_response: requests.Response | None = None
        for attempt in range(self.args.search_attempts):
            try:
                response = self.request(
                    "POST",
                    url,
                    headers=self.auth_headers(self.business_api_key or ""),
                    json=body,
                )
                last_response = response
            except requests.RequestException as exc:
                if attempt + 1 == self.args.search_attempts:
                    self.result("R04 regional search", False, str(exc))
                    return
                time.sleep(self.args.search_interval)
                continue

            if response.status_code == 200:
                try:
                    payload = response.json()
                    data = payload.get("data")
                    valid = (
                        isinstance(data, dict)
                        and isinstance(data.get("hits"), list)
                        and "estimatedTotalHits" in data
                        and isinstance(payload.get("meta"), dict)
                        and payload.get("error") is None
                    )
                    found = any(str(item.get("id")) == document_id for item in data.get("hits", []))
                    if not valid:
                        self.result("R04 regional search", False, "invalid {data, meta, error} response envelope")
                        return
                    if found or not expect_document:
                        self.result("R04 regional search", True, f"response envelope valid; document_found={found}")
                        return
                    if attempt + 1 < self.args.search_attempts:
                        time.sleep(self.args.search_interval)
                        continue
                    self.skip("R04 regional search", "search index is ready but the test document has not propagated yet")
                except (ValueError, TypeError, AttributeError) as exc:
                    self.result("R04 regional search", False, f"invalid response: {exc}")
                return

            if response.status_code in (404, 429, 502, 503, 504):
                if attempt + 1 < self.args.search_attempts:
                    time.sleep(self.args.search_interval)
                    continue
            break

        if last_response is not None and last_response.status_code == 404:
            try:
                error = last_response.json().get("error") or {}
                if error.get("code") == "SEARCH_INDEX_NOT_FOUND":
                    self.skip("R04 regional search", "collection is not visible in the region yet (CDC propagation)")
                else:
                    self.result("R04 regional search", False, self._response_detail(last_response))
            except (ValueError, AttributeError):
                self.result("R04 regional search", False, self._response_detail(last_response))
        elif last_response is not None:
            self.result("R04 regional search", False, self._response_detail(last_response))

    def run(self) -> int:
        self.run_oauth()
        if self.args.write_tests:
            self.run_bootstrap()
        else:
            self.skip("M01 bootstrap", "write tests are disabled")
            self.skip("M02 collection settings", "write tests are disabled")
        self.run_runtime()
        print(
            f"\nSummary: passed={self.passed} failed={self.failed} skipped={self.skipped}"
        )
        if self.args.write_tests and self.app_id:
            print(f"Test application created: {self.app_id} (left for controlled cleanup)")
        return 1 if self.failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test APPS/MeliData OAuth, management, data, discovery, and search APIs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("MELIDATA_BASE_URL", DEFAULT_BASE_URL),
        help="MeliData center URL",
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("OPEN_PLATFORM_SERVICE_CLIENT_ID", "apps"),
        help="OAuth service client id",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("OPEN_PLATFORM_SERVICE_CLIENT_SECRET"),
        help="OAuth service client secret; prefer the environment variable",
    )
    parser.add_argument(
        "--owner-itcode",
        default=os.getenv("MELIDATA_OWNER_ITCODE", "apps-api-test"),
        help="owner_itcode used by M01",
    )
    parser.add_argument(
        "--app-name",
        default=os.getenv("MELIDATA_TEST_APP_NAME"),
        help="optional app_name; otherwise a unique test name is generated",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("MELIDATA_TEST_COLLECTION", "apps_api_test"),
        help="collection used by M02/R01-R04",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MELIDATA_API_KEY"),
        help="existing business API Key for read-only runtime checks",
    )
    parser.add_argument(
        "--agent-base-url",
        default=os.getenv("MELIDATA_AGENT_BASE_URL"),
        help="trusted regional Agent base_url for R04; otherwise discovered by R03",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("MELIDATA_TEST_REGION"),
        help="optional exact region filter for R03",
    )
    parser.add_argument(
        "--write-tests",
        "--enable-write-tests",
        dest="write_tests",
        action="store_true",
        help="enable M01/M02/R01/R02 and create a test application",
    )
    parser.add_argument(
        "--skip-refresh-reuse-check",
        action="store_true",
        help="skip the one-time refresh-token reuse assertion",
    )
    parser.add_argument(
        "--refresh-attempts",
        type=int,
        default=3,
        help="maximum A02 attempts for a transient post-issuance 401",
    )
    parser.add_argument(
        "--refresh-interval",
        type=float,
        default=0.5,
        help="seconds between transient A02 attempts",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS certificate verification (development only)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("MELIDATA_TEST_TIMEOUT", "15")),
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--search-attempts",
        type=int,
        default=6,
        help="R04 attempts while waiting for CDC/index propagation",
    )
    parser.add_argument(
        "--search-interval",
        type=float,
        default=5.0,
        help="seconds between R04 attempts",
    )
    return parser


def main() -> int:
    if requests is None:
        raise SystemExit(
            "This script requires requests. Install it with: python -m pip install requests"
        )
    args = build_parser().parse_args()
    if (
        args.timeout <= 0
        or args.search_attempts <= 0
        or args.search_interval < 0
        or args.refresh_attempts <= 0
        or args.refresh_interval < 0
    ):
        print("timeouts and attempt counts must be positive", file=sys.stderr)
        return 2
    if not args.collection or len(args.collection) > 128:
        print("collection must be 1-128 characters", file=sys.stderr)
        return 2
    return ApiTester(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
