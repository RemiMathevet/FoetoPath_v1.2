#!/usr/bin/env python3
"""
FoetoPath — Module d'authentification & gestion des utilisateurs.

Rôles :
  admin         Tous les droits. Crée / supprime tous les profils.
  admin_centre  Crée admin_centre et user. Accès complet aux cas.
  user          Crée et consulte les cas.
  spectator     Consulte les cas (lecture seule).

L'administrateur principal (Remi_Mathevet) est créé automatiquement
au premier lancement avec un mot de passe en dur.
"""

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# ── Hachage simple (SHA-256 + sel) ────────────────────────────────────────
# Pas besoin de bcrypt pour un usage intranet hospitalier.


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Retourne (hash_hex, salt_hex)."""
    if salt is None:
        salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return h, salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return h == stored_hash


# ── Rôles & permissions ──────────────────────────────────────────────────

ROLES = ("admin", "admin_centre", "user", "spectator")

# Matrice de permissions :
#   can_manage_users   : accéder à la page /admin/users
#   can_create_roles   : quels rôles ce rôle peut créer
#   can_delete_users   : peut supprimer des utilisateurs
#   can_write_cases    : créer / modifier des cas
#   can_delete_cases   : supprimer des cas
#   can_read_cases     : consulter les cas

PERMISSIONS = {
    "admin": {
        "can_manage_users": True,
        "can_create_roles": ["admin_centre", "user", "spectator"],
        "can_delete_users": True,
        "can_write_cases": True,
        "can_delete_cases": True,
        "can_read_cases": True,
    },
    "admin_centre": {
        "can_manage_users": True,
        "can_create_roles": ["admin_centre", "user", "spectator"],
        "can_delete_users": False,
        "can_write_cases": True,
        "can_delete_cases": True,
        "can_read_cases": True,
    },
    "user": {
        "can_manage_users": False,
        "can_create_roles": [],
        "can_delete_users": False,
        "can_write_cases": True,
        "can_delete_cases": False,
        "can_read_cases": True,
    },
    "spectator": {
        "can_manage_users": False,
        "can_create_roles": [],
        "can_delete_users": False,
        "can_write_cases": False,
        "can_delete_cases": False,
        "can_read_cases": True,
    },
}


def get_permissions(role: str) -> dict:
    return PERMISSIONS.get(role, PERMISSIONS["spectator"])


# ── Base de données ──────────────────────────────────────────────────────

_db_path: str | None = None


def init_db(data_dir: str) -> str:
    """Initialise la table users dans auth.db et crée l'admin par défaut."""
    global _db_path
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    _db_path = str(p / "auth.db")

    con = sqlite3.connect(_db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            salt        TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'spectator',
            display_name TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now')),
            created_by  TEXT DEFAULT '',
            last_login  TEXT DEFAULT '',
            active      INTEGER DEFAULT 1
        )
    """)
    con.commit()

    # ── Admin par défaut ──
    row = con.execute(
        "SELECT id FROM users WHERE username = ?", ("Remi_Mathevet",)
    ).fetchone()
    if not row:
        pw_hash, salt = _hash_password("R1m2E3a4")
        con.execute(
            "INSERT INTO users (username, password, salt, role, display_name, created_by) "
            "VALUES (?, ?, ?, 'admin', 'Rémi Mathevet', 'system')",
            ("Remi_Mathevet", pw_hash, salt),
        )
        con.commit()

    con.close()
    return _db_path


def _conn():
    return sqlite3.connect(_db_path)


def _row_to_dict(row, cursor) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


# ── Authentification ─────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> dict | None:
    """Vérifie les identifiants. Retourne le user dict ou None."""
    con = _conn()
    cur = con.execute(
        "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
    )
    row = cur.fetchone()
    if not row:
        con.close()
        return None
    user = _row_to_dict(row, cur)
    con.close()

    if not _verify_password(password, user["password"], user["salt"]):
        return None

    # Mettre à jour last_login
    con = _conn()
    con.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user["id"]),
    )
    con.commit()
    con.close()

    # Ne pas retourner le hash/salt
    user.pop("password", None)
    user.pop("salt", None)
    return user


# ── CRUD Utilisateurs ────────────────────────────────────────────────────

def create_user(username: str, password: str, role: str,
                display_name: str = "", created_by: str = "") -> int | None:
    """Crée un utilisateur. Retourne l'id ou None si le username existe déjà."""
    if role not in ROLES:
        return None
    pw_hash, salt = _hash_password(password)
    con = _conn()
    try:
        cur = con.execute(
            "INSERT INTO users (username, password, salt, role, display_name, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, pw_hash, salt, role, display_name, created_by),
        )
        con.commit()
        uid = cur.lastrowid
        con.close()
        return uid
    except sqlite3.IntegrityError:
        con.close()
        return None


def update_user(user_id: int, data: dict) -> bool:
    """Met à jour un utilisateur (display_name, role, active).
    Si 'password' est dans data, le re-hashe."""
    allowed = {"display_name", "role", "active"}
    fields = {k: v for k, v in data.items() if k in allowed}

    con = _conn()
    if "password" in data and data["password"]:
        pw_hash, salt = _hash_password(data["password"])
        fields["password"] = pw_hash
        fields["salt"] = salt

    if not fields:
        con.close()
        return False

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    con.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    con.commit()
    con.close()
    return True


def delete_user(user_id: int) -> bool:
    con = _conn()
    cur = con.execute("DELETE FROM users WHERE id = ?", (user_id,))
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    return deleted


def get_user(user_id: int) -> dict | None:
    con = _conn()
    cur = con.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        con.close()
        return None
    user = _row_to_dict(row, cur)
    con.close()
    user.pop("password", None)
    user.pop("salt", None)
    return user


def get_user_by_username(username: str) -> dict | None:
    con = _conn()
    cur = con.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        con.close()
        return None
    user = _row_to_dict(row, cur)
    con.close()
    user.pop("password", None)
    user.pop("salt", None)
    return user


def list_users() -> list[dict]:
    con = _conn()
    cur = con.execute("SELECT * FROM users ORDER BY role, username")
    rows = cur.fetchall()
    users = [_row_to_dict(r, cur) for r in rows]
    con.close()
    for u in users:
        u.pop("password", None)
        u.pop("salt", None)
    return users
