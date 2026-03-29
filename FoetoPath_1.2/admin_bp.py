#!/usr/bin/env python3
"""
FoetoPath — Blueprint Admin.

Routes pour :
  - Gestion des cas (CRUD)
  - Sync téléphone → PC
  - Scan des dossiers macro
  - Appairage lames / macro
  - Paramètres
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from collections import OrderedDict
from flask import Blueprint, jsonify, render_template, request, send_file

log = logging.getLogger(__name__)

import db
from auth_bp import login_required, role_required, can_write, can_delete
from config import PHOTO_EXTENSIONS, SLIDE_EXTENSIONS, MIME_MAP
from utils.file_ops import (
    list_photos_in, list_slides_in, generate_thumbnail,
    validate_photo_path, get_photo_mime, cat_info, photo_label,
)

admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/admin",
)


# ── Auth : protéger toutes les routes du blueprint ──────────────────────
from flask import redirect, session, url_for

@admin_bp.before_request
def _require_login():
    """Toutes les routes /admin/* nécessitent une connexion."""
    from flask import session, request, jsonify, redirect, url_for
    # Exempter l'endpoint PWA submit (les téléphones n'ont pas de session)
    if request.path == "/admin/api/pwa/submit":
        return None
    if request.path == "/admin/api/pwa/load":
        return None
    if request.path == "/admin/api/pwa/photo":
        return None
    if "user_id" not in session:
        if request.path.startswith("/admin/api/"):
            return jsonify({"error": "Non authentifié"}), 401
        return redirect(url_for("auth.login_page", next=request.path))

    role = session.get("user_role", "spectator")

    # Spectateur : interdire l'accès aux paramètres (page + API PUT)
    if role == "spectator":
        if request.path == "/admin/settings":
            if request.path.startswith("/admin/api/"):
                return jsonify({"error": "Accès refusé"}), 403
            return redirect(url_for("hub"))
        if request.path == "/admin/api/settings" and request.method == "PUT":
            return jsonify({"error": "Accès refusé"}), 403

    # Écriture : refuser spectator sur les mutations
    if request.method in ("POST", "PUT", "DELETE") and request.path.startswith("/admin/api/"):
        from auth_db import get_permissions
        perms = get_permissions(role)
        if request.method == "DELETE" and not perms.get("can_delete_cases"):
            return jsonify({"error": "Suppression non autorisée"}), 403
        if request.method in ("POST", "PUT") and not perms.get("can_write_cases"):
            return jsonify({"error": "Lecture seule"}), 403


# ── Page principale ────────────────────────────────────────────────────────

@admin_bp.route("/")
def admin_index():
    """Page d'administration principale (fœtus)."""
    return render_template("admin.html")


@admin_bp.route("/placenta")
def admin_placenta():
    """Page d'administration placentas."""
    return render_template("admin_placenta.html")


@admin_bp.route("/users")
def admin_users():
    """Page de gestion des utilisateurs (protégée par before_request + JS côté client)."""
    return render_template("users.html")


@admin_bp.route("/settings")
def admin_settings():
    """Page de paramètres globaux."""
    return render_template("settings.html")


# ── API Cases CRUD ─────────────────────────────────────────────────────────

@admin_bp.route("/api/cases", methods=["GET"])
def api_list_cases():
    """Liste tous les cas avec filtres optionnels."""
    statut = request.args.get("statut")
    search = request.args.get("q")
    cases = db.list_cases(statut=statut, search=search)

    # Enrichir avec le nombre de modules remplis
    for c in cases:
        modules = db.get_all_modules(c["id"])
        c["module_count"] = len(modules)
        c["modules_filled"] = list(modules.keys())
        # Récupérer les dossiers macro
        macro = db.get_macro_folders(c["id"])
        c["macro_folders"] = macro

    return jsonify({"cases": cases, "total": len(cases)})


@admin_bp.route("/api/cases", methods=["POST"])
def api_create_case():
    """Crée un nouveau cas, ou fusionne avec un cas existant (ex: créé par sync)."""
    data = request.get_json()
    if not data or not data.get("numero_dossier"):
        return jsonify({"error": "Numéro de dossier requis"}), 400

    # Tracking utilisateur
    username = session.get("username", "")
    if username:
        data.setdefault("created_by", username)
        data["modified_by"] = username

    existing = db.get_case_by_numero(data["numero_dossier"])
    if existing:
        # Fusionner : le cas existe (probablement auto-créé par sync), on enrichit
        db.update_case(existing["id"], data)
        return jsonify({"id": existing["id"], "message": "Cas existant mis à jour (fusion)", "merged": True}), 200

    try:
        case_id = db.create_case(data)
        return jsonify({"id": case_id, "message": "Cas créé"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/cases/<int:case_id>", methods=["GET"])
def api_get_case(case_id):
    """Détails d'un cas avec toutes ses données modules."""
    case = db.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    case["modules"] = db.get_all_modules(case_id)
    case["macro_folders"] = db.get_macro_folders(case_id)
    return jsonify(case)


@admin_bp.route("/api/cases/<int:case_id>", methods=["PUT"])
def api_update_case(case_id):
    """Met à jour un cas."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données requises"}), 400

    case = db.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    # Tracking utilisateur
    username = session.get("username", "")
    if username:
        data["modified_by"] = username

    db.update_case(case_id, data)
    return jsonify({"message": "Cas mis à jour", "id": case_id})


@admin_bp.route("/api/cases/<int:case_id>", methods=["DELETE"])
def api_delete_case(case_id):
    """Supprime un cas et toutes ses données associées."""
    if db.delete_case(case_id):
        return jsonify({"message": "Cas supprimé"})
    return jsonify({"error": "Cas non trouvé"}), 404


# ── API Module Data ────────────────────────────────────────────────────────

@admin_bp.route("/api/cases/<int:case_id>/modules/<module_name>", methods=["GET"])
def api_get_module(case_id, module_name):
    """Récupère les données d'un module."""
    data = db.get_module_data(case_id, module_name)
    if data is None:
        return jsonify({"error": "Module non trouvé"}), 404
    return jsonify({"module": module_name, "data": data})


@admin_bp.route("/api/cases/<int:case_id>/modules/<module_name>", methods=["PUT"])
def api_save_module(case_id, module_name):
    """Enregistre les données d'un module."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données requises"}), 400

    case = db.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    db.save_module_data(case_id, module_name, data)
    return jsonify({"message": f"Module {module_name} sauvegardé"})


# ── Scan dossiers macro ───────────────────────────────────────────────────

@admin_bp.route("/api/cases/<int:case_id>/scan-macro", methods=["POST"])
def api_scan_macro(case_id):
    """Scanne les sous-dossiers macro d'un cas."""
    from services.sync import scan_macro_for_case
    try:
        result = scan_macro_for_case(case_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# ── Appairage lames / macro ───────────────────────────────────────────────

# SLIDE_EXTENSIONS et PHOTO_EXTENSIONS importés depuis config.py


@admin_bp.route("/api/cases/<int:case_id>/pairing", methods=["GET"])
def api_pairing(case_id):
    """
    Construit le tableau d'appairage pour un cas :
    - Photos macro frais
    - Photos macro fixé (= cassettes)
    - Lames correspondantes
    - Contrôle cassettes vs lames
    """
    from services.pairing import build_pairing_table
    try:
        result = build_pairing_table(case_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@admin_bp.route("/api/sync", methods=["POST"])
def api_sync():
    """
    Scanne le dossier FoetoPath local et importe/fusionne les cas en BDD.
    """
    from services.sync import run_sync
    data = request.get_json() or {}
    scan_path = data.get("source_dir") or db.get_setting("data_root")

    if not scan_path:
        return jsonify({"error": "Aucun répertoire source configuré. Renseignez 'data_root' dans les paramètres."}), 400

    try:
        result = run_sync(scan_path)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Liste utilisateurs (pour dropdown attribution) ───────────────────────

@admin_bp.route("/api/users/list", methods=["GET"])
def api_users_list():
    """Liste les utilisateurs actifs (pour le dropdown d'attribution des cas)."""
    import auth_db
    users = auth_db.list_users()
    # Retourner uniquement les infos nécessaires pour le dropdown
    return jsonify({
        "users": [
            {"id": u["id"], "username": u["username"], "display_name": u.get("display_name", ""), "role": u["role"]}
            for u in users if u.get("active", 1)
        ]
    })


# ── Settings ──────────────────────────────────────────────────────────────

@admin_bp.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(db.get_all_settings())


@admin_bp.route("/api/settings", methods=["PUT"])
def api_save_settings():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données requises"}), 400
    for k, v in data.items():
        db.set_setting(k, str(v))
    return jsonify({"message": "Paramètres sauvegardés"})


@admin_bp.route("/api/settings/test-path", methods=["POST"])
def api_test_path():
    """Vérifie si un chemin existe et est accessible en écriture."""
    data = request.get_json() or {}
    raw = data.get("path", "").strip()
    if not raw:
        return jsonify({"exists": False, "writable": False, "error": "Chemin vide"})
    p = Path(os.path.expanduser(raw))
    exists = p.is_dir()
    writable = exists and os.access(str(p), os.W_OK)
    return jsonify({
        "exists": exists,
        "writable": writable,
        "resolved": str(p),
    })


# ── Calculs biométriques ──────────────────────────────────────────────────

@admin_bp.route("/api/cases/<int:case_id>/compute", methods=["POST"])
def api_compute(case_id):
    """
    Lance les calculs biométriques pour un cas.
    Lit les modules macro_frais et macro_autopsie, calcule DS + ratios,
    sauvegarde les résultats dans le module 'computed_biometrics',
    et retourne le rapport textuel Jinja2.
    """
    import biometrics

    case = db.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    # Récupérer les données modules
    macro_frais = db.get_module_data(case_id, "macro_frais")
    macro_autopsie = db.get_module_data(case_id, "macro_autopsie")

    if not macro_frais and not macro_autopsie:
        return jsonify({"error": "Aucune donnée macro_frais ni macro_autopsie pour ce cas"}), 400

    # Terme SA — chercher dans macro_frais en priorité
    #   Structure réelle : macro_frais.terme.sa = 24
    #   Fallback : macro_frais.biometries.terme_sa, puis case.terme_issue
    terme = None
    maceration = 0

    if macro_frais:
        # 1. macro_frais.terme.sa (structure réelle de l'app)
        terme_obj = macro_frais.get("terme")
        if isinstance(terme_obj, dict):
            terme = terme_obj.get("sa")
        elif isinstance(terme_obj, (int, float)):
            terme = int(terme_obj)

        # 2. Fallback : dans biometries
        if not terme:
            bio = macro_frais.get("biometries", macro_frais.get("biometrie", {}))
            terme = bio.get("terme_sa") or bio.get("terme")

        # Macération : macro_frais.maceration.maroun_score
        mac_obj = macro_frais.get("maceration")
        if isinstance(mac_obj, dict):
            maceration = mac_obj.get("maroun_score", 0) or 0
        elif isinstance(mac_obj, (int, float)):
            maceration = int(mac_obj)

    # 3. Fallback : terme_issue du dossier admin ("24 SA + 3j" → 24)
    if not terme and case.get("terme_issue"):
        import re
        m = re.match(r"(\d+)", str(case["terme_issue"]))
        if m:
            terme = int(m.group(1))

    # 4. Override depuis le body de la requête (si passé manuellement)
    body = request.get_json() or {}
    terme = body.get("terme_sa") or terme
    maceration = body.get("maceration_grade", maceration)

    if not terme:
        return jsonify({"error": "Terme SA non trouvé. Renseignez-le dans le formulaire ou passez terme_sa dans le body."}), 400

    terme = int(terme)

    # Calculer
    results = biometrics.compute_all(
        terme_sa=terme,
        macro_frais=macro_frais,
        macro_autopsie=macro_autopsie,
        maceration_grade=maceration,
    )

    # Générer le rapport texte
    report_text = biometrics.render_report(results)

    # Sauvegarder en BDD
    db.save_module_data(case_id, "computed_biometrics", {
        "results": results,
        "report_text": report_text,
    })

    return jsonify({
        "results": results,
        "report_text": report_text,
    })


# ── Ollama — Démarrage, listing modèles, génération ───────────────────────

@admin_bp.route("/api/ollama/status", methods=["POST"])
def api_ollama_status():
    """
    Vérifie si Ollama tourne, le démarre si besoin, puis liste les modèles.
    """
    from services.ollama import check_ollama_status
    try:
        result = check_ollama_status()
        return jsonify(result)
    except RuntimeError as e:
        if "n'est pas installé" in str(e):
            return jsonify({
                "error": str(e),
                "running": False,
                "models": [],
            }), 500
        elif "pas encore prêt" in str(e):
            return jsonify({
                "error": str(e),
                "running": False,
                "started": True,
                "models": [],
            }), 503
        else:
            return jsonify({
                "error": str(e),
                "running": False,
                "models": [],
            }), 500


@admin_bp.route("/api/cases/<int:case_id>/ollama", methods=["POST"])
def api_ollama(case_id):
    """
    Envoie le rapport biométrique à Ollama pour reformulation
    en texte médical rédigé.
    """
    from services.ollama import run_ollama_biometrics

    case = db.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    computed = db.get_module_data(case_id, "computed_biometrics")
    if not computed or not computed.get("report_text"):
        return jsonify({"error": "Aucun rapport calculé. Lancez d'abord le calcul biométrique."}), 400

    report_text = computed["report_text"]
    body = request.get_json() or {}
    model = body.get("model") or db.get_setting("ollama_model", "mistral")

    try:
        result = run_ollama_biometrics(case_id, report_text, model)
        return jsonify(result)
    except RuntimeError as e:
        if "non accessible" in str(e):
            return jsonify({"error": str(e)}), 502
        else:
            return jsonify({"error": str(e)}), 500


# ── Foekinator (diagnostic bayésien) ─────────────────────────────────────

@admin_bp.route("/api/foekinator/databases", methods=["GET"])
def api_foekinator_databases():
    """Liste les bases de données Foekinator disponibles (fichiers JSON)."""
    foek_dir = Path(__file__).parent / "Foekinator"
    databases = []
    if foek_dir.is_dir():
        for p in sorted(foek_dir.iterdir()):
            if p.suffix.lower() == ".json" and p.is_file():
                try:
                    import json as _json
                    data = _json.loads(p.read_text(encoding="utf-8"))
                    meta = data.get("_meta", {})
                    databases.append({
                        "id": p.stem,
                        "filename": p.name,
                        "name": meta.get("name", p.stem.replace("_", " ").title()),
                        "version": meta.get("version", "?"),
                        "diseases_count": meta.get("diseases_count", len(data.get("diseases", []))),
                        "hpo_terms_count": meta.get("hpo_terms_count", len(data.get("hpo_terms", {}))),
                    })
                except Exception:
                    log.debug("Failed to load database metadata", exc_info=True)
                    databases.append({"id": p.stem, "filename": p.name, "name": p.stem, "version": "?", "diseases_count": 0, "hpo_terms_count": 0})
    return jsonify({"databases": databases})


@admin_bp.route("/api/foekinator/load", methods=["GET"])
def api_foekinator_load():
    """Charge une base de données Foekinator par son ID (stem du fichier)."""
    db_id = request.args.get("id", "").strip()
    if not db_id:
        return jsonify({"error": "ID de base requis"}), 400

    foek_dir = Path(__file__).parent / "Foekinator"
    filepath = foek_dir / (db_id + ".json")
    if not filepath.is_file():
        return jsonify({"error": "Base non trouvée"}), 404

    import json as _json
    data = _json.loads(filepath.read_text(encoding="utf-8"))
    return jsonify(data)


# ── Microscopie (grilles de lecture) ──────────────────────────────────────

@admin_bp.route("/api/micro/templates", methods=["GET"])
def api_micro_templates():
    """Liste les templates de grilles de lecture microscopie."""
    templates_dir = Path(__file__).parent / "templates" / "micro"
    templates = []
    if templates_dir.is_dir():
        for p in sorted(templates_dir.iterdir()):
            if p.suffix.lower() == ".json" and p.is_file():
                try:
                    import json as _json
                    data = _json.loads(p.read_text(encoding="utf-8"))
                    templates.append({
                        "id": p.stem,
                        "name": data.get("name", p.stem),
                        "description": data.get("description", ""),
                        "icon": data.get("icon", "&#128203;"),
                    })
                except Exception:
                    log.debug("Failed to load template metadata", exc_info=True)
                    templates.append({"id": p.stem, "name": p.stem, "description": "", "icon": "&#128203;"})
    return jsonify({"templates": templates})


# ── CR (Comptes-rendus) ───────────────────────────────────────────────────

@admin_bp.route("/api/cr/templates", methods=["GET"])
def api_cr_templates():
    """Liste les templates CR disponibles avec leur version."""
    import cr_templates
    return jsonify({"templates": cr_templates.get_available_templates()})


@admin_bp.route("/api/cr/templates/versions", methods=["GET"])
def api_cr_template_versions():
    """Retourne les versions et changelogs de tous les templates CR."""
    import cr_templates
    return jsonify(cr_templates.get_all_versions_info())


@admin_bp.route("/api/cr/templates/<template_id>/changelog", methods=["GET"])
def api_cr_template_changelog(template_id):
    """Retourne le changelog d'un template spécifique."""
    import cr_templates
    changelog = cr_templates.get_template_changelog(template_id)
    if not changelog:
        return jsonify({"error": f"Template '{template_id}' non trouvé"}), 404
    return jsonify({"template_id": template_id, "changelog": changelog})


@admin_bp.route("/api/cases/<int:case_id>/cr/generate", methods=["POST"])
def api_cr_generate(case_id):
    """
    Génère un CR à partir d'un template Jinja2.
    Body: {"template_id": "soffoet"}
    """
    import cr_templates
    import biometrics

    case = db.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    body = request.get_json() or {}
    template_id = body.get("template_id", "soffoet")

    # Récupérer tous les modules
    all_modules = db.get_all_modules(case_id)
    modules_data = {name: mod["data"] for name, mod in all_modules.items()}

    # Récupérer les calculs biométriques (s'ils existent)
    computed = modules_data.get("computed_biometrics", {})

    # Construire le contexte et rendre
    if template_id == "neuropath":
        context = cr_templates.build_neuropath_context(case, modules_data)
    elif template_id == "radio":
        context = cr_templates.build_radio_context(case, modules_data)
    else:
        context = cr_templates.build_cr_context(case, modules_data, computed)
    cr_text = cr_templates.render_cr(template_id, context)

    # Sauvegarder le dernier CR généré
    db.save_module_data(case_id, "last_cr", {
        "template_id": template_id,
        "text": cr_text,
    })

    return jsonify({
        "template_id": template_id,
        "text": cr_text,
    })


@admin_bp.route("/api/cases/<int:case_id>/cr/ollama", methods=["POST"])
def api_cr_ollama(case_id):
    """
    Envoie un texte CR à Ollama pour rédaction en langage naturel médical.
    Body: {"text": "...", "model": "mistral"}
    """
    from services.ollama import run_ollama_cr

    case = db.get_case(case_id)
    if not case:
        return jsonify({"error": "Cas non trouvé"}), 404

    body = request.get_json() or {}
    source_text = body.get("text", "")

    if not source_text:
        # Fallback: dernier CR généré
        last_cr = db.get_module_data(case_id, "last_cr")
        if last_cr:
            source_text = last_cr.get("text", "")
    if not source_text:
        return jsonify({"error": "Aucun texte CR à reformuler. Générez d'abord un CR."}), 400

    model = body.get("model") or db.get_setting("ollama_model", "mistral")

    try:
        result = run_ollama_cr(case_id, source_text, model)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


# ── Import JSON files ─────────────────────────────────────────────────────

@admin_bp.route("/api/import-json", methods=["POST"])
def api_import_json():
    """Import un fichier JSON pré-examen directement (upload ou path)."""
    data = request.get_json()
    json_path = data.get("path")

    if json_path and os.path.isfile(json_path):
        case_id = db.import_case_from_json(json_path)
        if case_id:
            return jsonify({"message": "Importé", "case_id": case_id})
        return jsonify({"error": "Impossible d'importer (numéro dossier manquant ?)"}), 400

    # Import depuis le body directement
    json_data = data.get("data")
    if json_data:
        admin = json_data.get("case_admin", json_data)
        numero = admin.get("numero_dossier")
        if not numero:
            return jsonify({"error": "Numéro de dossier requis"}), 400

        existing = db.get_case_by_numero(numero)
        if existing:
            case_id = existing["id"]
            db.update_case(case_id, admin)
        else:
            case_id = db.create_case(admin)

        # Sauvegarder les modules
        for key in ["atcd_maternels", "grossesse_en_cours", "examens_prenataux", "atcd_obstetricaux"]:
            if key in json_data:
                db.save_module_data(case_id, key, json_data[key])

        return jsonify({"message": "Importé", "case_id": case_id})

    return jsonify({"error": "Aucune donnée à importer"}), 400


# ── Viewer Photos macro ────────────────────────────────────────────────────

@admin_bp.route("/viewer-photos")
def viewer_photos():
    """Page viewer photos macro pour un cas."""
    case_id = request.args.get("case_id")
    photos_path = request.args.get("path", "")
    return render_template("viewer_photos.html", case_id=case_id, photos_path=photos_path)


@admin_bp.route("/api/photos/list", methods=["POST"])
def api_photos_list():
    """Liste les photos d'un cas dans l'ordre exact des JSON modules.

    Ordre : macro_frais.photos → macro_autopsie.photos → (futur: fixé, neuropath)
    Les extras sont classés selon leur position (entre photo_ = ext, entre p_ = autopsie).
    """
    data = request.get_json() or {}
    folder = data.get("path", "")
    case_id = data.get("case_id")

    # Récupérer le cas et les modules
    json_sections = []  # [(section_label, icon, photos_list)]
    if case_id:
        case = db.get_case(int(case_id))
        if case and case.get("dossier_macro_path") and not folder:
            folder = case["dossier_macro_path"]

        # macro_frais → examen externe + anomalies + extras
        macro_frais = db.get_module_data(int(case_id), "macro_frais")
        if macro_frais and macro_frais.get("photos"):
            json_sections.append(("macro_frais", macro_frais["photos"]))

        # macro_autopsie → autopsie
        macro_autopsie = db.get_module_data(int(case_id), "macro_autopsie")
        if macro_autopsie and macro_autopsie.get("photos"):
            json_sections.append(("macro_autopsie", macro_autopsie["photos"]))

        # macro_fixe → fixé (tranches de section, lésions)
        macro_fixe = db.get_module_data(int(case_id), "macro_fixe")
        if macro_fixe and macro_fixe.get("photos"):
            json_sections.append(("macro_fixe", macro_fixe["photos"]))

        # neuropath → neuropathologie
        neuropath = db.get_module_data(int(case_id), "neuropath")
        if neuropath:
            # neuropath stores photo_keys as flat list of strings, convert to photos format
            np_photos = neuropath.get("photos", [])
            if not np_photos and neuropath.get("photo_keys"):
                np_photos = [{"key": k, "label": _photo_label(k)} for k in neuropath["photo_keys"]]
            if np_photos:
                json_sections.append(("neuropath", np_photos))

    if not folder or not os.path.isdir(folder):
        return jsonify({"error": "Dossier introuvable"}), 400

    # ── Scanner les fichiers sur disque ──
    files_on_disk = {}  # key (sans préfixe dossier) → photo dict
    for check_dir in [folder, os.path.join(folder, "photos")]:
        if os.path.isdir(check_dir):
            for p in list_photos_in(check_dir):
                stem = p["name"].lower()
                # Retirer le préfixe dossier (ex: "26p4381_photo_face" → "photo_face")
                parts = stem.split("_", 1)
                key = parts[1] if len(parts) > 1 else stem
                files_on_disk[key] = p
                # Garder aussi le stem complet comme fallback
                files_on_disk[stem] = p

    # ── Construire les catégories dans l'ordre du JSON ──
    categories = OrderedDict()
    matched_keys = set()

    for section_name, photo_list in json_sections:
        # Le contexte est fixé par la section JSON, pas par le préfixe de clé
        section_context_map = {
            "macro_frais": "externe",
            "macro_autopsie": "autopsie",
            "macro_fixe": "fixe",
            "neuropath": "neuropath",
        }
        context = section_context_map.get(section_name, "autre")

        for entry in photo_list:
            key = entry.get("key", "").lower()
            label = entry.get("label", "")

            # Déterminer la catégorie
            if key.startswith("anomal"):
                cat = "anomalie"
            elif key.startswith("extra") or key.startswith("xp_"):
                cat = f"extra_{context}"
            elif section_name == "macro_fixe":
                if key.startswith("p_tranche"):
                    cat = "fixe"
                elif key.startswith("p_lesion"):
                    cat = "fixe_lesion"
                else:
                    cat = "fixe"
            else:
                cat = context  # utilise le contexte de la section

            # Matcher avec le fichier sur disque
            photo_file = files_on_disk.get(key)
            if not photo_file:
                continue  # pas de fichier correspondant

            matched_keys.add(key)

            # Ajouter la catégorie si première fois
            cat_info = _cat_info(cat)
            if cat not in categories:
                categories[cat] = {"label": cat_info[0], "icon": cat_info[1], "photos": []}

            photo_file["label"] = label or _photo_label(key)
            categories[cat]["photos"].append(photo_file)

    # ── Photos sur disque non matchées dans le JSON → "Autres" ──
    for key, p in files_on_disk.items():
        if key not in matched_keys and p.get("filename") and not any(
            p["filename"] == ep["filename"]
            for cat_data in categories.values()
            for ep in cat_data["photos"]
        ):
            if "autre" not in categories:
                categories["autre"] = {"label": "Autres", "icon": "📁", "photos": []}
            p["label"] = _photo_label(key)
            categories["autre"]["photos"].append(p)

    total = sum(len(c["photos"]) for c in categories.values())

    # Forcer les anomalies en premier, puis le reste dans l'ordre du JSON
    ordered = OrderedDict()
    if "anomalie" in categories:
        ordered["anomalie"] = categories["anomalie"]
    for k, v in categories.items():
        if k != "anomalie":
            ordered[k] = v

    return jsonify({
        "path": folder,
        "total": total,
        "categories": ordered,
    })


# _cat_info → utils.file_ops.cat_info
_cat_info = cat_info


# _photo_label → utils.file_ops.photo_label
_photo_label = photo_label


# ── Utilitaires photos ────────────────────────────────────────────────────

@admin_bp.route("/api/photo/serve")
def api_serve_photo():
    """Sert une photo pour preview."""
    path = request.args.get("path", "")
    ok, err = validate_photo_path(path)
    if not ok:
        return jsonify({"error": err}), 404 if "trouvée" in err else 403
    return send_file(path, mimetype=get_photo_mime(path))


@admin_bp.route("/api/photo/thumbnail")
def api_photo_thumbnail():
    """Génère un thumbnail pour une photo."""
    from flask import Response
    path = request.args.get("path", "")
    w = int(request.args.get("w", 160))
    h = int(request.args.get("h", 160))
    return Response(generate_thumbnail(path, w, h), mimetype="image/jpeg")


# ── API PWA Fœtus — Submit / Load / Photo ────────────────────────────────

@admin_bp.route("/api/pwa/submit", methods=["POST"])
def api_pwa_submit():
    """
    Réception des données depuis la PWA fœtus.
    FormData attendu :
      - json_data: string JSON (macro_frais, macro_autopsie, macro_fixe, neuropath)
      - dossier: numéro de dossier
      - module: nom du module
      - photo_<key>: fichiers image (multiples, un par clé)
      - b64_<key>: photos en base64 dataURL (alternative aux fichiers)
    """
    from flask import session as flask_session
    import base64

    json_str = request.form.get("json_data", "{}")
    dossier = request.form.get("dossier", "").strip()
    module = request.form.get("module", "macro_frais")

    if not dossier:
        return jsonify({"error": "Numéro de dossier requis"}), 400

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return jsonify({"error": "JSON invalide"}), 400

    submit_user = flask_session.get("username", "") or request.form.get("user", "pwa")

    # ── Trouver ou créer le cas ──
    existing = db.get_case_by_numero(dossier)
    if existing:
        case_id = existing["id"]
        # Tracker qui modifie le cas via PWA
        db.update_case(case_id, {"modified_by": submit_user})
    else:
        case_id = db.create_case({
            "numero_dossier": dossier,
            "sexe": data.get("sexe"),
            "terme_issue": str(data.get("terme", {}).get("sa", "")) if data.get("terme") else None,
            "created_by": submit_user,
            "modified_by": submit_user,
        })

    # ── Sauvegarder les données du module (avec tracking utilisateur) ──
    data["_submitted_by"] = submit_user
    data["_submitted_at"] = datetime.now(timezone.utc).isoformat()
    data["_submitted_via"] = "pwa"
    db.save_module_data(case_id, module, data)

    # ── Déterminer le répertoire de stockage ──
    # Priorité : data_root configuré > dossier_macro_path existant > fallback à côté de la DB
    data_root = db.get_setting("data_root")
    if data_root:
        base_dir = Path(data_root) / "Foetus" / dossier
    elif existing and existing.get("dossier_macro_path"):
        base_dir = Path(existing["dossier_macro_path"])
    else:
        # Fallback : créer un dossier Foetus à côté de la BDD
        base_dir = db.get_db_path().parent / "Foetus" / dossier

    case_dir = base_dir / "photos"
    case_dir.mkdir(parents=True, exist_ok=True)

    # Sauvegarder aussi le JSON brut
    json_path = base_dir / f"{dossier}_{module}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Mettre à jour le chemin macro du cas
    db.update_case(case_id, {"dossier_macro_path": str(base_dir)})

    # ── Sauvegarder les photos sur disque ──
    photos_saved = 0

    # Photos depuis FormData (fichiers)
    for key in request.files:
        if key.startswith("photo_"):
            photo_key = key[6:]  # Retirer "photo_"
            fobj = request.files[key]
            if fobj and fobj.filename:
                ext = Path(fobj.filename).suffix or ".jpg"
                photo_path = case_dir / f"{dossier}_{photo_key}{ext}"
                fobj.save(str(photo_path))
                photos_saved += 1

    # Photos depuis FormData (base64 dataURL)
    for key in request.form:
        if key.startswith("b64_"):
            photo_key = key[4:]  # Retirer "b64_"
            b64_data = request.form[key]
            if "," in b64_data:
                header, b64_content = b64_data.split(",", 1)
                ext = ".jpg"
                if "png" in header:
                    ext = ".png"
                elif "webp" in header:
                    ext = ".webp"
            else:
                b64_content = b64_data
                ext = ".jpg"
            try:
                img_bytes = base64.b64decode(b64_content)
                photo_path = case_dir / f"{dossier}_{photo_key}{ext}"
                with open(photo_path, "wb") as f:
                    f.write(img_bytes)
                photos_saved += 1
            except Exception:
                log.warning("Failed to save photo for %s", dossier, exc_info=True)

    # Mettre à jour les macro_folders
    try:
        db.scan_macro_folders(case_id, str(base_dir))
    except Exception:
        log.warning("Failed to scan macro folders for case %s", case_id, exc_info=True)

    return jsonify({
        "status": "ok",
        "case_id": case_id,
        "module": module,
        "photos_saved": photos_saved,
        "message": f"Module {module} sauvegardé pour {dossier}",
    })


@admin_bp.route("/api/pwa/load", methods=["GET"])
def api_pwa_load():
    """
    Charge les données d'un cas pour la PWA fœtus.
    Params: dossier=<numero>, module=<nom_module> (optionnel)
    Retourne le cas + données module + liste des photos disponibles.
    """
    dossier = request.args.get("dossier", "").strip()
    module = request.args.get("module")

    if not dossier:
        return jsonify({"error": "Numéro de dossier requis"}), 400

    case = db.get_case_by_numero(dossier)
    if not case:
        return jsonify({"found": False}), 200

    result = {
        "found": True,
        "case_id": case["id"],
        "dossier": dossier,
        "terme_issue": case.get("terme_issue"),
    }

    if module:
        mod_data = db.get_module_data(case["id"], module)
        result["data"] = mod_data
    else:
        result["modules"] = db.get_all_modules(case["id"])

    # Liste des photos disponibles sur disque
    photo_list = []
    macro_path = case.get("dossier_macro_path", "")
    if macro_path:
        photos_dir = Path(macro_path) / "photos"
        if photos_dir.is_dir():
            for p in sorted(photos_dir.iterdir()):
                if p.is_file() and p.suffix.lower() in PHOTO_EXTENSIONS:
                    stem = p.stem.lower()
                    parts = stem.split("_", 1)
                    key = parts[1] if len(parts) > 1 else stem
                    photo_list.append({
                        "key": key,
                        "filename": p.name,
                        "path": str(p),
                    })

    result["photos_on_disk"] = photo_list
    return jsonify(result)


@admin_bp.route("/api/pwa/photo", methods=["GET"])
def api_pwa_photo():
    """Sert une photo pour la PWA par clé et dossier."""
    dossier = request.args.get("dossier", "").strip()
    key = request.args.get("key", "").strip()

    if not dossier or not key:
        return jsonify({"error": "Paramètres manquants"}), 400

    case = db.get_case_by_numero(dossier)
    if not case or not case.get("dossier_macro_path"):
        return jsonify({"error": "Cas non trouvé"}), 404

    photos_dir = Path(case["dossier_macro_path"]) / "photos"
    if not photos_dir.is_dir():
        return jsonify({"error": "Dossier photos introuvable"}), 404

    for p in photos_dir.iterdir():
        if p.is_file() and p.suffix.lower() in PHOTO_EXTENSIONS:
            stem = p.stem.lower()
            parts = stem.split("_", 1)
            file_key = parts[1] if len(parts) > 1 else stem
            if file_key == key.lower() or stem == f"{dossier.lower()}_{key.lower()}":
                mime_map = {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif",
                    ".bmp": "image/bmp", ".webp": "image/webp",
                }
                return send_file(str(p), mimetype=mime_map.get(p.suffix.lower(), "image/jpeg"))

    return jsonify({"error": "Photo non trouvée"}), 404
