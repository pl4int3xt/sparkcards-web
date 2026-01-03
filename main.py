from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def health():
    return "SparkCards backend running"

@app.get("/login")
def login_form():
    return """
    <h1>SparkCards Login</h1>
    <form method="POST" action="/login">
      <input name="name" placeholder="Name" required />
      <input name="phone" placeholder="Phone" required />
      <input name="birthday" placeholder="YYYY-MM-DD" required />
      <button type="submit">Create pass</button>
    </form>
    """

@app.post("/login")
def login_submit():
    name = request.form.get("name") or (request.json or {}).get("name")
    phone = request.form.get("phone") or (request.json or {}).get("phone")
    birthday = request.form.get("birthday") or (request.json or {}).get("birthday")
    return jsonify({"ok": True, "received": {"name": name, "phone": phone, "birthday": birthday}})

@app.get("/addstamp")
def addstamp():
    pass_id = request.args.get("pass")
    return jsonify({"ok": False, "error": "not implemented", "pass": pass_id})

