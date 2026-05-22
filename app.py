from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import os
import random
import string
from datetime import datetime
import requests
import psycopg2

from resend import Resend

# ================= APP =================

app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200


# ================= ENV =================

DATABASE_URL = os.getenv("DATABASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

if not DATABASE_URL:
    raise Exception("DATABASE_URL not found")


# ================= DB =================

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')


# ================= RESEND =================

resend = Resend(RESEND_API_KEY)


def send_verification_email(to_email, code):
    if not RESEND_API_KEY:
        return

    try:
        resend.emails.send({
            "from": "AI Chat <onboarding@resend.dev>",
            "to": to_email,
            "subject": "AI Chat — код подтверждения",
            "html": f"""
            <div style="font-family:Arial;padding:30px">
                <h2>Ваш код подтверждения</h2>
                <div style="font-size:32px;font-weight:bold;color:#6d28d9">
                    {code}
                </div>
            </div>
            """
        })
    except Exception as e:
        print("EMAIL ERROR:", e)


# ================= REGISTER =================

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Все поля обязательны"}), 400

    code = ''.join(random.choices(string.digits, k=6))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            password TEXT,
            verification_code TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        INSERT INTO pending_users (email, password, verification_code, created_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (email)
        DO UPDATE SET verification_code = EXCLUDED.verification_code
    """, (email, password, code, datetime.now().strftime("%Y-%m-%d %H:%M")))

    conn.commit()
    conn.close()

    print("CODE:", code)

    send_verification_email(email, code)

    return jsonify({"success": True})


# ================= VERIFY =================

@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json()

    email = data.get("email", "").strip()
    code = data.get("code", "").strip()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            password TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        SELECT * FROM pending_users
        WHERE email = %s AND verification_code = %s
    """, (email, code))

    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Неверный код"}), 400

    cur.execute("""
        INSERT INTO users (email, password, created_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (email) DO NOTHING
    """, (row[1], row[2], row[4]))

    cur.execute("DELETE FROM pending_users WHERE email = %s", (email,))

    conn.commit()

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user_id = cur.fetchone()[0]

    conn.close()

    return jsonify({"success": True, "user_id": user_id})


# ================= LOGIN =================

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    email = data.get("email", "")
    password = data.get("password", "")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cur.fetchone()

    conn.close()

    if not user or user[2] != password:
        return jsonify({"error": "Неверные данные"}), 401

    return jsonify({
        "success": True,
        "user_id": user[0],
        "email": user[1]
    })


# ================= CHAT =================

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()

    user_id = data.get("user_id")
    message = data.get("message", "")

    if not user_id or not message:
        return jsonify({"error": "message required"}), 400

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": message}]
    }

    try:
        r = requests.post(GROQ_API_URL, headers=headers, json=payload)
        ai_text = r.json()["choices"][0]["message"]["content"]
    except:
        ai_text = "Ошибка AI"

    return jsonify({"reply": ai_text})


# ================= START =================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
