# main.py
import os
import time
import json
import requests

from flask import Flask, request, jsonify
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.auth.crypt import RSASigner
from google.auth import jwt as google_jwt

app = Flask(__name__)

# ---------------- CONFIG ----------------

KEYFILE = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]  # path to JSON
ISSUER_ID = os.environ["ISSUER_ID"]
CLASS_ID = os.environ["CLASS_ID"]

BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Coffee Madrid")
TOTAL = int(os.environ.get("TOTAL", "8"))
IMG_BASE = os.environ.get("IMG_BASE", "https://pl4int3xt.github.io")

API_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]

# ----------------------------------------


def get_access_token():
    creds = service_account.Credentials.from_service_account_file(
        KEYFILE, scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token


def create_object(token, client_name: str, stamp_n: int = 0):
    object_id = (
        f"{ISSUER_ID}.user_"
        f"{client_name.lower().replace(' ', '_')}_"
        f"{int(time.time())}"
    )

    body = {
        "id": object_id,
        "classId": CLASS_ID,
        "state": "ACTIVE",

        "cardTitle": {
            "defaultValue": {"language": "en-US", "value": BUSINESS_NAME}
        },
        "subheader": {
            "defaultValue": {"language": "en-US", "value": client_name}
        },

        "heroImage": {
            "sourceUri": {"uri": f"{IMG_BASE}/stamps_{stamp_n}.png"}
        },

        "textModulesData": [
            {"header": "Stamps", "body": f"{stamp_n} / {TOTAL}"},
            {"header": "Reward", "body": "Free coffee"},
        ],
    }

    r = requests.post(
        f"{API_BASE}/genericObject",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=30,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(f"Wallet create failed {r.status_code}: {r.text}")

    return object_id


def generate_save_url(object_id: str):
    with open(KEYFILE, "r", encoding="utf-8") as f:
        sa = json.load(f)

    now = int(time.time())
    claims = {
        "iss": sa["client_email"],
        "aud": "google",
        "typ": "savetowallet",
        "iat": now,
        "exp": now + 3600,
        "payload": {
            "genericObjects": [
                {"id": object_id, "classId": CLASS_ID}
            ]
        },
    }

    signer = RSASigner.from_service_account_info(sa)
    signed = google_jwt.encode(signer, claims)
    if isinstance(signed, bytes):
        signed = signed.decode("utf-8")

    return f"https://pay.google.com/gp/v/save/{signed}"


# ---------------- ROUTES ----------------

@app.get("/")
def health():
    return "SparkCards backend running", 200


@app.get("/issue")
def issue():
    name = request.args.get("name", "Test User")

    token = get_access_token()
    object_id = create_object(token, name)
    save_url = generate_save_url(object_id)

    return jsonify({
        "ok": True,
        "objectId": object_id,
        "saveUrl": save_url
    })


# ----------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

