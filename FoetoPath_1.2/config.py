#!/usr/bin/env python3
"""
FoetoPath — Configuration centralisée.

Toutes les constantes partagées entre app.py, admin_bp.py, placenta_bp.py,
db.py et placenta_db.py sont définies ici.
"""

# ── Extensions fichiers ───────────────────────────────────────────────────

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tga"}

SLIDE_EXTENSIONS = {
    ".mrxs", ".svs", ".ndpi", ".tiff", ".tif",
    ".scn", ".bif", ".vms", ".vmu",
}

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tga": "image/x-tga",
}

# ── Viewer / OpenSeadragon ────────────────────────────────────────────────

TILE_SIZE = 254
TILE_OVERLAP = 1
TILE_FORMAT = "jpeg"
TILE_QUALITY = 80
THUMBNAIL_SIZE = (300, 300)

# ── Modules connus ────────────────────────────────────────────────────────

KNOWN_MODULES_FOETUS = [
    "pre_exam", "externe", "biometries", "interne",
    "imagerie", "prelevements", "placenta", "neuropath", "radio", "synthese",
]

KNOWN_MODULES_PLACENTA = [
    "macro_frais", "tranches_section", "micro", "cr", "computed",
]

# ── Dossiers macro (foetus) ──────────────────────────────────────────────

MACRO_FOLDER_TYPES = ["photos", "frais", "autopsie", "fixe", "neuropath"]

# ── Paramètres par défaut (table settings, foetus DB) ────────────────────

DEFAULT_SETTINGS = {
    "slides_root": "",
    "data_root": "",
    "viewer_port": "5000",
    "auto_sync": "false",
}
