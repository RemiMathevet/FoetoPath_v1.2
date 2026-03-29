#!/usr/bin/env python3
"""
FoetoPath — Blueprint Authentification & Gestion Utilisateurs.

Routes :
  GET  /auth/login          Page de connexion
  POST /auth/login          Soumettre identifiants
  GET  /auth/logout         Déconnexion
  GET  /admin/users         Page de gestion des comptes
  GET  /auth/api/me         Info utilisateur connecté
  GET  /auth/api/users      Liste des utilisateurs (admin/admin_centre)
  POST /auth/api/users      Créer un utilisateur
  PUT  /auth/api/users/<id> Modifier un utilisateur
  DELETE /auth/api/users/<id> Supprimer un utilisateur
"""

from functools import wraps

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import auth_db

auth_bp = Blueprint("auth", __name__, template_folder="templates")


# ══════════════════════════════════════════════════════════════════════════
#  Décorateurs d'accès — importables depuis les autres blueprints
# ══════════════════════════════════════════════════════════════════════════

def login_required(f):
    """Redirige vers /auth/login si l'utilisateur n'est pas connecté."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            # Pour les requêtes API, retourner 401 au lieu de redirect
            if request.path.startswith("/admin/api/") or \
               request.path.startswith("/placenta/api/") or \
               request.path.startswith("/auth/api/") or \
               request.path.startswith("/api/"):
                return jsonify({"error": "Non authentifié"}), 401
            return redirect(url_for("auth.login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Vérifie que l'utilisateur connecté a l'un des rôles spécifiés."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                if request.path.startswith(("/admin/api/", "/placenta/api/",
                                            "/auth/api/", "/api/")):
                    return jsonify({"error": "Non authentifié"}), 401
                return redirect(url_for("auth.login_page", next=request.path))
            user_role = session.get("user_role", "")
            if user_role not in roles:
                if request.path.startswith(("/admin/api/", "/placenta/api/",
                                            "/auth/api/", "/api/")):
                    return jsonify({"error": "Accès refusé", "role": user_role}), 403
                return redirect(url_for("hub"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def can_write(f):
    """Autorise admin, admin_centre, user. Refuse spectator."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Non authentifié"}), 401
        role = session.get("user_role", "spectator")
        perms = auth_db.get_permissions(role)
        if not perms.get("can_write_cases"):
            return jsonify({"error": "Lecture seule"}), 403
        return f(*args, **kwargs)
    return decorated


def can_delete(f):
    """Autorise admin, admin_centre. Refuse user et spectator."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Non authentifié"}), 401
        role = session.get("user_role", "spectator")
        perms = auth_db.get_permissions(role)
        if not perms.get("can_delete_cases"):
            return jsonify({"error": "Suppression non autorisée"}), 403
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════════════════
#  Pages
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/auth/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("hub"))
    return render_template("login.html")


@auth_bp.route("/auth/login", methods=["POST"])
def login_submit():
    """Connexion par formulaire ou JSON."""
    if request.is_json:
        data = request.get_json()
        username = data.get("username", "")
        password = data.get("password", "")
    else:
        username = request.form.get("username", "")
        password = request.form.get("password", "")

    user = auth_db.authenticate(username, password)
    if not user:
        if request.is_json:
            return jsonify({"error": "Identifiants invalides"}), 401
        return render_template("login.html", error="Identifiants invalides")

    # Stocker en session
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["user_role"] = user["role"]
    session["display_name"] = user.get("display_name", user["username"])
    session.permanent = True

    if request.is_json:
        return jsonify({"ok": True, "user": user})

    next_url = request.form.get("next") or request.args.get("next") or "/"
    return redirect(next_url)


@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))


# ══════════════════════════════════════════════════════════════════════════
#  API : Utilisateur connecté
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/auth/api/me")
def api_me():
    if "user_id" not in session:
        return jsonify({"error": "Non authentifié"}), 401
    perms = auth_db.get_permissions(session.get("user_role", "spectator"))
    return jsonify({
        "id": session["user_id"],
        "username": session["username"],
        "role": session["user_role"],
        "display_name": session.get("display_name", ""),
        "permissions": perms,
    })


# ══════════════════════════════════════════════════════════════════════════
#  API : Gestion des utilisateurs
# ══════════════════════════════════════════════════════════════════════════

@auth_bp.route("/auth/api/users", methods=["GET"])
@role_required("admin", "admin_centre")
def api_list_users():
    users = auth_db.list_users()
    return jsonify({"users": users})


@auth_bp.route("/auth/api/users", methods=["POST"])
@role_required("admin", "admin_centre")
def api_create_user():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")
    display_name = data.get("display_name", "")

    if not username or not password:
        return jsonify({"error": "Username et mot de passe requis"}), 400

    if role not in auth_db.ROLES:
        return jsonify({"error": f"Rôle invalide. Choix : {auth_db.ROLES}"}), 400

    # Vérifier que le créateur a le droit de créer ce rôle
    creator_role = session.get("user_role", "")
    creator_perms = auth_db.get_permissions(creator_role)
    if role not in creator_perms.get("can_create_roles", []):
        return jsonify({"error": f"Vous ne pouvez pas créer un {role}"}), 403

    uid = auth_db.create_user(
        username=username,
        password=password,
        role=role,
        display_name=display_name,
        created_by=session.get("username", ""),
    )
    if uid is None:
        return jsonify({"error": "Ce nom d'utilisateur existe déjà"}), 409

    return jsonify({"ok": True, "id": uid}), 201


@auth_bp.route("/auth/api/users/<int:user_id>", methods=["PUT"])
@role_required("admin", "admin_centre")
def api_update_user(user_id):
    data = request.get_json() or {}
    target = auth_db.get_user(user_id)
    if not target:
        return jsonify({"error": "Utilisateur non trouvé"}), 404

    creator_role = session.get("user_role", "")

    # admin_centre ne peut pas modifier un admin
    if creator_role == "admin_centre" and target["role"] == "admin":
        return jsonify({"error": "Vous ne pouvez pas modifier un admin"}), 403

    # Vérifier changement de rôle
    new_role = data.get("role")
    if new_role and new_role != target["role"]:
        creator_perms = auth_db.get_permissions(creator_role)
        if new_role not in creator_perms.get("can_create_roles", []):
            return jsonify({"error": f"Vous ne pouvez pas attribuer le rôle {new_role}"}), 403

    auth_db.update_user(user_id, data)
    return jsonify({"ok": True})


@auth_bp.route("/auth/api/users/<int:user_id>", methods=["DELETE"])
@role_required("admin")
def api_delete_user(user_id):
    target = auth_db.get_user(user_id)
    if not target:
        return jsonify({"error": "Utilisateur non trouvé"}), 404

    auth_db.delete_user(user_id)
    return jsonify({"ok": True})
