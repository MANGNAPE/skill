"""SKILLUP CAMPUS — serveur Flask (comptes, espace étudiant, compétences, formations, portfolio).

Base de données :
  - DATABASE_URL défini (PostgreSQL, ex. Neon/Supabase) -> données PERMANENTES (recommandé en ligne)
  - sinon SQLite local (fichier skillup.db) -> OK en local, mais effacé sur un hébergement gratuit
"""
import os
import re
import sqlite3
import time
from datetime import timedelta
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
USE_PG = DATABASE_URL.startswith("postgresql://")
if USE_PG:
    import psycopg2
    import psycopg2.extras

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
# Catalogue de formations : modifiez/ajoutez ici. "link" = lien du contenu (vide = bientôt disponible).
COURSES = [
    {"id": "excel", "icon": "📊", "title": "Excel intermédiaire", "category": "Compétence numérique",
     "level": "Débutant +", "duration": "6 h", "keyword": "excel", "link": "",
     "description": "Formules, tableaux croisés dynamiques et graphiques pour analyser vos données."},
    {"id": "powerbi", "icon": "📈", "title": "Initiation à Power BI", "category": "Analyse de données",
     "level": "Débutant", "duration": "5 h", "keyword": "donn", "link": "",
     "description": "Construire vos premiers tableaux de bord à partir de fichiers Excel."},
    {"id": "suivi-eval", "icon": "📝", "title": "Suivi-évaluation de projets", "category": "Gestion de projet",
     "level": "Intermédiaire", "duration": "8 h", "keyword": "suivi", "link": "",
     "description": "Cadre logique, indicateurs, collecte de données et rapports de suivi."},
    {"id": "communication", "icon": "🎤", "title": "Communication professionnelle", "category": "Compétences douces",
     "level": "Débutant", "duration": "4 h", "keyword": "communication", "link": "",
     "description": "Écrire un e-mail pro, prendre la parole et présenter un projet."},
    {"id": "emploi", "icon": "💼", "title": "CV, lettre et entretien", "category": "Insertion professionnelle",
     "level": "Débutant", "duration": "3 h", "keyword": "emploi", "link": "",
     "description": "Préparer des candidatures solides et réussir ses entretiens."},
    {"id": "ia", "icon": "🤖", "title": "Outils IA au quotidien", "category": "Compétence numérique",
     "level": "Débutant", "duration": "3 h", "keyword": "ia", "link": "",
     "description": "Utiliser l'IA pour étudier, rédiger et gagner du temps."},
]
COURSE_IDS = {c["id"] for c in COURSES}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_SKILLS, MAX_PORTFOLIO, MIN_PASSWORD = 20, 30, 8

app = Flask(_name_, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="/static")


def _load_secret_key():
    """SECRET_KEY depuis l'environnement (à définir en ligne), sinon fichier à côté de la base."""
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
    except OSError:
        return new_key


app.config["SECRET_KEY"] = _load_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RENDER") or os.environ.get("FORCE_HTTPS"))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


# ---------- Base de données (SQLite ou PostgreSQL) ----------
def get_db():
    if "db" not in g:
        if USE_PG:
            g.db = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def run(sql, params=()):
    db = get_db()
    if USE_PG:
        cur = db.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return cur
    return db.execute(sql, params)


def one(sql, params=()):
    return run(sql, params).fetchone()


def many(sql, params=()):
    return run(sql, params).fetchall()


def insert(sql, params=()):
    """INSERT qui renvoie l'id créé (les tables ont toutes une colonne id)."""
    if USE_PG:
        return run(sql + " RETURNING id", params).fetchone()["id"]
    return run(sql, params).lastrowid


def commit():
    get_db().commit()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id {pk}, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
    university TEXT, faculty TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS skills (
    id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 100));
CREATE TABLE IF NOT EXISTS portfolio (
    id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL, description TEXT, link TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS enrollments (
    id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL, UNIQUE (user_id, course_id));
"""


def init_db():
    if USE_PG:
        db = psycopg2.connect(DATABASE_URL)
        cur = db.cursor()
        cur.execute("SELECT pg_advisory_lock(727001)")  # évite la course entre les 2 workers
        cur.execute(SCHEMA.format(pk="SERIAL PRIMARY KEY"))
        cur.execute("SELECT pg_advisory_unlock(727001)")
        db.commit()
    else:
        db = sqlite3.connect(DB_PATH)
        db.executescript(SCHEMA.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT"))
        db.commit()
    db.close()


# ---------- Utilitaires ----------
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Session expirée. Veuillez vous reconnecter."), 401
        return view(*args, **kwargs)

    return wrapper


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return one("SELECT id, full_name, email, university, faculty FROM users WHERE id = ?", (uid,))


def user_payload(row):
    uid = row["id"]
    skills = many("SELECT id, name, level FROM skills WHERE user_id = ? ORDER BY id", (uid,))
    portfolio = many(
        "SELECT id, title, description, link FROM portfolio WHERE user_id = ? ORDER BY id DESC", (uid,))
    enrolled = [r["course_id"] for r in many("SELECT course_id FROM enrollments WHERE user_id = ?", (uid,))]
    progress = round(sum(s["level"] for s in skills) / len(skills)) if skills else 0
    return {
        "id": uid,
        "fullName": row["full_name"],
        "email": row["email"],
        "university": row["university"],
        "faculty": row["faculty"],
        "skills": [{"id": s["id"], "name": s["name"], "level": s["level"]} for s in skills],
        "portfolio": [dict(id=p["id"], title=p["title"], description=p["description"] or "",
                           link=p["link"] or "") for p in portfolio],
        "enrolled": enrolled,
        "progress": progress,
    }


def clean(value, max_len):
    return (value or "").strip()[:max_len] if isinstance(value, (str, type(None))) else ""


_attempts = {}


def too_many_attempts(key):
    now = time.time()
    recent = [t for t in _attempts.get(key, []) if now - t < 300]
    _attempts[key] = recent
    return len(recent) >= 8


def note_attempt(key):
    _attempts.setdefault(key, []).append(time.time())


# ---------- Pages ----------
@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/healthz")
def healthz():
    try:
        one("SELECT 1")
    except Exception:  # noqa: BLE001
        return jsonify(status="db_error"), 500
    return jsonify(status="ok", database="postgresql" if USE_PG else "sqlite")


# ---------- API : compte ----------
@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    full_name = clean(data.get("fullname"), 100)
    email = clean(data.get("email"), 200).lower()
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    university = clean(data.get("university"), 100)
    faculty = clean(data.get("faculty"), 120)

    if len(full_name) < 2:
        return jsonify(error="Veuillez indiquer votre nom et prénom."), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="Adresse e-mail invalide."), 400
    if len(password) < MIN_PASSWORD:
        return jsonify(error=f"Le mot de passe doit contenir au moins {MIN_PASSWORD} caractères."), 400
    if university and university not in UNIVERSITIES:
        return jsonify(error="Établissement non reconnu."), 400
    if one("SELECT 1 FROM users WHERE email = ?", (email,)):
        return jsonify(error="Un compte existe déjà avec cette adresse e-mail. Connectez-vous."), 409

    uid = insert(
        "INSERT INTO users (full_name, email, password_hash, university, faculty) VALUES (?, ?, ?, ?, ?)",
        (full_name, email, generate_password_hash(password), university or None, faculty or None))
    for name, level in DEFAULT_SKILLS:
        run("INSERT INTO skills (user_id, name, level) VALUES (?, ?, ?)", (uid, name, level))
    commit()
    session.clear()
    session.permanent = True
    session["user_id"] = uid
    return jsonify(user_payload(current_user())), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = clean(data.get("email"), 200).lower()
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    key = f"{request.remote_addr}:{email}"
    if too_many_attempts(key):
        return jsonify(error="Trop de tentatives. Réessayez dans quelques minutes."), 429
    row = one("SELECT * FROM users WHERE email = ?", (email,))
    if not row:
        note_attempt(key)
        return jsonify(error="Aucun compte avec cette adresse e-mail. Créez un compte d'abord."), 401
    if not check_password_hash(row["password_hash"], password):
        note_attempt(key)
        return jsonify(error="Mot de passe incorrect."), 401
    _attempts.pop(key, None)
    session.clear()
    session.permanent = True
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
        session.clear()
        return jsonify(user=None)
    return jsonify(user=user_payload(row))


@app.put("/api/profile")
@login_required
def update_profile():
    data = request.get_json(silent=True) or {}
    full_name = clean(data.get("fullname"), 100)
    university = clean(data.get("university"), 100)
    faculty = clean(data.get("faculty"), 120)
    if len(full_name) < 2:
        return jsonify(error="Veuillez indiquer votre nom et prénom."), 400
    if university and university not in UNIVERSITIES:
        return jsonify(error="Établissement non reconnu."), 400
    run("UPDATE users SET full_name = ?, university = ?, faculty = ? WHERE id = ?",
        (full_name, university or None, faculty or None, session["user_id"]))
    commit()
    return jsonify(user_payload(current_user()))


@app.put("/api/password")
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    old = data.get("current") if isinstance(data.get("current"), str) else ""
    new = data.get("new") if isinstance(data.get("new"), str) else ""
    row = one("SELECT password_hash FROM users WHERE id = ?", (session["user_id"],))
    if not row or not check_password_hash(row["password_hash"], old):
        return jsonify(error="Mot de passe actuel incorrect."), 400
    if len(new) < MIN_PASSWORD:
        return jsonify(error=f"Le nouveau mot de passe doit contenir au moins {MIN_PASSWORD} caractères."), 400
    run("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), session["user_id"]))
    commit()
    return jsonify(ok=True)


@app.post("/api/account/delete")
@login_required
def delete_account():
    data = request.get_json(silent=True) or {}
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    row = one("SELECT password_hash FROM users WHERE id = ?", (session["user_id"],))
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify(error="Mot de passe incorrect."), 400
    uid = session["user_id"]
    for table in ("skills", "portfolio", "enrollments"):
        run(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
    run("DELETE FROM users WHERE id = ?", (uid,))
    commit()
    session.clear()
    return jsonify(ok=True)


# ---------- API : compétences ----------
@app.post("/api/skills")
@login_required
def add_skill():
    data = request.get_json(silent=True) or {}
    name = clean(data.get("name"), 60)
    try:
        level = max(0, min(100, int(data.get("level", 0))))
    except (TypeError, ValueError):
        level = 0
    if len(name) < 2:
        return jsonify(error="Indiquez le nom de la compétence."), 400
    uid = session["user_id"]
    if one("SELECT COUNT(*) AS n FROM skills WHERE user_id = ?", (uid,))["n"] >= MAX_SKILLS:
        return jsonify(error=f"Maximum {MAX_SKILLS} compétences."), 400
    if one("SELECT 1 FROM skills WHERE user_id = ? AND LOWER(name) = LOWER(?)", (uid, name)):
        return jsonify(error="Cette compétence existe déjà."), 409
    run("INSERT INTO skills (user_id, name, level) VALUES (?, ?, ?)", (uid, name, level))
    commit()
    return jsonify(user_payload(current_user())), 201


@app.put("/api/skills/<int:skill_id>")
@login_required
def update_skill(skill_id):
    data = request.get_json(silent=True) or {}
    try:
        level = max(0, min(100, int(data.get("level"))))
    except (TypeError, ValueError):
        return jsonify(error="Niveau invalide."), 400
    cur = run("UPDATE skills SET level = ? WHERE id = ? AND user_id = ?", (level, skill_id, session["user_id"]))
    commit()
    if cur.rowcount == 0:
        return jsonify(error="Compétence introuvable."), 404
    return jsonify(user_payload(current_user()))


@app.delete("/api/skills/<int:skill_id>")
@login_required
def delete_skill(skill_id):
    cur = run("DELETE FROM skills WHERE id = ? AND user_id = ?", (skill_id, session["user_id"]))
    commit()
    if cur.rowcount == 0:
        return jsonify(error="Compétence introuvable."), 404
    return jsonify(user_payload(current_user()))


# ---------- API : formations ----------
@app.get("/api/courses")
def courses():
    return jsonify(courses=COURSES)


@app.post("/api/courses/<course_id>/toggle")
@login_required
def toggle_course(course_id):
    if course_id not in COURSE_IDS:
        return jsonify(error="Formation introuvable."), 404
    uid = session["user_id"]
    if one("SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ?", (uid, course_id)):
        run("DELETE FROM enrollments WHERE user_id = ? AND course_id = ?", (uid, course_id))
    else:
        run("INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)", (uid, course_id))
    commit()
    return jsonify(user_payload(current_user()))


# ---------- API : portfolio ----------
@app.post("/api/portfolio")
@login_required
def add_project():
    data = request.get_json(silent=True) or {}
    title = clean(data.get("title"), 100)
    description = clean(data.get("description"), 500)
    link = clean(data.get("link"), 300)
    if len(title) < 2:
        return jsonify(error="Donnez un titre à votre réalisation."), 400
    if link and not re.match(r"^https?://", link, re.I):
        return jsonify(error="Le lien doit commencer par http:// ou https://"), 400
    uid = session["user_id"]
    if one("SELECT COUNT(*) AS n FROM portfolio WHERE user_id = ?", (uid,))["n"] >= MAX_PORTFOLIO:
        return jsonify(error=f"Maximum {MAX_PORTFOLIO} réalisations."), 400
    run("INSERT INTO portfolio (user_id, title, description, link) VALUES (?, ?, ?, ?)",
        (uid, title, description or None, link or None))
    commit()
    return jsonify(user_payload(current_user())), 201


@app.delete("/api/portfolio/<int:item_id>")
@login_required
def delete_project(item_id):
    cur = run("DELETE FROM portfolio WHERE id = ? AND user_id = ?", (item_id, session["user_id"]))
    commit()
    if cur.rowcount == 0:
        return jsonify(error="Réalisation introuvable."), 404
    return jsonify(user_payload(current_user()))


# ---------- Erreurs JSON pour l'API ----------
@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify(error="Ressource introuvable."), 404
    return send_from_directory(BASE_DIR, "index.html")


@app.errorhandler(500)
def server_error(_e):
    return jsonify(error="Erreur du serveur. Réessayez dans un instant."), 500


init_db()

if _name_ == "_main_":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
