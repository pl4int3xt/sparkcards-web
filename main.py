# main.py
from __future__ import annotations

import os
import logging
from flask import Flask, request, jsonify

# IMPORTANT: import the module, don't execute anything at import time.
# issue_pass only runs inside endpoints.
from issue import issue_pass, IssueError

app = Flask(__name__)

# Make logs visible in Cloud Run logs
logging.basicConfig(level=logging.INFO)


@app.get("/")
def health():
    return "SparkCards backend running", 200


@app.get("/issue")
def issue_get():
    """
    Browser/quick test:
      GET /issue?name=Gonzalo
    """
    name = request.args.get("name", "Test User")
    try:
        res = issue_pass(user_name=name)
        return jsonify({"ok": True, "objectId": res.object_id, "saveUrl": res.save_url})
    except IssueError as e:
        app.logger.exception("IssueError in /issue GET")
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        app.logger.exception("Unhandled error in /issue GET")
        return jsonify({"ok": False, "error": "internal_error", "detail": str(e)}), 500


@app.post("/issue")
def issue_post():
    """
    POST JSON:
      { "name": "Gonzalo" }
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "Test User")
    try:
        res = issue_pass(user_name=name)
        return jsonify({"ok": True, "objectId": res.object_id, "saveUrl": res.save_url})
    except IssueError as e:
        app.logger.exception("IssueError in /issue POST")
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        app.logger.exception("Unhandled error in /issue POST")
        return jsonify({"ok": False, "error": "internal_error", "detail": str(e)}), 500


# For local running only (Cloud Run uses gunicorn CMD)
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

