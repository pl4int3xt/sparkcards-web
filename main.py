# main.py
from __future__ import annotations

import os
from flask import Flask, request, jsonify

from issue import issue_pass, IssueError

app = Flask(__name__)

# Simple health check
@app.get("/")
def health():
    return "SparkCards backend running", 200


# Issue a pass (simple for now: pass name in querystring)
# Example:
#   /issue?name=Gonzalo
@app.get("/issue")
def issue_get():
    name = (request.args.get("name") or "Test User").strip()
    try:
        res = issue_pass(user_name=name)
        return jsonify(
            {
                "ok": True,
                "objectId": res.object_id,
                "saveUrl": res.save_url,
            }
        ), 200
    except IssueError as e:
        # Known/expected config/API errors
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        # Unexpected errors
        return jsonify({"ok": False, "error": f"Unhandled error: {e}"}), 500

