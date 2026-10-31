import os
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, flash, abort, g
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================
# SKILLUP CAMPUS — application Flask
# Base de données SQLite en local / PostgreSQL avec DATABASE_URL
# ============================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    os.makedirs("instance", exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.abspath(
        os.path.join("instance", "skillup_campus.db")
    )

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 14

db = SQLAlchemy(app)

# ----------------------------- MODELES -----------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    institution = db.Column(db.String(180), default="")
    field_of_study = db.Column(db.String(180), default="")
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="student", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), default="Compétence générale")
    level = db.Column(db.String(30), default="Débutant")
    progress = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, default="")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(100), default="Général")
    description = db.Column(db.Text, default="")
    level = db.Column(db.String(50), default="Tous niveaux")
    resource_url = db.Column(db.String(500), default="")
    is_published = db.Column(db.Boolean, default=True)

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    progress = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    __table_args__ = (db.UniqueConstraint("user_id", "course_id"),)

class PortfolioItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(100), default="Projet")
    description = db.Column(db.Text, default="")
    link = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

# ----------------------------- SECURITE -----------------------------

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]

app.jinja_env.globals["csrf_token"] = csrf_token

@app.before_request
def protect_post_requests():
    if request.method == "POST":
        supplied = request.form.get("_csrf", "")
        expected = session.get("_csrf", "")
        if not supplied or not expected or not secrets.compare_digest(supplied, expected):
            abort(400, "Formulaire expiré ou invalide. Rechargez la page.")

@app.before_request
def load_current_user():
    g.user = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    if session.get("user_id") and g.user is None:
        session.clear()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Connectez-vous pour accéder à votre espace.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def safe_next(value):
    # N'accepte que les chemins internes simples.
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("dashboard")

# ----------------------------- DESIGN / GABARITS -----------------------------

BASE = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#102b4e">
<title>{{ title }} · SKILLUP CAMPUS</title>
<style>
:root{--navy:#102b4e;--navy2:#173d68;--green:#18a875;--bg:#f4f7fb;--ink:#1d2939;--muted:#667085;--line:#e6ebf1;--white:#fff;--red:#c0392b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px Inter,Segoe UI,Arial,sans-serif}
a{text-decoration:none;color:inherit}button,input,select,textarea{font:inherit}
.layout{min-height:100vh;display:grid;grid-template-columns:250px 1fr}
.sidebar{background:var(--navy);color:white;padding:23px 15px;position:sticky;top:0;height:100vh;overflow:auto}
.brand{font-weight:900;font-size:19px;display:flex;align-items:center;gap:10px;padding:4px 10px 27px}
.logo{width:38px;height:38px;border-radius:12px;background:var(--green);display:grid;place-items:center;color:white;font-weight:900}
.navlabel{font-size:10px;letter-spacing:1.5px;color:#8fa5bd;padding:13px 12px 7px;text-transform:uppercase}
.nav a{display:flex;gap:12px;align-items:center;padding:11px 12px;border-radius:10px;color:#d5e0eb;margin:3px 0;font-size:14px}
.nav a:hover,.nav a.active{background:#ffffff1b;color:white}
.nav .ico{width:20px;text-align:center}
.side-bottom{border-top:1px solid #ffffff26;margin-top:25px;padding-top:15px}
.main{min-width:0}.topbar{height:72px;background:white;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 34px;position:sticky;top:0;z-index:5}
.topbar small{color:var(--muted)}.userbox{display:flex;align-items:center;gap:10px}.avatar{width:38px;height:38px;border-radius:50%;background:#e2f4ed;color:#13875f;display:grid;place-items:center;font-weight:800}
.content{max-width:1200px;margin:auto;padding:32px 34px 60px}
h1{font-size:27px;color:var(--navy);margin:0 0 7px}h2{font-size:19px;color:var(--navy);margin:0 0 15px}h3{font-size:16px;color:var(--navy);margin:0 0 8px}
.subtitle{color:var(--muted);margin:0 0 25px}.grid{display:grid;gap:17px}.grid.cards{grid-template-columns:repeat(4,minmax(0,1fr))}.grid.two{grid-template-columns:1.15fr .85fr}
.card{background:white;border:1px solid var(--line);border-radius:16px;padding:21px;box-shadow:0 4px 15px #102b4e07}
.stat small{color:var(--muted)}.stat strong{display:block;color:var(--navy);font-size:27px;margin-top:7px}
.btn{border:0;border-radius:9px;padding:10px 15px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;gap:7px;cursor:pointer}
.primary{background:var(--green);color:white}.secondary{background:white;border:1px solid var(--line);color:var(--navy)}.danger{background:#fff1f0;color:var(--red)}
.btn:hover{filter:brightness(.97)}.actions{display:flex;gap:9px;flex-wrap:wrap}
form .field{margin:13px 0}label{display:block;font-size:13px;font-weight:700;margin-bottom:6px;color:#344054}
input,select,textarea{width:100%;padding:11px 12px;border:1px solid #d8dee8;border-radius:9px;background:white;outline:none}
input:focus,select:focus,textarea:focus{border-color:var(--green);box-shadow:0 0 0 3px #18a87518}
textarea{min-height:100px;resize:vertical}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}.full{grid-column:1/-1}
.flash{padding:12px 15px;border-radius:10px;margin:0 0 15px;background:#e9f7f0;color:#116b4d}.flash.error{background:#fff1f0;color:#a52b20}.flash.info{background:#edf4ff;color:#234f86}
.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:560px}th,td{text-align:left;padding:12px;border-bottom:1px solid var(--line);font-size:13px}th{color:var(--muted);font-weight:700}
.pill{display:inline-block;border-radius:30px;padding:4px 9px;background:#e8f7f1;color:#13875f;font-size:11px;font-weight:800}
.progress{height:8px;border-radius:20px;background:#edf1f5;overflow:hidden}.progress i{display:block;height:100%;background:var(--green)}
.empty{padding:28px;text-align:center;color:var(--muted);border:1px dashed #ccd5df;border-radius:12px}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px}.muted{color:var(--muted)}.small{font-size:12px}
.authbody{min-height:100vh;display:grid;grid-template-columns:1fr 1fr;background:white}
.authleft{background:linear-gradient(145deg,#102b4e,#145b59);color:white;padding:8vw;display:flex;flex-direction:column;justify-content:center}
.authleft h1{font-size:42px;color:white;line-height:1.1}.authleft p{color:#d4e4ee;max-width:470px;line-height:1.7}
.authright{display:grid;place-items:center;padding:30px}.authbox{width:min(420px,100%)}.authbox h2{font-size:27px;margin-bottom:6px}
.authbox .btn{width:100%;margin-top:10px}.authfoot{font-size:13px;text-align:center;color:var(--muted);margin-top:18px}
.mobilebrand{display:none}
@media(max-width:1050px){.grid.cards{grid-template-columns:repeat(2,1fr)}.layout{grid-template-columns:220px 1fr}.content{padding:25px 22px}}
@media(max-width:760px){.layout{display:block}.sidebar{position:relative;height:auto;padding:10px 12px}.brand{padding:3px 8px 10px}.nav{display:flex;overflow-x:auto;gap:4px}.navlabel,.side-bottom{display:none}.nav a{white-space:nowrap;padding:9px}.topbar{height:60px;padding:0 17px}.content{padding:22px 15px 45px}.grid.two{grid-template-columns:1fr}.authbody{grid-template-columns:1fr}.authleft{display:none}.authright{min-height:100vh}.mobilebrand{display:flex;margin-bottom:30px}}
@media(max-width:460px){.grid.cards{grid-template-columns:1fr 1fr;gap:10px}.card{padding:15px}.stat strong{font-size:22px}.formgrid{grid-template-columns:1fr}.full{grid-column:auto}h1{font-size:23px}}
</style>
</head><body>
{% if current_user %}
<div class="layout">
<aside class="sidebar">
<a class="brand" href="{{ url_for('dashboard') }}"><span class="logo">S</span> SKILLUP CAMPUS</a>
<div class="navlabel">Espace étudiant</div>
<nav class="nav">
<a class="{{ 'active' if active=='dashboard' else '' }}" href="{{ url_for('dashboard') }}"><span class="ico">▦</span> Tableau de bord</a>
<a class="{{ 'active' if active=='profile' else '' }}" href="{{ url_for('profile') }}"><span class="ico">◉</span> Mon profil</a>
<a class="{{ 'active' if active=='diagnostic' else '' }}" href="{{ url_for('diagnostic') }}"><span class="ico">⌕</span> Diagnostic</a>
<a class="{{ 'active' if active=='skills' else '' }}" href="{{ url_for('skills') }}"><span class="ico">✦</span> Mes compétences</a>
<a class="{{ 'active' if active=='courses' else '' }}" href="{{ url_for('courses') }}"><span class="ico">▤</span> Formations</a>
<a class="{{ 'active' if active=='portfolio' else '' }}" href="{{ url_for('portfolio') }}"><span class="ico">▣</span> Mon portfolio</a>
<a class="{{ 'active' if active=='progress' else '' }}" href="{{ url_for('progress') }}"><span class="ico">↗</span> Ma progression</a>
</nav>
<div class="side-bottom">
<div class="navlabel">Compte</div>
<nav class="nav"><a href="{{ url_for('profile') }}"><span class="ico">⚙</span> Paramètres</a>
<form method="post" action="{{ url_for('logout') }}"><input type="hidden" name="_csrf" value="{{ csrf_token() }}"><button class="btn" style="background:transparent;color:#d5e0eb;padding:10px 12px">↪ Déconnexion</button></form></nav>
</div>
</aside>
<div class="main">
<header class="topbar"><div><strong>{{ title }}</strong><br><small>Votre espace de développement</small></div><div class="userbox"><div><b>{{ current_user.full_name }}</b><br><small>{{ current_user.role|capitalize }}</small></div><div class="avatar">{{ current_user.full_name[:1]|upper }}</div></div></header>
<main class="content">
{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash {{ category }}">{{ message }}</div>{% endfor %}{% endwith %}
{{ body|safe }}
</main></div></div>
{% else %}
{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash {{ category }}" style="position:fixed;top:15px;left:5%;right:5%;z-index:5">{{ message }}</div>{% endfor %}{% endwith %}
<div class="authbody"><section class="authleft"><a class="brand" href="{{ url_for('home') }}"><span class="logo">S</span> SKILLUP CAMPUS</a><h1>Votre potentiel mérite un espace pour grandir.</h1><p>Développez vos compétences, suivez votre progression et construisez un portfolio qui valorise vos réalisations.</p><p>Une plateforme conçue pour accompagner les étudiants dans leur parcours professionnel.</p></section><section class="authright"><div class="authbox"><div class="mobilebrand brand"><span class="logo">S</span> SKILLUP CAMPUS</div>{{ body|safe }}</div></section></div>
{% endif %}
</body></html>
"""

def page(title, body, active=""):
    return render_template_string(BASE, title=title, body=body, active=active,
                                  current_user=g.user)

# ----------------------------- PAGES PUBLIQUES / AUTH -----------------------------

@app.route("/")
def home():
    if g.user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/inscription", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        institution = request.form.get("institution", "").strip()
        field = request.form.get("field_of_study", "").strip()
        if len(name) < 2 or "@" not in email or len(password) < 8:
            flash("Vérifiez les informations. Le mot de passe doit contenir au moins 8 caractères.", "error")
        elif User.query.filter(func.lower(User.email) == email).first():
            flash("Cette adresse e-mail possède déjà un compte.", "error")
        else:
            user = User(full_name=name, email=email, institution=institution,
                        field_of_study=field, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            flash("Votre compte a été créé. Bienvenue sur SKILLUP CAMPUS !", "info")
            return redirect(url_for("dashboard"))
    body = r"""
    <h2>Créer votre compte</h2><p class="muted">Rejoignez SKILLUP CAMPUS et commencez votre parcours.</p>
    <form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="field"><label>Nom et prénom</label><input name="full_name" required maxlength="120" autocomplete="name"></div>
    <div class="field"><label>Adresse e-mail</label><input type="email" name="email" required autocomplete="email"></div>
    <div class="field"><label>Université / établissement</label><input name="institution" maxlength="180"></div>
    <div class="field"><label>Filière / domaine d'étude</label><input name="field_of_study" maxlength="180"></div>
    <div class="field"><label>Mot de passe (8 caractères minimum)</label><input type="password" name="password" minlength="8" required autocomplete="new-password"></div>
    <button class="btn primary">Créer mon compte →</button></form>
    <div class="authfoot">Vous avez déjà un compte ? <a style="color:#18a875;font-weight:800" href="{{ url_for('login') }}">Se connecter</a></div>"""
    return page("Créer un compte", body)

@app.route("/connexion", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            flash("Connexion réussie. Heureux de vous retrouver !", "info")
            return redirect(safe_next(request.args.get("next")))
        flash("Adresse e-mail ou mot de passe incorrect.", "error")
    body = r"""
    <h2>Bienvenue !</h2><p class="muted">Connectez-vous pour accéder à votre espace étudiant.</p>
    <form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="field"><label>Adresse e-mail</label><input type="email" name="email" required autocomplete="email"></div>
    <div class="field"><label>Mot de passe</label><input type="password" name="password" required autocomplete="current-password"></div>
    <button class="btn primary">Se connecter →</button></form>
    <div class="authfoot">Vous n'avez pas de compte ? <a style="color:#18a875;font-weight:800" href="{{ url_for('register') }}">Créer un compte</a><br><br><span class="small">Mot de passe oublié : contactez l'administrateur pour une réinitialisation sécurisée.</span></div>"""
    return page("Connexion", body)

@app.route("/deconnexion", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("login"))

# ----------------------------- ESPACE ETUDIANT -----------------------------

@app.route("/tableau-de-bord")
@login_required
def dashboard():
    skill_count = Skill.query.filter_by(user_id=g.user.id).count()
    portfolio_count = PortfolioItem.query.filter_by(user_id=g.user.id).count()
    enrollment_count = Enrollment.query.filter_by(user_id=g.user.id).count()
    avg = db.session.query(func.avg(Skill.progress)).filter_by(user_id=g.user.id).scalar() or 0
    recent_skills = Skill.query.filter_by(user_id=g.user.id).order_by(Skill.id.desc()).limit(5).all()
    body = r"""
    <h1>Bonjour {{ current_user.full_name.split(' ')[0] }} 👋</h1>
    <p class="subtitle">Voici votre espace de travail. Chaque étape vous rapproche de vos objectifs.</p>
    <div class="grid cards">
      <div class="card stat"><small>Compétences suivies</small><strong>{{ skill_count }}</strong><span class="small muted">Votre savoir-faire</span></div>
      <div class="card stat"><small>Formations rejointes</small><strong>{{ enrollment_count }}</strong><span class="small muted">Votre apprentissage</span></div>
      <div class="card stat"><small>Éléments du portfolio</small><strong>{{ portfolio_count }}</strong><span class="small muted">Vos réalisations</span></div>
      <div class="card stat"><small>Progression moyenne</small><strong>{{ avg|round|int }}%</strong><span class="small muted">Sur vos compétences</span></div>
    </div>
    <div class="grid two" style="margin-top:18px">
      <section class="card"><div class="row"><h2>Mes compétences récentes</h2><a class="small" style="color:#18a875" href="{{ url_for('skills') }}">Tout voir →</a></div>
      {% if recent_skills %}{% for s in recent_skills %}<div style="margin:17px 0"><div class="row"><b>{{ s.title }}</b><span class="small muted">{{ s.progress }}%</span></div><div class="progress" style="margin-top:8px"><i style="width:{{ s.progress }}%"></i></div></div>{% endfor %}{% else %}<div class="empty">Vous n'avez pas encore ajouté de compétence.<br><a href="{{ url_for('skills') }}" style="color:#18a875">Ajouter ma première compétence</a></div>{% endif %}</section>
      <section class="card"><h2>Prochaines étapes</h2>
      <p class="muted">Organisez votre parcours en quelques actions simples.</p>
      <p>① <a href="{{ url_for('diagnostic') }}">Faire le point sur mes compétences</a></p>
      <p>② <a href="{{ url_for('courses') }}">Découvrir les formations</a></p>
      <p>③ <a href="{{ url_for('portfolio') }}">Ajouter un projet à mon portfolio</a></p>
      <p>④ <a href="{{ url_for('profile') }}">Compléter mon profil</a></p></section>
    </div>"""
    return page("Tableau de bord", render_template_string(body, skill_count=skill_count,
        portfolio_count=portfolio_count, enrollment_count=enrollment_count, avg=avg,
        recent_skills=recent_skills), "dashboard")

@app.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        g.user.full_name = request.form.get("full_name", "").strip()[:120]
        g.user.institution = request.form.get("institution", "").strip()[:180]
        g.user.field_of_study = request.form.get("field_of_study", "").strip()[:180]
        new_password = request.form.get("new_password", "")
        if new_password:
            if len(new_password) < 8:
                flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "error")
                return redirect(url_for("profile"))
            g.user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("Votre profil a été mis à jour.", "info")
        return redirect(url_for("profile"))
    body = r"""
    <h1>Mon profil</h1><p class="subtitle">Gérez vos informations personnelles et académiques.</p>
    <div class="card"><form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="formgrid">
    <div class="field"><label>Nom et prénom</label><input name="full_name" value="{{ current_user.full_name }}" required></div>
    <div class="field"><label>Adresse e-mail (non modifiable)</label><input value="{{ current_user.email }}" disabled></div>
    <div class="field"><label>Université / établissement</label><input name="institution" value="{{ current_user.institution }}"></div>
    <div class="field"><label>Filière / domaine</label><input name="field_of_study" value="{{ current_user.field_of_study }}"></div>
    <div class="field full"><label>Nouveau mot de passe (laisser vide pour ne pas changer)</label><input type="password" name="new_password" minlength="8" autocomplete="new-password"></div>
    </div><button class="btn primary">Enregistrer les modifications</button></form></div>"""
    return page("Mon profil", body, "profile")

@app.route("/diagnostic")
@login_required
def diagnostic():
    body = r"""
    <h1>Mon diagnostic</h1><p class="subtitle">Évaluez votre niveau avec honnêteté. Vous pourrez le faire évoluer au fil de vos apprentissages.</p>
    <div class="grid two">
    <div class="card"><h2>Comment utiliser le diagnostic ?</h2><p class="muted">Ajoutez une compétence, choisissez votre niveau actuel et estimez votre progression. Le diagnostic est personnel et peut être actualisé à tout moment.</p><a class="btn primary" href="{{ url_for('skills') }}">Commencer mon diagnostic →</a></div>
    <div class="card"><h2>Échelle de niveau</h2><p><span class="pill">Débutant</span> Je découvre les bases.</p><p><span class="pill">Intermédiaire</span> Je réalise des tâches courantes.</p><p><span class="pill">Avancé</span> Je travaille de manière autonome.</p><p><span class="pill">Expert</span> Je maîtrise et peux accompagner d'autres personnes.</p></div>
    </div>"""
    return page("Diagnostic", body, "diagnostic")

@app.route("/competences", methods=["GET", "POST"])
@login_required
def skills():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        try: progress = max(0, min(100, int(request.form.get("progress", 0))))
        except ValueError: progress = 0
        if not title:
            flash("Le nom de la compétence est obligatoire.", "error")
        else:
            db.session.add(Skill(title=title[:120], category=request.form.get("category","Compétence générale")[:80],
                level=request.form.get("level","Débutant")[:30], progress=progress,
                notes=request.form.get("notes","")[:3000], user_id=g.user.id))
            db.session.commit()
            flash("Compétence ajoutée.", "info")
        return redirect(url_for("skills"))
    items = Skill.query.filter_by(user_id=g.user.id).order_by(Skill.id.desc()).all()
    body = r"""
    <h1>Mes compétences</h1><p class="subtitle">Ajoutez vos savoir-faire et suivez votre progression.</p>
    <div class="grid two"><section class="card"><h2>Ajouter une compétence</h2>
    <form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="field"><label>Nom de la compétence</label><input name="title" placeholder="Ex. : Excel, communication, collecte de données..." required></div>
    <div class="formgrid"><div class="field"><label>Catégorie</label><select name="category"><option>Numérique</option><option>Professionnelle</option><option>Technique</option><option>Recherche et données</option><option>Langues</option><option>Autre</option></select></div>
    <div class="field"><label>Niveau</label><select name="level"><option>Débutant</option><option>Intermédiaire</option><option>Avancé</option><option>Expert</option></select></div>
    <div class="field full"><label>Progression estimée : <output id="pv">0</output>%</label><input type="range" min="0" max="100" name="progress" value="0" oninput="pv.value=this.value"></div></div>
    <div class="field"><label>Notes (facultatif)</label><textarea name="notes"></textarea></div><button class="btn primary">Ajouter</button></form></section>
    <section class="card"><h2>Mes compétences enregistrées</h2>
    {% if items %}{% for s in items %}<div style="padding:13px 0;border-bottom:1px solid #e6ebf1"><div class="row"><b>{{ s.title }}</b><span class="pill">{{ s.level }}</span></div><small class="muted">{{ s.category }} · {{ s.progress }}%</small><div class="progress" style="margin-top:8px"><i style="width:{{ s.progress }}%"></i></div><form method="post" action="{{ url_for('delete_skill',skill_id=s.id) }}" style="margin-top:8px"><input type="hidden" name="_csrf" value="{{ csrf_token() }}"><button class="btn danger" onclick="return confirm('Supprimer cette compétence ?')">Supprimer</button></form></div>{% endfor %}{% else %}<div class="empty">Aucune compétence enregistrée pour le moment.</div>{% endif %}
    </section></div>"""
    return page("Mes compétences", render_template_string(body, items=items), "skills")

@app.route("/competences/<int:skill_id>/supprimer", methods=["POST"])
@login_required
def delete_skill(skill_id):
    item = Skill.query.filter_by(id=skill_id, user_id=g.user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Compétence supprimée.", "info")
    return redirect(url_for("skills"))

@app.route("/formations", methods=["GET", "POST"])
@login_required
def courses():
    if request.method == "POST":
        course_id = request.form.get("course_id", type=int)
        course = Course.query.filter_by(id=course_id, is_published=True).first_or_404()
        if not Enrollment.query.filter_by(user_id=g.user.id, course_id=course.id).first():
            db.session.add(Enrollment(user_id=g.user.id, course_id=course.id))
            db.session.commit()
            flash("Formation ajoutée à votre parcours.", "info")
        return redirect(url_for("courses"))
    items = Course.query.filter_by(is_published=True).order_by(Course.id.desc()).all()
    enrolled = {e.course_id for e in Enrollment.query.filter_by(user_id=g.user.id).all()}
    body = r"""
    <h1>Formations</h1><p class="subtitle">Explorez les parcours proposés et ajoutez ceux qui vous intéressent.</p>
    {% if items %}<div class="grid cards">{% for c in items %}<article class="card"><span class="pill">{{ c.category }}</span><h3 style="margin-top:13px">{{ c.title }}</h3><p class="muted">{{ c.description }}</p><p class="small muted">Niveau : {{ c.level }}</p>
    {% if c.id in enrolled %}<span class="pill">Dans mon parcours</span>{% else %}<form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}"><input type="hidden" name="course_id" value="{{ c.id }}"><button class="btn primary">Ajouter à mon parcours</button></form>{% endif %}
    {% if c.resource_url %}<p><a style="color:#18a875" target="_blank" rel="noopener" href="{{ c.resource_url }}">Ouvrir la ressource ↗</a></p>{% endif %}</article>{% endfor %}</div>{% else %}<div class="empty">Aucune formation n'est encore publiée. Les formations seront ajoutées par l'équipe d'administration.</div>{% endif %}"""
    return page("Formations", render_template_string(body, items=items, enrolled=enrolled), "courses")

@app.route("/portfolio", methods=["GET", "POST"])
@login_required
def portfolio():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if title:
            db.session.add(PortfolioItem(title=title[:180], category=request.form.get("category","Projet")[:100],
                description=request.form.get("description","")[:4000], link=request.form.get("link","")[:500],
                user_id=g.user.id))
            db.session.commit()
            flash("Réalisation ajoutée à votre portfolio.", "info")
        else:
            flash("Le titre est obligatoire.", "error")
        return redirect(url_for("portfolio"))
    items = PortfolioItem.query.filter_by(user_id=g.user.id).order_by(PortfolioItem.created_at.desc()).all()
    body = r"""
    <h1>Mon portfolio</h1><p class="subtitle">Présentez vos projets, travaux pratiques et réalisations.</p>
    <div class="grid two"><section class="card"><h2>Ajouter une réalisation</h2><form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div class="field"><label>Titre du projet</label><input name="title" required></div><div class="field"><label>Type de réalisation</label><select name="category"><option>Projet académique</option><option>Stage</option><option>Projet personnel</option><option>Expérience professionnelle</option><option>Autre</option></select></div>
    <div class="field"><label>Description</label><textarea name="description" placeholder="Objectif, votre rôle, résultats obtenus..."></textarea></div>
    <div class="field"><label>Lien externe (facultatif)</label><input type="url" name="link" placeholder="https://..."></div><button class="btn primary">Enregistrer</button></form></section>
    <section class="card"><h2>Mes réalisations</h2>{% if items %}{% for p in items %}<article style="padding:13px 0;border-bottom:1px solid #e6ebf1"><span class="pill">{{ p.category }}</span><h3 style="margin-top:9px">{{ p.title }}</h3><p class="muted">{{ p.description }}</p>{% if p.link %}<a href="{{ p.link }}" target="_blank" rel="noopener" style="color:#18a875">Voir le projet ↗</a>{% endif %}</article>{% endfor %}{% else %}<div class="empty">Votre portfolio est encore vide. Ajoutez votre première réalisation.</div>{% endif %}</section></div>"""
    return page("Mon portfolio", render_template_string(body, items=items), "portfolio")

@app.route("/progression")
@login_required
def progress():
    skills_list = Skill.query.filter_by(user_id=g.user.id).all()
    enrollments = Enrollment.query.filter_by(user_id=g.user.id).all()
    avg = round(sum(s.progress for s in skills_list) / len(skills_list)) if skills_list else 0
    done = sum(1 for e in enrollments if e.completed)
    body = r"""
    <h1>Ma progression</h1><p class="subtitle">Un aperçu de votre évolution dans SKILLUP CAMPUS.</p>
    <div class="grid cards"><div class="card stat"><small>Compétences suivies</small><strong>{{ skills_list|length }}</strong></div><div class="card stat"><small>Progression moyenne</small><strong>{{ avg }}%</strong></div><div class="card stat"><small>Formations rejointes</small><strong>{{ enrollments|length }}</strong></div><div class="card stat"><small>Formations terminées</small><strong>{{ done }}</strong></div></div>
    <section class="card" style="margin-top:18px"><h2>Détail par compétence</h2>{% if skills_list %}{% for s in skills_list %}<div style="margin:17px 0"><div class="row"><b>{{ s.title }}</b><span>{{ s.progress }}%</span></div><div class="progress" style="margin-top:8px"><i style="width:{{ s.progress }}%"></i></div></div>{% endfor %}{% else %}<div class="empty">Ajoutez des compétences pour suivre votre évolution.</div>{% endif %}</section>"""
    return page("Ma progression", render_template_string(body, skills_list=skills_list, avg=avg,
        enrollments=enrollments, done=done), "progress")

# ----------------------------- ADMINISTRATION -----------------------------

@app.route("/administration")
@admin_required
def admin():
    users = User.query.order_by(User.created_at.desc()).all()
    courses_count = Course.query.count()
    body = r"""
    <h1>Administration</h1><p class="subtitle">Vue réservée aux administrateurs.</p>
    <div class="grid cards"><div class="card stat"><small>Comptes étudiants</small><strong>{{ users|length }}</strong></div><div class="card stat"><small>Formations</small><strong>{{ courses_count }}</strong></div></div>
    <section class="card" style="margin-top:18px"><h2>Comptes créés</h2><div class="tablewrap"><table><thead><tr><th>Nom</th><th>E-mail</th><th>Établissement</th><th>Rôle</th></tr></thead><tbody>{% for u in users %}<tr><td>{{ u.full_name }}</td><td>{{ u.email }}</td><td>{{ u.institution }}</td><td>{{ u.role }}</td></tr>{% endfor %}</tbody></table></div></section>
    <section class="card" style="margin-top:18px"><h2>Publier une formation</h2><form method="post" action="{{ url_for('admin_course') }}"><input type="hidden" name="_csrf" value="{{ csrf_token() }}"><div class="formgrid"><div class="field"><label>Titre</label><input name="title" required></div><div class="field"><label>Catégorie</label><input name="category"></div><div class="field"><label>Niveau</label><input name="level" value="Tous niveaux"></div><div class="field"><label>Lien de ressource (facultatif)</label><input type="url" name="resource_url"></div><div class="field full"><label>Description</label><textarea name="description"></textarea></div></div><button class="btn primary">Publier la formation</button></form></section>"""
    return page("Administration", render_template_string(body, users=users, courses_count=courses_count))

@app.route("/administration/formations", methods=["POST"])
@admin_required
def admin_course():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Le titre de la formation est obligatoire.", "error")
    else:
        db.session.add(Course(title=title[:180], category=request.form.get("category","Général")[:100],
            level=request.form.get("level","Tous niveaux")[:50],
            resource_url=request.form.get("resource_url","")[:500],
            description=request.form.get("description","")[:3000]))
        db.session.commit()
        flash("Formation publiée.", "info")
    return redirect(url_for("admin"))

# ----------------------------- ERREURS / INITIALISATION -----------------------------

@app.errorhandler(403)
def forbidden(_):
    return page("Accès refusé", "<h1>Accès refusé</h1><p class='subtitle'>Vous n'avez pas les autorisations nécessaires.</p><a class='btn primary' href='/tableau-de-bord'>Retour au tableau de bord</a>"), 403

@app.errorhandler(404)
def not_found(_):
    return page("Page introuvable", "<h1>Page introuvable</h1><p class='subtitle'>Cette page n'existe pas ou n'est plus disponible.</p><a class='btn primary' href='/tableau-de-bord'>Retour au tableau de bord</a>"), 404

with app.app_context():
    db.create_all()
    # Quelques formations de départ, publiées une seule fois.
    if Course.query.count() == 0:
        db.session.add_all([
            Course(title="Maîtriser les bases d'Excel", category="Compétences numériques",
                   description="Organiser des données, utiliser les formules essentielles et créer des tableaux.", level="Débutant"),
            Course(title="Introduction à Power BI", category="Données et analyse",
                   description="Découvrir la préparation des données et la création de rapports visuels.", level="Débutant"),
            Course(title="Communication professionnelle", category="Compétences professionnelles",
                   description="Améliorer la communication écrite, orale et le travail en équipe.", level="Tous niveaux"),
            Course(title="Initiation au suivi-évaluation", category="Gestion de projet",
                   description="Comprendre les indicateurs, les outils de collecte et le suivi des activités.", level="Débutant")
        ])
        db.session.commit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
