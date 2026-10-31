"""SKILLUP CAMPUS — serveur Flask (comptes, sessions, espace étudiant)."""
import os
import re
import sqlite3
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SKILLUP_DB", os.path.join(BASE_DIR, "skillup.db"))
UNIVERSITIES = {
    "Université de Parakou",
    "Université d'Abomey-Calavi",
    "Université Nationale d'Agriculture",
    "Autre établissement",
}
DEFAULT_SKILLS = [
    ("Microsoft Excel", 75),
    ("Communication professionnelle", 60),
    ("Suivi-évaluation", 35),
]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="/static")
def _load_secret_key():
    """SECRET_KEY depuis l'environnement, sinon une clé stable stockée à côté de la base.
    (Une clé aléatoire par processus casserait les sessions avec plusieurs workers.)"""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    key_path = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), ".secret_key")
    try:
        with open(key_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    new_key = os.urandom(32).hex()
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(new_key)
        return new_key
    except FileExistsError:
        with open(key_path) as f:
            return f.read().strip()


app.config["SECRET_KEY"] = _load_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            university TEXT,
            faculty TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 100)
        );
        """
    )
    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Connexion requise."), 401
        return view(*args, **kwargs)

    return wrapper


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute(
        "SELECT id, full_name, email, university, faculty FROM users WHERE id = ?", (uid,)
    ).fetchone()


def user_payload(row):
    skills = get_db().execute(
        "SELECT id, name, level FROM skills WHERE user_id = ? ORDER BY id", (row["id"],)
    ).fetchall()
    progress = round(sum(s["level"] for s in skills) / len(skills)) if skills else 0
    return {
        "id": row["id"],
        "fullName": row["full_name"],
        "email": row["email"],
        "university": row["university"],
        "faculty": row["faculty"],
        "skills": [{"id": s["id"], "name": s["name"], "level": s["level"]} for s in skills],
        "progress": progress,
    }


# ---------- Pages ----------
@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


# ---------- API ----------
@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    full_name = (data.get("fullname") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    university = (data.get("university") or "").strip()
    faculty = (data.get("faculty") or "").strip()

    if len(full_name) < 2:
        return jsonify(error="Veuillez indiquer votre nom et prénom."), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="Adresse e-mail invalide."), 400
    if len(password) < 6:
        return jsonify(error="Le mot de passe doit contenir au moins 6 caractères."), 400
    if university and university not in UNIVERSITIES:
        return jsonify(error="Établissement non reconnu."), 400

    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return jsonify(error="Un compte existe déjà avec cette adresse e-mail."), 409

    cur = db.execute(
        "INSERT INTO users (full_name, email, password_hash, university, faculty) VALUES (?, ?, ?, ?, ?)",
        (full_name, email, generate_password_hash(password), university or None, faculty or None),
    )
    db.executemany(
        "INSERT INTO skills (user_id, name, level) VALUES (?, ?, ?)",
        [(cur.lastrowid, name, level) for name, level in DEFAULT_SKILLS],
    )
    db.commit()
    session.clear()
    session["user_id"] = cur.lastrowid
    return jsonify(user_payload(current_user())), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify(error="E-mail ou mot de passe incorrect."), 401
    session.clear()
    session["user_id"] = row["id"]
    return jsonify(user_payload(row))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def me():
    row = current_user()
    if not row:
        return jsonify(user=None)
    return jsonify(user=user_payload(row))


@app.put("/api/skills/<int:skill_id>")
@login_required
def update_skill(skill_id):
    data = request.get_json(silent=True) or {}
    try:
        level = int(data.get("level"))
    except (TypeError, ValueError):
        return jsonify(error="Niveau invalide."), 400
    level = max(0, min(100, level))
    db = get_db()
    cur = db.execute(
        "UPDATE skills SET level = ? WHERE id = ? AND user_id = ?",
        (level, skill_id, session["user_id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Compétence introuvable."), 404
    return jsonify(user_payload(current_user()))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
