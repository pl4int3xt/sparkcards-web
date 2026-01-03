# create_class_v2.py
import os
import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

KEYFILE = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
ISSUER_ID = os.environ["ISSUER_ID"]  # numeric

API_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]

# ✅ NEW CLASS NAME (change only this if you want another)
CLASS_SUFFIX = "coffee_madrid_loyalty_v2"
CLASS_ID = f"{ISSUER_ID}.{CLASS_SUFFIX}"

BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "Coffee Madrid")


def get_token():
    creds = service_account.Credentials.from_service_account_file(KEYFILE, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def main():
    token = get_token()

    body = {
        "id": CLASS_ID,
        "cardTitle": {
            "defaultValue": {"language": "en-US", "value": BUSINESS_NAME}
        },
        # optional styling
        "hexBackgroundColor": "#F2F2F2",
    }

    r = requests.post(
        f"{API_BASE}/genericClass",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=30,
    )

    print("HTTP:", r.status_code)
    print(r.text[:2000])

    if r.status_code in (200, 201):
        print("[+] Created class:", CLASS_ID)
    elif r.status_code == 409:
        print("[i] Class already exists:", CLASS_ID)


if __name__ == "__main__":
    main()

