#!/usr/bin/env python3
"""
FoetoPath — Blueprint Placenta.

Routes pour :
  - Servir la PWA (/pwa/placentas/)
  - API CRUD cas placenta
  - Réception des données + photos depuis la PWA
  - Viewer photos
  - Génération CR Jinja2
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, Response, abort, jsonify, render_template, request, send_file, send_from_directory

log = logging.getLogger(__name__)

import placenta_db as pdb
from config import PHOTO_EXTENSIONS, SLIDE_EXTENSIONS, MIME_MAP
from utils.file_ops import (
    list_photos_in, list_slides_in, generate_thumbnail,
    validate_photo_path, get_photo_mime,
)

placenta_bp = Blueprint(
    "placenta",
    __name__,
    url_prefix="/placenta",
)


# ── Auth : protéger les routes API (pas les PWA) ────────────────────────

@placenta_bp.before_request
def _require_login():
    """Routes /placenta/api/* nécessitent une connexion.
    Les routes /placenta/pwa/* restent libres (accès mobile)."""
    from flask import session, request as req, jsonify
    # PWA : pas d'auth requise
    if req.path.startswith("/placenta/pwa/"):
        return None
    # API submit depuis PWA : pas d'auth (le téléphone envoie direct)
    if req.path == "/placenta/api/cases/submit":
        return None
    if "user_id" not in session:
        if req.path.startswith("/placenta/api/"):
            return jsonify({"error": "Non authentifié"}), 401
        return None  # Les pages non-API sont servies par admin_bp
    # Mutations : vérifier droits
    role = session.get("user_role", "spectator")
    if req.method in ("POST", "PUT", "DELETE") and req.path.startswith("/placenta/api/"):
        from auth_db import get_permissions
        perms = get_permissions(role)
        if req.method == "DELETE" and not perms.get("can_delete_cases"):
            return jsonify({"error": "Suppression non autorisée"}), 403
        if req.method in ("POST", "PUT") and not perms.get("can_write_cases"):
            return jsonify({"error": "Lecture seule"}), 403


# ── Servir les fichiers PWA ──────────────────────────────────────────────

PWA_DIR = Path(__file__).parent / "pwa" / "placentas"


@placenta_bp.route("/pwa/<path:filename>")
def pwa_static(filename):
    """Sert les fichiers statiques de la PWA placenta."""
    return send_from_directory(str(PWA_DIR), filename)


# ── Routes PWA (sans préfixe /placenta pour un accès direct) ─────────────
# Ces routes sont enregistrées séparément dans app.py via un second blueprint


# ── API : Check dossier ──────────────────────────────────────────────────

@placenta_bp.route("/api/cases/check")
def api_check_case():
    """Vérifie si un dossier placenta existe."""
    numero = request.args.get("numero", "")
    if not numero:
        return jsonify({"exists": False})
    case = pdb.get_case_by_numero(numero)
    return jsonify({
        "exists": case is not None,
        "case_id": case["id"] if case else None,
    })


# ── API : Soumission depuis PWA (FormData avec photos) ──────────────────

@placenta_bp.route("/api/cases/submit", methods=["POST"])
def api_submit():
    """
    Réception des données depuis la PWA.
    FormData attendu :
      - json_data: string JSON (macro_frais ou tranches_section)
      - dossier: numéro de dossier
      - module: nom du module (macro_frais | tranches_section)
      - photos: fichiers image (multiples)
    """
    json_str = request.form.get("json_data", "{}")
    dossier = request.form.get("dossier", "")
    module = request.form.get("module", "macro_frais")

    if not dossier:
        return jsonify({"error": "Numéro de dossier requis"}), 400

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return jsonify({"error": "JSON invalide"}), 400

    # Identifier l'utilisateur (session Flask ou champ formulaire PWA)
    from flask import session as flask_session
    submit_user = flask_session.get("username", "") or request.form.get("user", "pwa")

    # Créer ou mettre à jour le cas
    if module == "macro_frais":
        case_id = pdb.import_from_macro_frais_json(data, user=submit_user)
    else:
        # tranches_section ou autre module
        existing = pdb.get_case_by_numero(dossier)
        if existing:
            case_id = existing["id"]
        else:
            case_id = pdb.create_case({"numero_dossier": dossier}, user=submit_user)
        pdb.save_module_data(case_id, module, data, user=submit_user)

    if not case_id:
        return jsonify({"error": "Impossible de créer le cas"}), 500

    # Sauvegarder les photos
    photos_saved = 0
    photos_dir = _get_photos_dir(dossier)

    for photo_file in request.files.getlist("photos"):
        if photo_file and photo_file.filename:
            filename = photo_file.filename
            filepath = photos_dir / filename
            photo_file.save(str(filepath))

            # Extraire la clé photo du nom de fichier
            # Convention: {dossier}_{key}.jpg → key
            stem = Path(filename).stem
            if stem.startswith(dossier + "_"):
                photo_key = stem[len(dossier) + 1:]
            else:
                photo_key = stem

            pdb.save_photo(
                case_id=case_id,
                photo_key=photo_key,
                filename=filename,
                label=photo_key.replace("_", " ").title(),
                module=module,
                file_path=str(filepath),
                size_bytes=filepath.stat().st_size if filepath.exists() else 0,
                user=submit_user,
            )
            photos_saved += 1

    # Mettre à jour le chemin photos
    pdb.update_case(case_id, {"dossier_photos_path": str(photos_dir)}, user=submit_user)

    # ── Sauvegarde JSON sur disque ──
    _save_json_to_disk(dossier, module, data)

    return jsonify({
        "ok": True,
        "case_id": case_id,
        "module": module,
        "photos_saved": photos_saved,
    })


def _get_photos_dir(dossier: str) -> Path:
    """Retourne le répertoire photos pour un dossier, le crée si besoin."""
    data_root = _data_root()
    photos_dir = data_root / "Placentas" / dossier / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    return photos_dir


def _data_root() -> Path:
    """Retourne le répertoire racine des données."""
    # Essayer le setting global, sinon ~/Documents/FoetoPath
    try:
        import db as foetopath_db
        root = foetopath_db.get_setting("data_root")
        if root:
            return Path(root)
    except Exception:
        log.debug("Failed to load data_root setting, using default", exc_info=True)
    return Path(os.path.expanduser("~/Documents/FoetoPath"))


def _save_json_to_disk(dossier: str, module: str, data: dict):
    """Écrit le JSON du module sur disque dans le dossier du cas."""
    case_dir = _data_root() / "Placentas" / dossier
    case_dir.mkdir(parents=True, exist_ok=True)
    json_path = case_dir / f"{dossier}_{module}.json"
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        log.debug("Failed to save JSON to disk: %s", json_path, exc_info=True)  # silencieux — le JSON disque est un backup, pas critique


# ── API : CRUD Cases ─────────────────────────────────────────────────────

@placenta_bp.route("/api/cases", methods=["GET"])
def api_list_cases():
    """Liste les cas placenta."""
    statut = request.args.get("statut")
    search = request.args.get("q")
    cases = pdb.list_cases(statut=statut, search=search)

    for c in cases:
        modules = pdb.get_all_modules(c["id"])
        c["module_count"] = len(modules)
        c["modules_filled"] = list(modules.keys())
        c["photos"] = pdb.get_photos(c["id"])

    return jsonify({"cases": cases, "total": len(cases)})


@placenta_bp.route("/api/cases", methods=["POST"])
def api_create_case():
    """Crée un nouveau cas placenta."""
    data = request.get_json()
    if not data or not data.get("numero_dossier"):
        return jsonify({"error": "Numéro de dossier requis"}), 400

    existing = pdb.get_case_by_numero(data["numero_dossier"])
    if existing:
        pdb.update_case(existing["id"], data)
        return jsonify({"id": existing["id"], "message": "Cas mis à jour", "merged": True})

    try:
        case_id = pdb.create_case(data)
        return jsonify({"id": case_id, "message": "Cas créé"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@placenta_bp.route("/api/cases/<int:case_id>", methods=["GET"])
def api_get_case(case_id):
    """Détails complets d'un cas placenta."""
    case = pdb.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    case["modules"] = pdb.get_all_modules(case_id)
    case["photos"] = pdb.get_photos(case_id)
    return jsonify(case)


@placenta_bp.route("/api/cases/<int:case_id>", methods=["PUT"])
def api_update_case(case_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données requises"}), 400
    case = pdb.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404
    pdb.update_case(case_id, data)
    return jsonify({"message": "Cas mis à jour"})


@placenta_bp.route("/api/cases/<int:case_id>", methods=["DELETE"])
def api_delete_case(case_id):
    if pdb.delete_case(case_id):
        return jsonify({"message": "Cas supprimé"})
    return jsonify({"error": "Cas non trouvé"}), 404


# ── API : Modules ────────────────────────────────────────────────────────

@placenta_bp.route("/api/cases/<int:case_id>/modules/<module_name>", methods=["GET"])
def api_get_module(case_id, module_name):
    data = pdb.get_module_data(case_id, module_name)
    if data is None:
        return jsonify({"error": "Module non trouvé"}), 404
    return jsonify({"module": module_name, "data": data})


@placenta_bp.route("/api/cases/<int:case_id>/modules/<module_name>", methods=["PUT"])
def api_save_module(case_id, module_name):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données requises"}), 400
    case = pdb.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404
    pdb.save_module_data(case_id, module_name, data)
    return jsonify({"message": f"Module {module_name} sauvegardé"})


# ── API : Photos ─────────────────────────────────────────────────────────

# PHOTO_EXTENSIONS et MIME_MAP importés depuis config.py


@placenta_bp.route("/api/cases/<int:case_id>/photos", methods=["GET"])
def api_list_photos(case_id):
    module = request.args.get("module")
    photos = pdb.get_photos(case_id, module=module)
    return jsonify({"photos": photos, "total": len(photos)})


@placenta_bp.route("/api/photos/list", methods=["POST"])
def api_photos_list():
    """
    Liste les photos d'un cas placenta par catégorie, pour le sidebar du viewer.
    Retourne un format compatible avec le viewer (mêmes clés que l'endpoint foetus).
    """
    body = request.get_json() or {}
    case_id = body.get("case_id")
    if not case_id:
        return jsonify({"error": "case_id requis"}), 400

    case = pdb.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    photos_path = case.get("dossier_photos_path", "")
    db_photos = pdb.get_photos(case_id)

    # Catégoriser les photos
    categories = {}

    # Photos macro frais
    frais_photos = [p for p in db_photos if p.get("module") == "macro_frais"]
    if frais_photos:
        categories["frais"] = {
            "icon": "&#x1F7E2;",
            "label": "Macro frais",
            "photos": [{"path": p["file_path"], "label": p.get("label") or p.get("photo_key", ""),
                         "name": p.get("photo_key", ""), "filename": p.get("filename", "")}
                        for p in frais_photos if p.get("file_path")]
        }

    # Photos tranches / lésions
    tranches_photos = [p for p in db_photos if p.get("module") == "tranches_section"]
    if tranches_photos:
        categories["tranches"] = {
            "icon": "&#x1F52A;",
            "label": "Tranches & lésions",
            "photos": [{"path": p["file_path"], "label": p.get("label") or p.get("photo_key", ""),
                         "name": p.get("photo_key", ""), "filename": p.get("filename", "")}
                        for p in tranches_photos if p.get("file_path")]
        }

    # Si pas de photos en DB, scanner le dossier
    if not categories and photos_path:
        pp = Path(photos_path)
        photos_sub = pp / "photos"
        scan_dir = str(photos_sub) if photos_sub.is_dir() else str(pp)
        all_photos = _list_photos_in(scan_dir)

        frais = []
        tranches = []
        for ph in all_photos:
            name_lower = ph["name"].lower()
            if any(k in name_lower for k in ("tr_", "tranche", "lesion", "section")):
                tranches.append(ph)
            else:
                frais.append(ph)

        if frais:
            categories["frais"] = {
                "icon": "&#x1F7E2;",
                "label": "Macro frais",
                "photos": [{"path": p["path"], "label": p["filename"],
                             "name": p["name"], "filename": p["filename"]} for p in frais]
            }
        if tranches:
            categories["tranches"] = {
                "icon": "&#x1F52A;",
                "label": "Tranches & lésions",
                "photos": [{"path": p["path"], "label": p["filename"],
                             "name": p["name"], "filename": p["filename"]} for p in tranches]
            }

    return jsonify({"categories": categories, "case_id": case_id})


@placenta_bp.route("/api/photo/serve")
def api_serve_photo():
    path = request.args.get("path", "")
    ok, err = validate_photo_path(path)
    if not ok:
        return jsonify({"error": err}), 404 if "trouvée" in err else 403
    return send_file(path, mimetype=get_photo_mime(path))


@placenta_bp.route("/api/photo/thumbnail")
def api_photo_thumbnail():
    path = request.args.get("path", "")
    w = int(request.args.get("w", 160))
    h = int(request.args.get("h", 160))
    return Response(generate_thumbnail(path, w, h), mimetype="image/jpeg")


# SLIDE_EXTENSIONS importé depuis config.py


# _list_slides_in et _list_photos_in → utils.file_ops
_list_slides_in = list_slides_in
_list_photos_in = list_photos_in


@placenta_bp.route("/api/cases/<int:case_id>/pairing", methods=["GET"])
def api_pairing(case_id):
    """
    Construit le tableau d'appairage pour un cas placenta :
    - Photos macro (frais + tranches de section)
    - Lames correspondantes
    """
    case = pdb.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    photos_path = case.get("dossier_photos_path", "")
    lames_path = case.get("dossier_lames_path", "")

    # Chercher le dossier lames si pas défini
    if not lames_path:
        try:
            import db as foetopath_db
            slides_root = foetopath_db.get_setting("slides_root")
            if slides_root:
                candidate = Path(slides_root) / case["numero_dossier"]
                if candidate.is_dir():
                    lames_path = str(candidate)
        except Exception:
            log.debug("Failed to load slides_root setting", exc_info=True)

    # Si toujours pas trouvé, chercher un sous-dossier "lames" dans le dossier du cas
    if not lames_path:
        case_dir = _data_root() / "Placentas" / case["numero_dossier"]
        candidate = case_dir / "lames"
        if candidate.is_dir():
            lames_path = str(candidate)

    # Collecter les photos
    photos_frais = []
    photos_tranches = []

    if photos_path and os.path.isdir(photos_path):
        pp = Path(photos_path)
        # Si c'est le dossier du cas lui-même, chercher photos/
        photos_sub = pp / "photos" if not (pp / "photos").is_dir() else pp / "photos"
        if photos_sub.is_dir():
            all_photos = _list_photos_in(str(photos_sub))
        else:
            all_photos = _list_photos_in(str(pp))

        # Séparer frais vs tranches par convention de nommage
        for ph in all_photos:
            name_lower = ph["name"].lower()
            if any(k in name_lower for k in ("tr_", "tranche", "lesion", "section")):
                photos_tranches.append(ph)
            else:
                photos_frais.append(ph)

    # Collecter les lames
    slides = []
    if lames_path and os.path.isdir(lames_path):
        slides = _list_slides_in(lames_path)

    # Construire l'appairage par ID (première partie du nom de fichier)
    organ_ids = set()
    photo_map_frais = {}
    photo_map_tranches = {}
    slide_map = {}

    for ph in photos_frais:
        key = ph["name"].split("_")[0].upper() if "_" in ph["name"] else ph["name"].upper()
        photo_map_frais.setdefault(key, []).append(ph)
        organ_ids.add(key)

    for ph in photos_tranches:
        key = ph["name"].split("_")[0].upper() if "_" in ph["name"] else ph["name"].upper()
        photo_map_tranches.setdefault(key, []).append(ph)
        organ_ids.add(key)

    for sl in slides:
        key = sl["name"].split("_")[0].upper() if "_" in sl["name"] else sl["name"].upper()
        slide_map.setdefault(key, []).append(sl)
        organ_ids.add(key)

    pairing_rows = []
    for organ_id in sorted(organ_ids):
        pairing_rows.append({
            "organ_id": organ_id,
            "photos_frais": photo_map_frais.get(organ_id, []),
            "photos_tranches": photo_map_tranches.get(organ_id, []),
            "slides": slide_map.get(organ_id, []),
        })

    return jsonify({
        "case_id": case_id,
        "numero_dossier": case["numero_dossier"],
        "pairing": pairing_rows,
        "stats": {
            "photos_frais": len(photos_frais),
            "photos_tranches": len(photos_tranches),
            "slides": len(slides),
        },
        "paths": {
            "photos": photos_path,
            "lames": lames_path,
        },
        "all_photos_frais": photos_frais,
        "all_photos_tranches": photos_tranches,
        "all_slides": slides,
    })


# ── API : Sync dossier local ────────────────────────────────────────────

@placenta_bp.route("/api/sync", methods=["POST"])
def api_sync():
    """
    Scanne le dossier Placentas/ et importe les cas.

    Structure attendue :
      data_root/Placentas/
      ├── 26P4061/
      │   ├── macro_frais.json
      │   ├── tranches_section.json
      │   └── photos/
      └── 26P4099/
          └── ...
    """
    data = request.get_json() or {}
    scan_path = data.get("source_dir")

    if not scan_path:
        scan_path = str(_data_root() / "Placentas")

    source = Path(scan_path)
    if not source.is_dir():
        return jsonify({"error": f"Dossier introuvable : {scan_path}"}), 400

    stats = {"scanned": 0, "imported": 0, "updated": 0, "photos": 0, "jsons": 0, "errors": 0}

    for entry in sorted(source.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        stats["scanned"] += 1

        case_id_str = entry.name
        existing = pdb.get_case_by_numero(case_id_str)

        # Detecter dossier lames
        lames_dir = entry / "lames"
        lames_path = str(lames_dir) if lames_dir.is_dir() else ""
        if not lames_path:
            try:
                import db as foetopath_db
                slides_root = foetopath_db.get_setting("slides_root")
                if slides_root:
                    candidate = Path(slides_root) / case_id_str
                    if candidate.is_dir():
                        lames_path = str(candidate)
            except Exception:
                log.debug("Failed to load slides_root setting for case", exc_info=True)

        update_data = {"dossier_photos_path": str(entry)}
        if lames_path:
            update_data["dossier_lames_path"] = lames_path

        if existing:
            case_id = existing["id"]
            pdb.update_case(case_id, update_data)
            stats["updated"] += 1
        else:
            try:
                case_id = pdb.create_case({
                    "numero_dossier": case_id_str,
                    **update_data,
                })
                stats["imported"] += 1
            except Exception:
                log.warning("Failed to create case for %s", case_id_str, exc_info=True)
                stats["errors"] += 1
                continue

        # Importer les JSON
        for f in sorted(entry.iterdir()):
            if f.is_file() and f.suffix.lower() == ".json":
                stem = f.stem
                if stem.startswith(case_id_str + "_"):
                    module_name = stem[len(case_id_str) + 1:]
                else:
                    module_name = stem
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        json_data = json.load(fh)
                    pdb.save_module_data(case_id, module_name, json_data)
                    stats["jsons"] += 1
                except Exception:
                    log.warning("Failed to import JSON module %s", module_name, exc_info=True)
                    stats["errors"] += 1

        # Compter les photos
        photos_dir = entry / "photos"
        if photos_dir.is_dir():
            for ph in photos_dir.iterdir():
                if ph.is_file() and ph.suffix.lower() in PHOTO_EXTENSIONS:
                    try:
                        if ph.stat().st_size >= 1024:
                            stats["photos"] += 1
                    except OSError:
                        pass

    return jsonify({
        "status": "ok",
        "message": (
            f"Scan terminé : {stats['scanned']} dossier(s), "
            f"{stats['imported']} créé(s), {stats['updated']} mis à jour, "
            f"{stats['jsons']} JSON, {stats['photos']} photos"
        ),
        "stats": stats,
    })


# ── API : Génération CR ─────────────────────────────────────────────────

@placenta_bp.route("/api/cr/templates", methods=["GET"])
def api_cr_templates():
    import placenta_cr_templates as pcr
    return jsonify({"templates": pcr.get_available_templates()})


@placenta_bp.route("/api/cr/templates/versions", methods=["GET"])
def api_cr_template_versions():
    """Retourne les versions et changelogs de tous les templates CR placenta."""
    import placenta_cr_templates as pcr
    return jsonify(pcr.get_all_versions_info())


@placenta_bp.route("/api/cr/templates/<template_id>/changelog", methods=["GET"])
def api_cr_template_changelog(template_id):
    """Retourne le changelog d'un template placenta spécifique."""
    import placenta_cr_templates as pcr
    changelog = pcr.get_template_changelog(template_id)
    if not changelog:
        return jsonify({"error": f"Template '{template_id}' non trouvé"}), 404
    return jsonify({"template_id": template_id, "changelog": changelog})


@placenta_bp.route("/api/cases/<int:case_id>/cr/generate", methods=["POST"])
def api_cr_generate(case_id):
    """Génère un CR placenta à partir d'un template Jinja2."""
    import placenta_cr_templates as pcr

    case = pdb.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    body = request.get_json() or {}
    template_id = body.get("template_id", "standard")

    all_modules = pdb.get_all_modules(case_id)
    modules_data = {name: mod["data"] for name, mod in all_modules.items()}

    context = pcr.build_cr_context(case, modules_data)
    cr_text = pcr.render_cr(template_id, context)

    pdb.save_module_data(case_id, "last_cr", {
        "template_id": template_id,
        "text": cr_text,
    })

    return jsonify({
        "template_id": template_id,
        "text": cr_text,
    })


# ── API : Export JSON ─────────────────────────────────────────────────

@placenta_bp.route("/api/cases/<int:case_id>/export-json", methods=["POST"])
def api_export_json(case_id):
    """Exporte toutes les données d'un cas en JSON sur disque."""
    case = pdb.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    dossier = case["numero_dossier"]
    all_modules = pdb.get_all_modules(case_id)

    # Écrire chaque module
    for name, mod in all_modules.items():
        _save_json_to_disk(dossier, name, mod["data"])

    # Écrire un fichier récap admin
    case_dir = _data_root() / "Placentas" / dossier
    case_dir.mkdir(parents=True, exist_ok=True)
    admin_data = {k: v for k, v in case.items() if k not in ("modules", "photos")}
    admin_path = case_dir / f"{dossier}_admin.json"
    try:
        with open(admin_path, "w", encoding="utf-8") as f:
            json.dump(admin_data, f, ensure_ascii=False, indent=2)
    except Exception:
        log.debug("Failed to save admin data to disk: %s", admin_path, exc_info=True)

    return jsonify({
        "ok": True,
        "dossier": dossier,
        "modules_exported": list(all_modules.keys()),
        "path": str(case_dir),
    })

