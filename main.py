import json
import time
import requests
from flask import Flask, request, jsonify, redirect
from google.auth import default
from google.auth.transport.requests import Request
import os

app = Flask(__name__)

# TODO: set these
ISSUER_ID = "YOUR_ISSUER_ID"
CLASS_ID = f"{ISSUER_ID}.YOUR_CLASS_SUFFIX"   # e.g. 1234567890.sparkcards
SIGNER_SA_EMAIL = "wallet-backend@YOUR_PROJECT.iam.gserviceaccount.com"

WALLET_OBJECTS_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
IAM_SIGNJWT_URL = f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{SIGNER_SA_EMAIL}:signJwt"

BUILD_SHA = os.getenv("K_REVISION", "unknown")  # Cloud Run revision id

@app.get("/__version")
def version():
    return {
        "revision": BUILD_SHA
    }


def get_access_token():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def create_wallet_object(access_token: str, object_id: str, user_name: str):
    # Example for a generic pass object. Adjust to your object type if needed.
    url = f"{WALLET_OBJECTS_BASE}/genericObject"
    payload = {
        "id": object_id,
        "classId": CLASS_ID,
        "state": "ACTIVE",
        "cardTitle": {"defaultValue": {"language": "en", "value": "SparkCards"}},
        "header": {"defaultValue": {"language": "en", "value": user_name}},
        # Add your stamp fields / images later
    }

    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=20
    )

    # 409 means "already exists" — that's fine for re-issuing/testing
    if r.status_code not in (200, 201, 409):
        raise RuntimeError(f"Wallet object create failed {r.status_code}: {r.text}")


def sign_jwt_with_iam(access_token: str, jwt_payload: dict) -> str:
    # IAMCredentials signJwt expects the *unsigned JWT claims* as a JSON string
    body = {"payload": json.dumps(jwt_payload)}
    r = requests.post(
        IAM_SIGNJWT_URL,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=20
    )
    if r.status_code != 200:
        raise RuntimeError(f"signJwt failed {r.status_code}: {r.text}")
    return r.json()["signedJwt"]


@app.post("/issue")
def issue():
    data = request.json or request.form or {}
    name = data.get("name", "Test User")

    # Object IDs must be globally unique under issuer
    # e.g. "issuerId.objectSuffix"
    object_suffix = f"user_{int(time.time())}"
    object_id = f"{ISSUER_ID}.{object_suffix}"

    token = get_access_token()

    # 1) Create object
    create_wallet_object(token, object_id, name)

    # 2) Build JWT claims for "Save to Google Wallet"
    jwt_claims = {
        "iss": SIGNER_SA_EMAIL,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        # You can include one or more objects
        "payload": {
            "genericObjects": [
                {"id": object_id}
            ]
        }
    }

    signed_jwt = sign_jwt_with_iam(token, jwt_claims)
    save_url = f"https://pay.google.com/gp/v/save/{signed_jwt}"

    return jsonify({"ok": True, "objectId": object_id, "saveUrl": save_url})


@app.get("/issue")
def issue_get():
    name = request.args.get("name", "Test User")
    try:
        res = issue_pass(user_name=name)
        return jsonify({"ok": True, "objectId": res.object_id, "saveUrl": res.save_url})
    except IssueError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
