import os
import time
import json
import base64
from typing import Optional
import html
import re

import requests
from flask import Flask, request, jsonify, render_template

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.auth.crypt import RSASigner
from google.auth import jwt as google_jwt

app = Flask(__name__)

API_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]

# REQUIRED
ISSUER_ID = os.environ.get("ISSUER_ID")
if not ISSUER_ID:
    raise RuntimeError("ISSUER_ID env var is required")

# IMPORTANT: your mounted file from the screenshot
MOUNTED_KEYFILE_PATH = "/key.json/GOOGLE_APPLICATION_CREDENTIALS"

#SOLVE TEMPLATE ISSUES
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static",
)


def resolve_keyfile_path() -> str:
    """
    MUST read JSON key from mounted volume file.
    Priority:
      1) GOOGLE_APPLICATION_CREDENTIALS env var (if it points to a real file)
      2) The mounted volume path from your Cloud Run volume config
    """
    p = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if p and os.path.isfile(p):
        return p

    if os.path.isfile(MOUNTED_KEYFILE_PATH):
        return MOUNTED_KEYFILE_PATH

    raise RuntimeError(
        "Service account keyfile not found. "
        "Expected GOOGLE_APPLICATION_CREDENTIALS to point to a mounted file, "
        f"or file present at {MOUNTED_KEYFILE_PATH}."
    )


def get_access_token() -> str:
    keyfile = resolve_keyfile_path()
    creds = service_account.Credentials.from_service_account_file(keyfile, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def create_generic_object(
    token: str,
    class_id: str,
    object_id: str,
    business_name: str,
    client_name: str,
    img_base: str,
    stamp_n: int,
    total: int,
) -> None:
    body = {
        "id": object_id,
        "classId": class_id,
        "state": "ACTIVE",
        "cardTitle": {"defaultValue": {"language": "en-US", "value": business_name}},
        "header": {"defaultValue": {"language": "en-US", "value": "Loyalty Card"}},
        "subheader": {"defaultValue": {"language": "en-US", "value": client_name}},
        "heroImage": {"sourceUri": {"uri": f"{img_base}/stamps_{stamp_n}.png"}},
        "textModulesData": [
            {"header": "Stamps to next reward", "body": f"{stamp_n} / {total}"},
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

    # If already exists -> patch instead (so /issue can be called repeatedly)
    if r.status_code in (200, 201):
        return

    if r.status_code == 409:
        patch_body = {
            "header": {"defaultValue": {"language": "en-US", "value": "Loyalty Card"}},
            "heroImage": {"sourceUri": {"uri": f"{img_base}/stamps_{stamp_n}.png"}},
            "subheader": {"defaultValue": {"language": "en-US", "value": client_name}},
            "textModulesData": [
                {"header": "Stamps to next reward", "body": f"{stamp_n} / {total}"},
                {"header": "Rewards collected", "body": "0"},
                {"header": "Reward", "body": "Free coffee"},
            ],
        }
        pr = requests.patch(
            f"{API_BASE}/genericObject/{object_id}",
            headers={"Authorization": f"Bearer {token}"},
            json=patch_body,
            timeout=30,
        )
        if pr.status_code in (200, 201):
            return
        raise RuntimeError(f"Patch object failed: {pr.status_code} {pr.text[:2000]}")

    raise RuntimeError(f"Create object failed: {r.status_code} {r.text[:2000]}")


def generate_save_url(object_id: str, class_id: str) -> str:
    keyfile = resolve_keyfile_path()
    with open(keyfile, "r", encoding="utf-8") as f:
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
                {"id": object_id, "classId": class_id, "state": "ACTIVE"}
            ]
        },
    }

    signer = RSASigner.from_service_account_info(sa)
    signed = google_jwt.encode(signer, claims)
    if isinstance(signed, bytes):
        signed = signed.decode("utf-8")

    return f"https://pay.google.com/gp/v/save/{signed}"

def get_generic_object(token: str, object_id: str) -> dict:
    r = requests.get(
        f"{API_BASE}/genericObject/{object_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Get object failed: {r.status_code} {r.text[:2000]}")
    return r.json()


def patch_generic_object(token: str, object_id: str, patch_body: dict) -> dict:
    r = requests.patch(
        f"{API_BASE}/genericObject/{object_id}",
        headers={"Authorization": f"Bearer {token}"},
        json=patch_body,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Patch object failed: {r.status_code} {r.text[:2000]}")
    return r.json()


def parse_current_stamps_from_object(obj: dict) -> int:
    """
    Your object uses:
      header: "Stamps to next reward"
      body:   "<n> / <total>"
    If missing, returns 0.
    """
    tmd = obj.get("textModulesData", []) or []
    for m in tmd:
        if (m.get("header") or "").strip().lower() == "stamps to next reward":
            body = (m.get("body") or "").strip()
            match = re.search(r"(\d+)\s*/\s*(\d+)", body)
            if match:
                return int(match.group(1))
    return 0


def build_award_stamp_patch(img_base: str, new_stamp_n: int, total: int) -> dict:
    """
    Keep EXACT module headers you already use in create_generic_object().
    Only change heroImage and the stamp counter text.
    """
    return {
        "heroImage": {"sourceUri": {"uri": f"{img_base}/stamps_{new_stamp_n}.png"}},
        "textModulesData": [
            {"header": "Stamps to next reward", "body": f"{new_stamp_n} / {total}"},
            {"header": "Rewards collected", "body": "0"},
            {"header": "Reward", "body": "Free coffee"},
        ],
    }

@app.get("/")
def home():
    return """
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>SparkCards</title></head>
  <body style="font-family:sans-serif;max-width:720px;margin:40px auto;">
    <h1>✅ SparkCards is running</h1>
    <p>Try issuing a pass:</p>
    <pre>POST /issue</pre>
    <p>Health: <a href="/health">/health</a></p>
  </body>
</html>
""".strip()


@app.get("/health")
def health():
    return jsonify(ok=True)


@app.post("/issue")
def issue():
    """
    Creates/patches a GenericObject under a class, then returns a Save URL.
    Accepts JSON:
      - client_name (default: "Gonzalo")
      - stamp_n (default: 0)
      - total (default: env TOTAL or 8)
      - business_name (default: env BUSINESS_NAME or "Coffee Madrid")
      - img_base (default: env IMG_BASE or "https://pl4int3xt.github.io")
      - class_id (default: f"{ISSUER_ID}.coffee_madrid_loyalty_v2")
      - object_id (optional; if not provided, auto-generated)
    """
    data = request.get_json(silent=True) or {}

    client_name = (data.get("client_name") or os.environ.get("CLIENT_NAME") or "Gonzalo").strip()
    stamp_n = int(data.get("stamp_n") or os.environ.get("STAMP_N") or 0)

    business_name = (data.get("business_name") or os.environ.get("BUSINESS_NAME") or "Coffee Madrid").strip()
    img_base = (data.get("img_base") or os.environ.get("IMG_BASE") or "https://pl4int3xt.github.io").strip()
    total = int(data.get("total") or os.environ.get("TOTAL") or 8)

    class_id = (data.get("class_id") or f"{ISSUER_ID}.coffee_madrid_loyalty_v2").strip()

    object_id = (data.get("object_id") or "").strip()

    if object_id:
        # Login manda deviceId (sin punto). Wallet necesita ISSUER_ID.something
        if "." not in object_id:
            object_id = f"{ISSUER_ID}.user_{object_id}"
    else:
        safe_name = client_name.lower().replace(" ", "_")
        object_id = f"{ISSUER_ID}.cmv2_{safe_name}_{int(time.time())}"
    

    try:
        token = get_access_token()
        create_generic_object(
            token=token,
            class_id=class_id,
            object_id=object_id,
            business_name=business_name,
            client_name=client_name,
            img_base=img_base,
            stamp_n=stamp_n,
            total=total,
        )
        save_url = generate_save_url(object_id, class_id)
        return jsonify(
            ok=True,
            class_id=class_id,
            object_id=object_id,
            save_url=save_url,
            keyfile_used=resolve_keyfile_path(),
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500




@app.get("/login")
def login_get():
    return render_template("login.html")

@app.post("/award_stamp")
def award_stamp():
    """
    Adds exactly +1 stamp by:
      1) GET current object
      2) parse current stamp count from "Stamps to next reward"
      3) PATCH heroImage + that module (capped at total)

    JSON:
      - object_id (required)  OR passId (alias)
      - total (optional; defaults to env TOTAL or 8)
      - img_base (optional; defaults to env IMG_BASE or https://pl4int3xt.github.io)
    """
    data = request.get_json(silent=True) or {}

    object_id = (data.get("object_id") or data.get("passId") or "").strip()
    if not object_id:
        return jsonify(ok=False, error="missing object_id (or passId)"), 400

    img_base = (data.get("img_base") or os.environ.get("IMG_BASE") or "https://pl4int3xt.github.io").strip()
    total = int(data.get("total") or os.environ.get("TOTAL") or 8)

    try:
        token = get_access_token()

        obj = get_generic_object(token, object_id)
        current = parse_current_stamps_from_object(obj)
        new_stamp_n = min(current + 1, total)

        patch_body = build_award_stamp_patch(img_base=img_base, new_stamp_n=new_stamp_n, total=total)
        patched = patch_generic_object(token, object_id, patch_body)

        return jsonify(
            ok=True,
            object_id=object_id,
            previous=current,
            new_stamp_n=new_stamp_n,
            total=total,
            hero_image=f"{img_base}/stamps_{new_stamp_n}.png",
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

