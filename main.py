from __future__ import annotations

import os
import json
import time
import secrets
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests
from flask import Flask, request, jsonify
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest

app = Flask(__name__)

WALLET_OBJECTS_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
IAM_CREDENTIALS_BASE = "https://iamcredentials.googleapis.com/v1"


@dataclass
class IssueResult:
    object_id: str
    save_url: str


class IssueError(RuntimeError):
    pass


def _get_env(name: str, default: Optional[str] = None) -> str:
    val = os.getenv(name, default)
    if not val:
        raise IssueError(f"Missing required env var: {name}")
    return val


def _get_access_token() -> str:
    creds, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(GoogleAuthRequest())
    return creds.token


def _headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _post_json(url: str, access_token: str, payload: Dict[str, Any]) -> requests.Response:
    return requests.post(url, headers=_headers(access_token), data=json.dumps(payload), timeout=20)


def _generate_object_id(issuer_id: str) -> str:
    return f"{issuer_id}.user_{int(time.time())}_{secrets.token_hex(6)}"


def _create_generic_object(token, object_id, class_id, user_name, app_title):
    r = _post_json(
        f"{WALLET_OBJECTS_BASE}/genericObject",
        token,
        {
            "id": object_id,
            "classId": class_id,
            "state": "ACTIVE",
            "cardTitle": {"defaultValue": {"language": "en", "value": app_title}},
            "header": {"defaultValue": {"language": "en", "value": user_name}},
        },
    )
    if r.status_code not in (200, 201, 409):
        raise IssueError(f"Wallet error {r.status_code}: {r.text}")


def issue_pass(user_name: str) -> IssueResult:
    issuer_id = _get_env("ISSUER_ID")
    class_id = _get_env("CLASS_ID")
    signer_sa_email = _get_env("SIGNER_SA_EMAIL")
    app_title = _get_env("APP_TITLE", "SparkCards")

    token = _get_access_token()
    object_id = _generate_object_id(issuer_id)

    _create_generic_object(token, object_id, class_id, user_name, app_title)

    jwt_claims = {
        "iss": signer_sa_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "payload": {"genericObjects": [{"id": object_id}]},
    }

    r = requests.post(
        f"{IAM_CREDENTIALS_BASE}/projects/-/serviceAccounts/{signer_sa_email}:signJwt",
        headers=_headers(token),
        json={"payload": json.dumps(jwt_claims)},
        timeout=20,
    )
    if r.status_code != 200:
        raise IssueError(f"signJwt failed: {r.text}")

    save_url = f"https://pay.google.com/gp/v/save/{r.json()['signedJwt']}"
    return IssueResult(object_id, save_url)


@app.get("/")
def health():
    return "SparkCards backend running", 200


@app.get("/issue")
def issue():
    name = request.args.get("name", "Test User")
    res = issue_pass(name)
    return jsonify({"objectId": res.object_id, "saveUrl": res.save_url})

