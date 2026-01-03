# issue.py
"""
Issue Google Wallet passes from your Cloud Run backend.

Design goals:
- NO service-account JSON key in GitHub
- Uses Cloud Run's service account (Application Default Credentials)
- Signs the "Save to Google Wallet" JWT via IAMCredentials signJwt
- Creates a Wallet Object (Generic by default) and returns a save URL

Prereqs (env vars):
- ISSUER_ID            e.g. "1234567890123456789"
- CLASS_ID             e.g. "1234567890123456789.sparkcards_class"
- SIGNER_SA_EMAIL      e.g. "wallet-backend@your-project.iam.gserviceaccount.com"
Optional:
- OBJECT_TYPE          "generic" (default) or "loyalty"
- APP_TITLE            e.g. "SparkCards" (default)
"""

from __future__ import annotations

import json
import time
import secrets
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest

WALLET_OBJECTS_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
IAM_CREDENTIALS_BASE = "https://iamcredentials.googleapis.com/v1"


@dataclass
class IssueResult:
    object_id: str
    save_url: str


class IssueError(RuntimeError):
    pass


def _get_env(name: str, default: Optional[str] = None) -> str:
    import os

    val = os.getenv(name, default)
    if not val:
        raise IssueError(f"Missing required env var: {name}")
    return val


def _get_access_token() -> str:
    # Cloud Run provides ADC automatically when the service runs as a service account.
    creds, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(GoogleAuthRequest())
    return creds.token


def _wallet_headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _post_json(url: str, access_token: str, payload: Dict[str, Any], timeout: int = 20) -> requests.Response:
    return requests.post(url, headers=_wallet_headers(access_token), data=json.dumps(payload), timeout=timeout)


def _generate_object_id(issuer_id: str, prefix: str = "u") -> str:
    # Object IDs must be: "<issuerId>.<uniqueSuffix>"
    suffix = f"{prefix}_{int(time.time())}_{secrets.token_hex(6)}"
    return f"{issuer_id}.{suffix}"


def _create_generic_object(access_token: str, object_id: str, class_id: str, user_name: str, app_title: str) -> None:
    url = f"{WALLET_OBJECTS_BASE}/genericObject"
    payload = {
        "id": object_id,
        "classId": class_id,
        "state": "ACTIVE",
        "cardTitle": {"defaultValue": {"language": "en", "value": app_title}},
        "header": {"defaultValue": {"language": "en", "value": user_name}},
    }
    r = _post_json(url, access_token, payload)
    if r.status_code not in (200, 201, 409):
        raise IssueError(f"genericObject create failed {r.status_code}: {r.text}")


def _create_loyalty_object(access_token: str, object_id: str, class_id: str, user_name: str, app_title: str) -> None:
    url = f"{WALLET_OBJECTS_BASE}/loyaltyObject"
    payload = {
        "id": object_id,
        "classId": class_id,
        "state": "ACTIVE",
        "accountName": user_name,
        "programName": app_title,
    }
    r = _post_json(url, access_token, payload)
    if r.status_code not in (200, 201, 409):
        raise IssueError(f"loyaltyObject create failed {r.status_code}: {r.text}")


def _sign_jwt_with_iam(access_token: str, signer_sa_email: str, jwt_claims: Dict[str, Any]) -> str:
    url = f"{IAM_CREDENTIALS_BASE}/projects/-/serviceAccounts/{signer_sa_email}:signJwt"
    body = {"payload": json.dumps(jwt_claims)}
    r = requests.post(url, headers=_wallet_headers(access_token), data=json.dumps(body), timeout=20)
    if r.status_code != 200:
        raise IssueError(f"IAM signJwt failed {r.status_code}: {r.text}")
    return r.json()["signedJwt"]


def issue_pass(user_name: str, object_id: Optional[str] = None) -> IssueResult:
    issuer_id = _get_env("ISSUER_ID")
    class_id = _get_env("CLASS_ID")
    signer_sa_email = _get_env("SIGNER_SA_EMAIL")
    object_type = _get_env("OBJECT_TYPE", "generic").strip().lower()
    app_title = _get_env("APP_TITLE", "SparkCards")

    access_token = _get_access_token()

    if object_id is None:
        object_id = _generate_object_id(issuer_id, prefix="user")

    if object_type == "loyalty":
        _create_loyalty_object(access_token, object_id, class_id, user_name, app_title)
        payload_key = "loyaltyObjects"
    else:
        _create_generic_object(access_token, object_id, class_id, user_name, app_title)
        payload_key = "genericObjects"

    now = int(time.time())
    jwt_claims = {
        "iss": signer_sa_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": now,
        "payload": {payload_key: [{"id": object_id}]},
    }

    signed_jwt = _sign_jwt_with_iam(access_token, signer_sa_email, jwt_claims)
    save_url = f"https://pay.google.com/gp/v/save/{signed_jwt}"

    return IssueResult(object_id=object_id, save_url=save_url)

