# app.py
import os
import sqlite3
import requests
from datetime import datetime
from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "app.db"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
FLASK_SECRET = os.getenv("FLASK_SECRET", "change_this_secret")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = FLASK_SECRET

# ---------------- DB helpers ----------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chats (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      god TEXT NOT NULL,
      role TEXT NOT NULL, -- 'user' or 'bot'
      message TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# ---------------- auth helpers ----------------
def create_user(email, password):
    db = get_db()
    cur = db.cursor()
    hashed = generate_password_hash(password)
    cur.execute("INSERT INTO users (email, password, created_at) VALUES (?, ?, ?)",
                (email, hashed, datetime.utcnow().isoformat()))
    db.commit()
    return cur.lastrowid

def find_user_by_email(email):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    return cur.fetchone()

def get_user_by_id(uid):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
    return cur.fetchone()

def login_user(user_row):
    session.clear()
    session["user_id"] = user_row["id"]
    session["email"] = user_row["email"]

def logout_user():
    session.clear()

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_user_by_id(uid)

# ---------------- routes ----------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pwd = request.form.get("password","")
        if not email or not pwd:
            return render_template("register.html", error="Email & password required.")
        if find_user_by_email(email):
            return render_template("register.html", error="Email already registered.")
        uid = create_user(email, pwd)
        user = get_user_by_id(uid)
        login_user(user)
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pwd = request.form.get("password","")
        user = find_user_by_email(email)
        if user and check_password_hash(user["password"], pwd):
            login_user(user)
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid credentials.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/")
def index():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    return render_template("index.html", email=user["email"])

# History endpoint (per user + god)
@app.route("/history")
def history():
    user = current_user()
    if not user:
        return jsonify({"error":"Unauthorized"}), 401
    god = request.args.get("god","Krishna")
    cur = get_db().cursor()
    cur.execute("SELECT role, message, created_at FROM chats WHERE user_id=? AND god=? ORDER BY id ASC",
                (user["id"], god))
    rows = cur.fetchall()
    data = [{"role": r["role"], "message": r["message"], "created_at": r["created_at"]} for r in rows]
    return jsonify({"history": data})

# send message -> save user msg, call OpenRouter, save bot reply
@app.route("/ask", methods=["POST"])
def ask():
    user = current_user()
    if not user:
        return jsonify({"error":"Unauthorized"}), 401

    payload = request.get_json(force=True)
    message = payload.get("message","").strip()
    god = payload.get("god","Krishna")
    if not message:
        return jsonify({"error":"Empty message"}), 400

    db = get_db()
    cur = db.cursor()
    # save user msg
    cur.execute("INSERT INTO chats (user_id, god, role, message, created_at) VALUES (?,?,?,?,?)",
                (user["id"], god, "user", message, datetime.utcnow().isoformat()))
    db.commit()

    # prepare system prompt
    system_prompt = f"You are {god}. Respond in Hinglish, kind and concise. Keep it respectful."

    bot_reply = ""
    if not OPENROUTER_API_KEY:
        bot_reply = "Server misconfigured: OPENROUTER_API_KEY missing."
    else:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            body = {
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {"role":"system","content": system_prompt},
                    {"role":"user","content": message}
                ],
                "temperature": 0.7,
                "max_tokens": 650
            }
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=body, timeout=30)
            resp.raise_for_status()
            j = resp.json()
            bot_reply = j.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not bot_reply:
                bot_reply = "क्षमा करें, उत्तर उपलब्ध नहीं है।"
        except Exception as e:
            bot_reply = f"API error: {str(e)}"

    # save bot reply
    cur.execute("INSERT INTO chats (user_id, god, role, message, created_at) VALUES (?,?,?,?,?)",
                (user["id"], god, "bot", bot_reply, datetime.utcnow().isoformat()))
    db.commit()

    return jsonify({"reply": bot_reply})

# status
@app.route("/status")
def status():
    user = current_user()
    return jsonify({"ok": True, "user": user["email"] if user else None})

# init DB
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)