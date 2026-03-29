#!/usr/bin/env python3
"""
FoetoPath — Templates Jinja2 pour les comptes-rendus.

Templates disponibles :
  - soffoet    : CR type SOFFOET (basé sur le modèle officiel)
  - court      : CR synthétique court
  - neuropath  : CR neuropathologique
  - radio      : CR radiologique

Chaque template reçoit un contexte construit par build_cr_context()
à partir des données du cas (admin + modules + calculs).

Les templates Jinja2 sont stockés dans templates/cr/ en tant que fichiers .jinja2
"""

from jinja2 import Template, Environment, FileSystemLoader
from typing import Optional
import os


# ══════════════════════════════════════════════════════════════════════════
# Jinja2 Environment pour charger les templates depuis les fichiers
# ══════════════════════════════════════════════════════════════════════════

_template_dir = os.path.join(os.path.dirname(__file__), "templates", "cr")
_jinja_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=False)


# ══════════════════════════════════════════════════════════════════════════
# Construction du contexte pour les templates
# ══════════════════════════════════════════════════════════════════════════

def build_cr_context(case: dict, modules: dict, computed: dict = None) -> dict:
    """
    Construit le contexte unifié pour les templates Jinja2.

    Args:
        case: données admin du cas (table cases)
        modules: dict {module_name: data} (tous les modules)
        computed: résultats des calculs biométriques (computed_biometrics)

    Returns:
        Dict prêt à passer aux templates
    """
    macro_frais = modules.get("macro_frais", {})
    macro_autopsie = modules.get("macro_autopsie", {})
    atcd_mat = modules.get("atcd_maternels", {})
    gross = modules.get("grossesse_en_cours", {})
    exam_pren = modules.get("examens_prenataux", {})

    bio = macro_frais.get("biometries", {})
    morpho = macro_frais.get("morphologie", {})
    terme = macro_frais.get("terme", {})

    # Calculs
    calc_bio = {}
    calc_org = {}
    calc_ind = {}
    calc_ratios = {}
    alertes = []
    if computed:
        results = computed.get("results", computed)
        calc_bio = results.get("biometries_gc", {}).get("mesures", {})
        calc_org = results.get("organes_gc", {}).get("organes", {})
        calc_ind = results.get("organes_individuels", {}).get("organes_pairs", {})
        calc_ratios = results.get("ratios", {})
        alertes = results.get("alertes", [])

    # Ouverture / autopsie
    ouverture = macro_autopsie.get("ouverture", {})
    voies_aeriennes = macro_autopsie.get("voies_aeriennes", {})
    thorax = macro_autopsie.get("thorax", {})
    coeur = macro_autopsie.get("coeur", {})
    poumons = macro_autopsie.get("poumons", {})
    digestif = macro_autopsie.get("digestif", {})
    retro = macro_autopsie.get("retroperitoine", {})
    neuro = macro_autopsie.get("neuro", {})
    prelevements = macro_autopsie.get("prelevements", {})
    macro_fixe = modules.get("macro_fixe", {})

    # ── Trophicité fœtale (basée sur DS du poids) ──
    trophicite = "non évaluable"
    masse_info = calc_bio.get("masse", {})
    if masse_info and masse_info.get("ds") is not None:
        ds_masse = masse_info["ds"]
        if ds_masse < -2:
            trophicite = "hypotrophe"
        elif ds_masse > 2:
            trophicite = "macrosome"
        else:
            trophicite = "eutrophe"

    # ── Agrégation de TOUTES les anomalies pour la conclusion ──
    all_anomalies = []

    # 1. Anomalies morphologiques externes (macro frais)
    for key, item in morpho.items():
        if isinstance(item, dict) and item.get("status") == "anormal":
            desc_parts = []
            if item.get("details"):
                desc_parts.extend(item["details"] if isinstance(item["details"], list) else [item["details"]])
            if item.get("text"):
                desc_parts.append(item["text"])
            label = key.replace("_", " ").capitalize()
            detail = ", ".join(desc_parts) if desc_parts else "anomalie non précisée"
            all_anomalies.append(f"{label} : {detail}")

    # 2. Alertes biométriques (organes hors normes)
    for a in alertes:
        all_anomalies.append(a)

    # 3. Anomalies internes (champs texte libres autopsie)
    if ouverture.get("ogi") and ouverture["ogi"].lower() not in ("normal", "normaux", "ras"):
        all_anomalies.append(f"OGI : {ouverture['ogi']}" + (f" — {ouverture['ogi_detail']}" if ouverture.get("ogi_detail") else ""))
    if voies_aeriennes.get("detail"):
        all_anomalies.append(f"Voies aériennes : {voies_aeriennes['detail']}")
    if thorax.get("tsa") and isinstance(thorax["tsa"], dict) and thorax["tsa"].get("etat") and thorax["tsa"]["etat"].lower() not in ("normaux", "normal", "ras"):
        all_anomalies.append(f"TSA : {thorax['tsa']['etat']}" + (f" — {thorax['tsa']['detail']}" if thorax["tsa"].get("detail") else ""))
    if coeur.get("og_retours"):
        all_anomalies.append(f"Retours veineux OG : {coeur['og_retours']}")
    if coeur.get("vg_ej") and isinstance(coeur["vg_ej"], dict) and coeur["vg_ej"].get("civ_diam"):
        all_anomalies.append(f"CIV : {coeur['vg_ej']['civ_diam']} mm")
    if coeur.get("vg_av") and isinstance(coeur["vg_av"], dict) and coeur["vg_av"].get("detail"):
        all_anomalies.append(f"Valve mitrale : {coeur['vg_av']['detail']}")
    if digestif.get("estomac") and isinstance(digestif["estomac"], dict) and digestif["estomac"].get("contenu"):
        all_anomalies.append(f"Contenu gastrique : {digestif['estomac']['contenu']}")
    if digestif.get("tube_dig") and isinstance(digestif["tube_dig"], dict) and digestif["tube_dig"].get("detail"):
        all_anomalies.append(f"Tube digestif : {digestif['tube_dig']['detail']}")
    if neuro.get("detail"):
        all_anomalies.append(f"Neuro : {neuro['detail']}")

    # 4. Lésions macro fixé
    fixe_organes = macro_fixe.get("organes", {})
    for org_id, org in fixe_organes.items():
        if isinstance(org, dict) and org.get("lesion_desc"):
            label = org_id.replace("_", " ").capitalize()
            all_anomalies.append(f"{label} (fixé) : {org['lesion_desc']}")

    # 5. Anomalies prénatales
    if exam_pren.get("anomalies_suspectees"):
        all_anomalies.append(f"Prénatal (suspectées) : {exam_pren['anomalies_suspectees']}")
    if exam_pren.get("anomalies_confirmees"):
        all_anomalies.append(f"Prénatal (confirmées) : {exam_pren['anomalies_confirmees']}")

    return {
        # Admin
        "case": case,
        "numero": case.get("numero_dossier", ""),
        "nom_mere": case.get("nom_mere", ""),
        "prenom_mere": case.get("prenom_mere", ""),
        "ddn_mere": case.get("ddn_mere", ""),
        "sexe": case.get("sexe") or macro_frais.get("sexe", ""),
        "type_issue": case.get("type_issue", ""),
        "terme_sa": terme.get("sa") if isinstance(terme, dict) else terme,
        "terme_j": terme.get("jours", 0) if isinstance(terme, dict) else 0,
        "date_deces": case.get("date_deces", ""),
        "date_examen": case.get("date_examen", ""),
        "indication": case.get("indication_examen", ""),
        "medecin": case.get("medecin_referent", ""),
        "service": case.get("service_demandeur", ""),

        # ATCD
        "atcd_mat": atcd_mat,
        "grossesse": gross,
        "exam_prenataux": exam_pren,

        # Macro frais
        "etat": macro_frais.get("etat", ""),
        "maceration": macro_frais.get("maceration", {}),
        "bio": bio,
        "morpho": morpho,
        "commentaire_frais": macro_frais.get("commentaire", ""),
        "anomalies_frais": macro_frais.get("anomalies", []),

        # Calculs biométriques
        "calc_bio": calc_bio,
        "calc_org": calc_org,
        "calc_ind": calc_ind,
        "calc_ratios": calc_ratios,
        "alertes": alertes,
        "lbwr": calc_ratios.get("_lbwr", {}),
        "trophicite": trophicite,
        "all_anomalies": all_anomalies,

        # Autopsie
        "ouverture": ouverture,
        "voies_aeriennes": voies_aeriennes,
        "thorax": thorax,
        "coeur": coeur,
        "poumons": poumons,
        "digestif": digestif,
        "retroperitoine": retro,
        "neuro": neuro,
        "prelevements": prelevements,
        "commentaire_autopsie": macro_autopsie.get("commentaire", ""),
        "macro_fixe": macro_fixe,

        # Photos
        "photos_frais": macro_frais.get("photos", []),
        "photos_autopsie": macro_autopsie.get("photos", []),
    }


# ══════════════════════════════════════════════════════════════════════════
# Helpers Jinja2
# ══════════════════════════════════════════════════════════════════════════

def _ds_text(calc_dict, key):
    """Formatte un résultat DS : 'valeur unité (±X.XX DS)'"""
    if not calc_dict or key not in calc_dict:
        return "#"
    m = calc_dict[key]
    return f"{m['valeur']:.1f} {m.get('unite', 'g')} ({m['ds']:+.2f} DS)"


def _morpho_text(morpho, key):
    """Extrait le texte d'un item morpho : normal ou description."""
    item = morpho.get(key, {})
    if not isinstance(item, dict):
        return str(item) if item else "pas de particularité"
    if item.get("status") == "normal":
        return "pas de particularité"
    parts = []
    if item.get("details"):
        parts.extend(item["details"] if isinstance(item["details"], list) else [item["details"]])
    if item.get("text"):
        parts.append(item["text"])
    return ", ".join(parts) if parts else "anomalie non précisée"


def build_neuropath_context(case: dict, modules: dict) -> dict:
    """
    Construit le contexte pour le template neuropath
    a partir des donnees du cas et du module neuropath.
    """
    np_data = modules.get("neuropath", {})

    return {
        "numero": case.get("numero_dossier", ""),
        "date_examen": case.get("date_examen", ""),
        "np_sa": np_data.get("sa", ""),
        "np_descriptions": np_data.get("descriptions", {}),
        "np_bio": np_data.get("biometries", {}),
        "np_zscores": np_data.get("zscores", {}),
        "np_oculaire": np_data.get("oculaire", {}),
        "np_cerv": np_data.get("cervelet", {}),
        "np_aqueduc": np_data.get("aqueduc", {}),
        "np_cc": np_data.get("corps_calleux", {}),
        "np_thd": np_data.get("tranches_hd", []),
        "np_thg": np_data.get("tranches_hg", []),
        "np_hpo": np_data.get("hpo_codes", []),
    }


def build_radio_context(case: dict, modules: dict) -> dict:
    """
    Construit le contexte pour le template radio
    a partir des donnees du cas et du module radio.
    """
    rd = modules.get("radio", {})
    terme = rd.get("terme", {})

    return {
        "numero": case.get("numero_dossier", ""),
        "date_examen": case.get("date_examen", ""),
        "rad_terme_sa": terme.get("sa", ""),
        "rad_terme_jours": terme.get("jours", 0),
        "rad_aspect_general": rd.get("aspect_general", ""),
        "rad_cotes": rd.get("cotes", {}),
        "rad_thorax_forme": rd.get("thorax_forme", ""),
        "rad_vertebres": rd.get("vertebres", {}),
        "rad_aspect_os": rd.get("aspect_os", {}),
        "rad_biometries": rd.get("biometries", {}),
        "rad_os_longs": rd.get("biometries", {}).get("os_longs", {}),
        "rad_scores": rd.get("scores_staturaux", {}),
        "rad_maturation": rd.get("maturation_osseuse", []),
        "rad_remarques": rd.get("remarques", ""),
        "rad_hpo_codes": rd.get("hpo_codes", []),
    }


# ══════════════════════════════════════════════════════════════════════════
# Registre des templates — avec versioning
# ══════════════════════════════════════════════════════════════════════════

TEMPLATES = {
    "soffoet": {
        "label": "CR SOFFOET (type 1)",
        "description": "Compte-rendu type SOFFOET complet",
        "version": "2.0.0",
        "file": "soffoet.jinja2",
        "changelog": [
            {
                "version": "2.0.0",
                "date": "2026-03-29",
                "changes": [
                    "Conclusion refondée : terme, macération, trophicité, liste exhaustive anomalies",
                    "Intégration complète des champs texte libres PWA (voies aériennes, OGI, TSA, "
                    "valves cardiaques, estomac, tube digestif, neuro, gonades, vessie, voies urinaires)",
                    "Section 'Examen après fixation' (macro_fixe : lésions + cassettes)",
                    "Anomalies prénatales (suspectées / confirmées) dans résumé clinique et conclusion",
                    "Détail prélèvements spéciaux",
                ],
            },
            {
                "version": "1.0.0",
                "date": "2026-03-01",
                "changes": [
                    "Template SOFFOET initial — résumé clinique, aspect externe, biométries, "
                    "examen interne, prélèvements, conclusion",
                ],
            },
        ],
    },
    "court": {
        "label": "CR Court",
        "description": "Synthèse courte pour communication rapide",
        "version": "2.0.0",
        "file": "court.jinja2",
        "changelog": [
            {
                "version": "2.0.0",
                "date": "2026-03-29",
                "changes": [
                    "Conclusion refondée : terme, macération, trophicité, liste exhaustive anomalies",
                    "Ajout notes (frais / autopsie) et anomalies prénatales",
                ],
            },
            {
                "version": "1.0.0",
                "date": "2026-03-01",
                "changes": ["Template court initial — synthèse rapide"],
            },
        ],
    },
    "neuropath": {
        "label": "Brouillon CR neuropath",
        "description": "Compte-rendu neuropathologique (examen du cerveau fixé)",
        "version": "1.0.0",
        "file": "neuropath.jinja2",
        "changelog": [
            {
                "version": "1.0.0",
                "date": "2026-03-29",
                "changes": [
                    "Template neuropath initial — macroscopie, biométries cérébrales, "
                    "cervelet/CC/aqueduc, biométries oculaires, tranches HD/HG, codes HPO",
                ],
            },
        ],
    },
    "radio": {
        "label": "Brouillon CR radio",
        "description": "Compte-rendu d'imagerie radiologique (squelette, biométries osseuses, maturation)",
        "version": "1.0.0",
        "file": "radio.jinja2",
        "changelog": [
            {
                "version": "1.0.0",
                "date": "2026-03-29",
                "changes": [
                    "Template radio initial — aspect squelette, biométries os longs (Chitty), "
                    "scores staturaux (Hadlock/Adalian), maturation osseuse",
                ],
            },
        ],
    },
}


def get_available_templates() -> list[dict]:
    """Retourne la liste des templates disponibles avec leur version."""
    return [
        {
            "id": tid,
            "label": t["label"],
            "description": t["description"],
            "version": t.get("version", "1.0.0"),
        }
        for tid, t in TEMPLATES.items()
    ]


def get_template_changelog(template_id: str) -> list[dict]:
    """Retourne le changelog d'un template."""
    if template_id not in TEMPLATES:
        return []
    return TEMPLATES[template_id].get("changelog", [])


def get_all_versions_info() -> dict:
    """Retourne un résumé de toutes les versions de tous les templates."""
    return {
        tid: {
            "label": t["label"],
            "current_version": t.get("version", "1.0.0"),
            "changelog": t.get("changelog", []),
        }
        for tid, t in TEMPLATES.items()
    }


def render_cr(template_id: str, context: dict) -> str:
    """
    Rend un CR à partir d'un template fichier et d'un contexte.

    Le texte généré inclut un marqueur de version en pied de page
    pour traçabilité.
    """
    if template_id not in TEMPLATES:
        return f"Template '{template_id}' non trouvé."

    tpl_entry = TEMPLATES[template_id]
    tpl_file = tpl_entry["file"]
    version = tpl_entry.get("version", "1.0.0")

    # Fonctions custom pour le template
    def _ds(key):
        return _ds_text(context.get("calc_bio", {}), key)

    def _morpho(key):
        return _morpho_text(context.get("morpho", {}), key)

    try:
        tpl = _jinja_env.get_template(tpl_file)
    except Exception as e:
        return f"Erreur chargement template '{tpl_file}': {str(e)}"

    # Ajouter les fonctions custom au contexte
    context_with_helpers = {**context, "_ds": _ds, "_morpho": _morpho}

    rendered = tpl.render(**context_with_helpers)

    # Marqueur de version en pied de CR
    rendered += f"\n---\n[Template {template_id} v{version}]"

    return rendered
