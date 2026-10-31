# SKILLUP CAMPUS — plateforme fonctionnelle

Application Flask + SQLite : inscription, connexion, espace étudiant avec
suivi des compétences (curseurs mis à jour et sauvegardés en base).

## Structure

- `index.html` — page d'accueil et tableau de bord (ex-maquette, branchée sur l'API)
- `app.py` — serveur Flask, API `/api/*`, base SQLite `skillup.db`
- `requirements.txt` — dépendances

## Lancer en local

```bash
pip install -r requirements.txt
SECRET_KEY="une-longue-chaine-aleatoire" python app.py          # http://localhost:8000
# ou en production :
SECRET_KEY="..." gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

Variables d'environnement :

| Variable       | Rôle                                              | Défaut                |
|----------------|---------------------------------------------------|-----------------------|
| `SECRET_KEY`   | Signature des sessions (**à définir en production**) | clé aléatoire au démarrage |
| `SKILLUP_DB`   | Chemin du fichier SQLite                          | `skillup.db` à côté de `app.py` |
| `PORT`         | Port d'écoute                                     | `8000`                |

## API

| Méthode | Route                 | Description                              |
|---------|-----------------------|------------------------------------------|
| POST    | `/api/register`       | Crée un compte (nom, e-mail, mot de passe, université, filière) |
| POST    | `/api/login`          | Connexion                                |
| POST    | `/api/logout`         | Déconnexion                              |
| GET     | `/api/me`             | Utilisateur connecté (ou `null`)         |
| PUT     | `/api/skills/<id>`    | Met à jour le niveau d'une compétence (connexion requise) |

Les mots de passe sont hachés (werkzeug), les sessions sont en cookie HTTP-only.

## Mise en ligne

Le dossier est prêt pour un hébergement Python classique (Render, Railway,
Fly.io, VPS…) : commande de démarrage `gunicorn app:app`, variable `SECRET_KEY`
définie, et un volume persistant pour `skillup.db` (ou `SKILLUP_DB` pointant dessus).
