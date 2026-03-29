#!/usr/bin/env python3
"""
FoetoPath — Module base de données SQLite hybride (fœtus).

Schéma :
  - cases          : données admin stables (colonnes SQL classiques)
  - module_data    : blob JSON par module par cas (pour modules en évolution)
  - macro_folders  : statut des sous-dossiers macro (frais, autopsie, fixe, neuropath)
  - settings       : configuration applicative (chemin lames, etc.)

Utilise db_core.DatabaseManager pour les opérations communes.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from config import KNOWN_MODULES_FOETUS, MACRO_FOLDER_TYPES, DEFAULT_SETTINGS
from db_core import DatabaseManager, _now, _row_to_dict

log = logging.getLogger(__name__)

# ── Instance partagée ────────────────────────────────────────────────────

_mgr = DatabaseManager(
    db_name="foetopath.db",
    cases_table="cases",
    modules_table="module_data",
)

# Alias de compatibilité
KNOWN_MODULES = KNOWN_MODULES_FOETUS


# ── Schéma SQL ───────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_dossier      TEXT UNIQUE NOT NULL,
    case_id_externe     TEXT,

    -- Identité mère
    nom_mere            TEXT,
    prenom_mere         TEXT,
    nom_naissance_mere  TEXT,
    ddn_mere            TEXT,

    -- Identité fœtus
    nom_foetus          TEXT,
    prenom_foetus       TEXT,
    ddn_foetus          TEXT,
    sexe                TEXT,

    -- Contexte clinique
    terme_issue         TEXT,
    type_issue          TEXT,
    indication_examen   TEXT,
    service_demandeur   TEXT,
    medecin_referent    TEXT,
    date_deces          TEXT,
    date_examen         TEXT,
    lieu_residence      TEXT,
    ville_maternite     TEXT,

    -- Workflow
    numero_placenta     TEXT,
    examen_placenta     INTEGER DEFAULT 0,
    acte_clinique       INTEGER DEFAULT 0,
    acte_imagerie       INTEGER DEFAULT 0,
    acte_anapath        INTEGER DEFAULT 0,
    acte_interne        INTEGER DEFAULT 0,
    acte_virtopsie      INTEGER DEFAULT 0,

    -- Chemins
    dossier_macro_path  TEXT,
    dossier_lames_path  TEXT,

    -- Attribution & suivi
    assigned_to         TEXT,
    created_by          TEXT,
    modified_by         TEXT,

    -- État du dossier
    statut              TEXT DEFAULT 'en_cours',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS module_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    module_name TEXT NOT NULL,
    data_json   TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL,
    UNIQUE(case_id, module_name)
);

CREATE TABLE IF NOT EXISTS macro_folders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    folder_type     TEXT NOT NULL,
    folder_path     TEXT,
    photo_count     INTEGER DEFAULT 0,
    verified        INTEGER DEFAULT 0,
    last_scan       TEXT,
    UNIQUE(case_id, folder_type)
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_numero ON cases(numero_dossier);
CREATE INDEX IF NOT EXISTS idx_cases_id_ext ON cases(case_id_externe);
CREATE INDEX IF NOT EXISTS idx_module_case  ON module_data(case_id, module_name);
CREATE INDEX IF NOT EXISTS idx_macro_case   ON macro_folders(case_id);
"""


# ── Init & Connexion (délégué à db_core) ─────────────────────────────────

def init_db(base_dir: str | Path) -> Path:
    """Initialise la BDD dans le répertoire donné. Crée les tables si absentes."""
    db_path = _mgr.set_path(base_dir)
    with _mgr.connect() as conn:
        conn.executescript(_SCHEMA)
        _ensure_default_settings(conn)
        _migrate_schema(conn)
    return db_path


def get_db_path() -> Path:
    return _mgr.get_db_path()


# Exposer _connect pour le code legacy qui l'utilise directement
_connect = _mgr.connect


# ── Migrations & Settings init ───────────────────────────────────────────

def _ensure_default_settings(conn):
    """Insère les paramètres par défaut s'ils n'existent pas."""
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v)
        )


def _migrate_schema(conn):
    """Ajoute les colonnes manquantes pour les BDD existantes (migration safe)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}
    migrations = [
        ("assigned_to", "TEXT"),
        ("created_by", "TEXT"),
        ("modified_by", "TEXT"),
    ]
    for col_name, col_type in migrations:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE cases ADD COLUMN {col_name} {col_type}")


# ── CRUD Cases ───────────────────────────────────────────────────────────

def create_case(data: dict) -> int:
    """Crée un nouveau cas. Retourne l'ID."""
    now = _now()
    fields = [
        "numero_dossier", "case_id_externe",
        "nom_mere", "prenom_mere", "nom_naissance_mere", "ddn_mere",
        "lieu_residence",
        "nom_foetus", "prenom_foetus", "ddn_foetus", "sexe",
        "terme_issue", "type_issue", "indication_examen",
        "service_demandeur", "medecin_referent",
        "date_deces", "date_examen",
        "ville_maternite", "numero_placenta", "examen_placenta",
        "acte_clinique", "acte_imagerie", "acte_anapath", "acte_interne", "acte_virtopsie",
        "dossier_macro_path", "dossier_lames_path",
        "assigned_to", "created_by", "modified_by",
        "statut", "notes",
    ]
    values = {f: data.get(f) for f in fields}
    values["created_at"] = now
    values["updated_at"] = now
    if not values.get("statut"):
        values["statut"] = "en_cours"

    cols = ", ".join(values.keys())
    placeholders = ", ".join(["?"] * len(values))

    with _mgr.connect() as conn:
        cur = conn.execute(
            f"INSERT INTO cases ({cols}) VALUES ({placeholders})",
            list(values.values()),
        )
        return cur.lastrowid


def update_case(case_id: int, data: dict) -> bool:
    """Met à jour un cas existant."""
    allowed = {
        "numero_dossier", "case_id_externe",
        "nom_mere", "prenom_mere", "nom_naissance_mere", "ddn_mere",
        "lieu_residence",
        "nom_foetus", "prenom_foetus", "ddn_foetus", "sexe",
        "terme_issue", "type_issue", "indication_examen",
        "service_demandeur", "medecin_referent",
        "date_deces", "date_examen",
        "ville_maternite", "numero_placenta", "examen_placenta",
        "acte_clinique", "acte_imagerie", "acte_anapath", "acte_interne", "acte_virtopsie",
        "dossier_macro_path", "dossier_lames_path",
        "assigned_to", "created_by", "modified_by",
        "statut", "notes",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)

    with _mgr.connect() as conn:
        conn.execute(
            f"UPDATE cases SET {set_clause} WHERE id = ?",
            list(updates.values()) + [case_id],
        )
        return True


def get_case(case_id: int) -> Optional[dict]:
    return _mgr.get_case(case_id)


def get_case_by_numero(numero: str) -> Optional[dict]:
    return _mgr.get_case_by_numero(numero)


def list_cases(statut: str = None, search: str = None) -> list[dict]:
    return _mgr.list_cases(
        statut=statut, search=search,
        search_fields=["numero_dossier", "nom_mere", "case_id_externe"],
    )


def delete_case(case_id: int) -> bool:
    return _mgr.delete_case(case_id)


# ── Module Data (délégué à db_core) ─────────────────────────────────────

def save_module_data(case_id: int, module_name: str, data: dict) -> bool:
    return _mgr.save_module_data(case_id, module_name, data)


def get_module_data(case_id: int, module_name: str) -> Optional[dict]:
    return _mgr.get_module_data(case_id, module_name)


def get_all_modules(case_id: int) -> dict[str, dict]:
    return _mgr.get_all_modules(case_id)


# ── Macro Folders (spécifique foetus) ────────────────────────────────────

def scan_macro_folders(case_id: int, base_path: str) -> list[dict]:
    """Scanne les sous-dossiers d'un cas et met à jour la BDD."""
    base = Path(base_path)
    results = []
    now = _now()
    photo_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

    with _mgr.connect() as conn:
        for ftype in MACRO_FOLDER_TYPES:
            folder = base / ftype
            exists = folder.is_dir()
            photo_count = 0
            if exists:
                for f in folder.iterdir():
                    if f.is_file() and f.suffix.lower() in photo_exts:
                        try:
                            if f.stat().st_size >= 1024:
                                photo_count += 1
                        except OSError:
                            log.debug("File stat error: %s", f, exc_info=True)

            conn.execute(
                """INSERT INTO macro_folders (case_id, folder_type, folder_path, photo_count, last_scan)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(case_id, folder_type)
                   DO UPDATE SET folder_path = excluded.folder_path,
                                 photo_count = excluded.photo_count,
                                 last_scan = excluded.last_scan""",
                (case_id, ftype, str(folder) if exists else None, photo_count, now),
            )
            results.append({
                "type": ftype,
                "exists": exists,
                "path": str(folder) if exists else None,
                "photo_count": photo_count,
            })
    return results


def get_macro_folders(case_id: int) -> list[dict]:
    with _mgr.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM macro_folders WHERE case_id = ? ORDER BY folder_type",
            (case_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


# ── Settings (spécifique foetus) ─────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with _mgr.connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with _mgr.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            (key, value),
        )


def get_all_settings() -> dict[str, str]:
    with _mgr.connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


# ── Import JSON ──────────────────────────────────────────────────────────

def import_case_from_json(json_path: str | Path) -> Optional[int]:
    """Importe un cas depuis un fichier JSON pré-examen."""
    path = Path(json_path)
    if not path.is_file():
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    admin = data.get("case_admin", data)
    numero = admin.get("numero_dossier")
    if not numero:
        return None

    existing = get_case_by_numero(numero)
    if existing:
        case_id = existing["id"]
        update_case(case_id, admin)
    else:
        case_id = create_case(admin)

    for key in ["atcd_maternels", "grossesse_en_cours", "examens_prenataux", "atcd_obstetricaux"]:
        if key in data:
            save_module_data(case_id, key, data[key])

    return case_id
