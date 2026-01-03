import os
import time
import json
import requests

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.auth.crypt import RSASigner
from google.auth import jwt as google_jwt

KEYFILE = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
ISSUER_ID = os.environ["ISSUER_ID"]

API_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]

CLASS_ID = f"{ISSUER_ID}.coffee_madrid_loyalty_v2"

BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Coffee Madrid")
CLIENT_NAME = os.environ.get("CLIENT_NAME", "Gonzalo")

IMG_BASE = "https://pl4int3xt.github.io"
STAMP_N = int(os.environ.get("STAMP_N", "0"))
TOTAL = int(os.environ.get("TOTAL", "8"))

OBJECT_ID = f"{ISSUER_ID}.cmv2_{CLIENT_NAME.lower().replace(' ', '_')}_{int(time.time())}"


def get_access_token():
    creds = service_account.Credentials.from_service_account_file(KEYFILE, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def create_object(token):
    body = {
        "id": OBJECT_ID,
        "classId": CLASS_ID,
        "state": "ACTIVE",

        # ✅ REQUIRED on GenericObject too
        "cardTitle": {
            "defaultValue": {"language": "en-US", "value": BUSINESS_NAME}
        },

        # client name shown prominently
        "header": {"defaultValue": {"language": "en-US", "value": ""}},  # or remove header
        "subheader": {"defaultValue": {"language": "en-US", "value": CLIENT_NAME}},


        # stamp grid
        "heroImage": {"sourceUri": {"uri": f"{IMG_BASE}/stamps_{STAMP_N}.png"}},

        # no barcode => no QR
        "textModulesData": [
            {"header": "Stamps to next reward", "body": f"{STAMP_N} / {TOTAL}"},
            {"header": "Rewards collected", "body": "0"},
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
        print("Create object failed:", r.status_code, r.text[:2000])
        raise SystemExit(1)

    print("[+] Created object:", OBJECT_ID)


def generate_save_url():
    with open(KEYFILE, "r", encoding="utf-8") as f:
        sa = json.load(f)

    now = int(time.time())
    claims = {
        "iss": sa["client_email"],
        "aud": "google",
        "typ": "savetowallet",
        "iat": now,
        "exp": now + 3600,
        "origins": [],
        "payload": {
            "genericObjects": [
                {"id": OBJECT_ID, "classId": CLASS_ID, "state": "ACTIVE"}
            ]
        },
    }

    signer = RSASigner.from_service_account_info(sa)
    signed = google_jwt.encode(signer, claims)
    if isinstance(signed, bytes):
        signed = signed.decode("utf-8")

    return f"https://pay.google.com/gp/v/save/{signed}"


def main():
    token = get_access_token()
    create_object(token)
    print("\n[+] Save link (open on Android in Chrome):")
    print(generate_save_url())


if __name__ == "__main__":
    main()

