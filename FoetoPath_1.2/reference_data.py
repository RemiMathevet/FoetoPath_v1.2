#!/usr/bin/env python3
"""
FoetoPath — Données de référence biométriques.

Sources :
  - Guihard-Costa 2002 : biométries macroscopiques + masses d'organes (classes bi-hebdomadaires)
  - Maroun 2017 : biométries + organes par SA (12–43 SA), stratifié par macération
  - Muller-Brochut 2018 : organes 12–20 SA

Format uniforme : {"moy": float, "sd": float}
Pour les organes stratifiés Maroun : {"moy": float, "sd": float} par grade de macération.

Mise à jour : ajouter/modifier les dicts ci-dessous, le moteur de calcul s'adapte.
"""

# ══════════════════════════════════════════════════════════════════════════
# GUIHARD-COSTA 2002 — Biométries macroscopiques
# Classes bi-hebdomadaires. Unités : masse(g), VT/VC/PC(mm), pied(mm)
# ══════════════════════════════════════════════════════════════════════════

GC_MACRO = {
    "13-14": {"masse": {"moy": 55.8, "sd": 14.4}, "VT": {"moy": 131.8, "sd": 15.4}, "VC": {"moy": 89.6, "sd": 11.7}, "PC": {"moy": 89.2, "sd": 11.8}, "pied": {"moy": 14, "sd": 2.9}},
    "15-16": {"masse": {"moy": 108.6, "sd": 24.7}, "VT": {"moy": 170.4, "sd": 16.2}, "VC": {"moy": 116.2, "sd": 12.2}, "PC": {"moy": 116.7, "sd": 12.2}, "pied": {"moy": 19, "sd": 3}},
    "17-18": {"masse": {"moy": 176.1, "sd": 39}, "VT": {"moy": 207.4, "sd": 17}, "VC": {"moy": 141.7, "sd": 12.7}, "PC": {"moy": 142.8, "sd": 12.6}, "pied": {"moy": 25, "sd": 3.2}},
    "19-20": {"masse": {"moy": 267.7, "sd": 57.1}, "VT": {"moy": 242.9, "sd": 17.8}, "VC": {"moy": 166.2, "sd": 13.1}, "PC": {"moy": 167.5, "sd": 12.9}, "pied": {"moy": 30, "sd": 3.3}},
    "21-22": {"masse": {"moy": 392.7, "sd": 79.2}, "VT": {"moy": 276.8, "sd": 18.6}, "VC": {"moy": 189.8, "sd": 13.6}, "PC": {"moy": 190.9, "sd": 13.3}, "pied": {"moy": 36, "sd": 3.5}},
    "23-24": {"masse": {"moy": 559.6, "sd": 105.1}, "VT": {"moy": 309.2, "sd": 19.4}, "VC": {"moy": 212.3, "sd": 14.1}, "PC": {"moy": 212.8, "sd": 13.7}, "pied": {"moy": 42, "sd": 3.6}},
    "25-26": {"masse": {"moy": 773.9, "sd": 134.9}, "VT": {"moy": 340, "sd": 20.2}, "VC": {"moy": 233.8, "sd": 14.6}, "PC": {"moy": 233.4, "sd": 14}, "pied": {"moy": 48, "sd": 3.8}},
    "27-28": {"masse": {"moy": 1038.2, "sd": 168.6}, "VT": {"moy": 369.3, "sd": 21}, "VC": {"moy": 254.4, "sd": 15.1}, "PC": {"moy": 252.7, "sd": 14.4}, "pied": {"moy": 53, "sd": 3.9}},
    "29-30": {"masse": {"moy": 1350.4, "sd": 206.1}, "VT": {"moy": 397, "sd": 21.8}, "VC": {"moy": 273.9, "sd": 15.5}, "PC": {"moy": 270.5, "sd": 14.8}, "pied": {"moy": 58, "sd": 4.1}},
    "31-32": {"masse": {"moy": 1702.5, "sd": 247.6}, "VT": {"moy": 432.2, "sd": 22.6}, "VC": {"moy": 292.4, "sd": 16}, "PC": {"moy": 287, "sd": 15.1}, "pied": {"moy": 63, "sd": 4.2}},
    "33-34": {"masse": {"moy": 2080.2, "sd": 292.9}, "VT": {"moy": 447.8, "sd": 23.4}, "VC": {"moy": 309.9, "sd": 16.5}, "PC": {"moy": 302.1, "sd": 15.5}, "pied": {"moy": 67, "sd": 4.4}},
    "35-36": {"masse": {"moy": 2460.8, "sd": 342.1}, "VT": {"moy": 470.9, "sd": 24.2}, "VC": {"moy": 326.5, "sd": 17}, "PC": {"moy": 315.8, "sd": 15.9}, "pied": {"moy": 71, "sd": 4.6}},
    "37-38": {"masse": {"moy": 2813.1, "sd": 395.3}, "VT": {"moy": 492.5, "sd": 24.9}, "VC": {"moy": 342, "sd": 17.5}, "PC": {"moy": 328.1, "sd": 16.2}, "pied": {"moy": 74, "sd": 4.7}},
    "39-40": {"masse": {"moy": 3095.1, "sd": 452.2}, "VT": {"moy": 512.5, "sd": 25.7}, "VC": {"moy": 356, "sd": 17.9}, "PC": {"moy": 339.1, "sd": 16.6}, "pied": {"moy": 76, "sd": 4.9}},
    "41-42": {"masse": {"moy": 3254.9, "sd": 531.1}, "VT": {"moy": 530.9, "sd": 26.5}, "VC": {"moy": 370, "sd": 18.4}, "PC": {"moy": 348.6, "sd": 17}, "pied": {"moy": 77, "sd": 5.1}},
}


# ══════════════════════════════════════════════════════════════════════════
# GUIHARD-COSTA 2002 — Masses d'organes COMBINÉS (g)
# Poumons = D+G, Reins = D+G, Surrénales = D+G
# ══════════════════════════════════════════════════════════════════════════

GC_ORGANES = {
    "13-14": {"thymus": {"moy": 0.09, "sd": 0.07}, "coeur": {"moy": 0.24, "sd": 0.13}, "poumons": {"moy": 1.26, "sd": 0.25}, "foie": {"moy": 3.09, "sd": 0.27}, "rate": {"moy": 0.06, "sd": 0.04}, "pancreas": {"moy": 0.09, "sd": 0.01}, "surrenales": {"moy": 0.29, "sd": 0.06}, "reins": {"moy": 0.41, "sd": 0.11}},
    "15-16": {"thymus": {"moy": 0.17, "sd": 0.12}, "coeur": {"moy": 0.82, "sd": 0.23}, "poumons": {"moy": 2.99, "sd": 0.54}, "foie": {"moy": 5.81, "sd": 1.71}, "rate": {"moy": 0.12, "sd": 0.08}, "pancreas": {"moy": 0.28, "sd": 0.08}, "surrenales": {"moy": 0.56, "sd": 0.10}, "reins": {"moy": 0.71, "sd": 0.18}},
    "17-18": {"thymus": {"moy": 0.31, "sd": 0.19}, "coeur": {"moy": 1.44, "sd": 0.37}, "poumons": {"moy": 5.09, "sd": 0.91}, "foie": {"moy": 9.39, "sd": 3.33}, "rate": {"moy": 0.23, "sd": 0.13}, "pancreas": {"moy": 0.42, "sd": 0.16}, "surrenales": {"moy": 0.91, "sd": 0.16}, "reins": {"moy": 1.38, "sd": 0.27}},
    "19-20": {"thymus": {"moy": 0.53, "sd": 0.3}, "coeur": {"moy": 2.21, "sd": 0.56}, "poumons": {"moy": 7.68, "sd": 1.34}, "foie": {"moy": 14.33, "sd": 5.15}, "rate": {"moy": 0.38, "sd": 0.2}, "pancreas": {"moy": 0.57, "sd": 0.24}, "surrenales": {"moy": 1.32, "sd": 0.23}, "reins": {"moy": 2.41, "sd": 0.38}},
    "21-22": {"thymus": {"moy": 0.87, "sd": 0.45}, "coeur": {"moy": 3.23, "sd": 0.79}, "poumons": {"moy": 10.84, "sd": 1.84}, "foie": {"moy": 21, "sd": 7.15}, "rate": {"moy": 0.62, "sd": 0.29}, "pancreas": {"moy": 0.78, "sd": 0.34}, "surrenales": {"moy": 1.79, "sd": 0.32}, "reins": {"moy": 3.84, "sd": 0.53}},
    "23-24": {"thymus": {"moy": 1.35, "sd": 0.64}, "coeur": {"moy": 4.55, "sd": 1.07}, "poumons": {"moy": 14.65, "sd": 2.39}, "foie": {"moy": 29.63, "sd": 9.35}, "rate": {"moy": 0.96, "sd": 0.42}, "pancreas": {"moy": 1.08, "sd": 0.45}, "surrenales": {"moy": 2.33, "sd": 0.41}, "reins": {"moy": 5.64, "sd": 0.70}},
    "25-26": {"thymus": {"moy": 2.01, "sd": 0.89}, "coeur": {"moy": 6.21, "sd": 1.39}, "poumons": {"moy": 19.09, "sd": 2.98}, "foie": {"moy": 40.27, "sd": 11.75}, "rate": {"moy": 1.44, "sd": 0.59}, "pancreas": {"moy": 1.47, "sd": 0.57}, "surrenales": {"moy": 2.92, "sd": 0.51}, "reins": {"moy": 7.78, "sd": 0.90}},
    "27-28": {"thymus": {"moy": 2.92, "sd": 1.21}, "coeur": {"moy": 8.2, "sd": 1.76}, "poumons": {"moy": 24.15, "sd": 3.61}, "foie": {"moy": 52.89, "sd": 14.33}, "rate": {"moy": 2.09, "sd": 0.8}, "pancreas": {"moy": 1.98, "sd": 0.7}, "surrenales": {"moy": 3.57, "sd": 0.61}, "reins": {"moy": 10.22, "sd": 1.12}},
    "29-30": {"thymus": {"moy": 4.14, "sd": 1.61}, "coeur": {"moy": 10.48, "sd": 2.17}, "poumons": {"moy": 29.79, "sd": 4.27}, "foie": {"moy": 67.29, "sd": 17.1}, "rate": {"moy": 2.95, "sd": 1.06}, "pancreas": {"moy": 2.58, "sd": 0.84}, "surrenales": {"moy": 4.3, "sd": 0.72}, "reins": {"moy": 12.9, "sd": 1.37}},
    "31-32": {"thymus": {"moy": 5.72, "sd": 2.1}, "coeur": {"moy": 12.98, "sd": 2.63}, "poumons": {"moy": 35.9, "sd": 4.94}, "foie": {"moy": 83.1, "sd": 20.07}, "rate": {"moy": 4.08, "sd": 1.39}, "pancreas": {"moy": 3.26, "sd": 0.98}, "surrenales": {"moy": 5.08, "sd": 0.82}, "reins": {"moy": 15.73, "sd": 1.65}},
    "33-34": {"thymus": {"moy": 7.75, "sd": 2.7}, "coeur": {"moy": 15.6, "sd": 3.14}, "poumons": {"moy": 42.36, "sd": 5.62}, "foie": {"moy": 99.87, "sd": 23.23}, "rate": {"moy": 5.53, "sd": 1.78}, "pancreas": {"moy": 3.97, "sd": 1.14}, "surrenales": {"moy": 5.93, "sd": 0.92}, "reins": {"moy": 18.62, "sd": 1.96}},
    "35-36": {"thymus": {"moy": 10.33, "sd": 3.42}, "coeur": {"moy": 18.21, "sd": 3.69}, "poumons": {"moy": 48.98, "sd": 6.30}, "foie": {"moy": 116.97, "sd": 26.58}, "rate": {"moy": 7.35, "sd": 2.25}, "pancreas": {"moy": 4.66, "sd": 1.31}, "surrenales": {"moy": 6.83, "sd": 1.01}, "reins": {"moy": 21.46, "sd": 2.29}},
    "37-38": {"thymus": {"moy": 13.54, "sd": 4.27}, "coeur": {"moy": 20.63, "sd": 4.28}, "poumons": {"moy": 55.59, "sd": 6.98}, "foie": {"moy": 133.64, "sd": 30.12}, "rate": {"moy": 9.63, "sd": 2.82}, "pancreas": {"moy": 5.26, "sd": 1.49}, "surrenales": {"moy": 7.79, "sd": 1.09}, "reins": {"moy": 24.12, "sd": 2.65}},
    "39-40": {"thymus": {"moy": 17.5, "sd": 5.27}, "coeur": {"moy": 22.68, "sd": 4.92}, "poumons": {"moy": 61.94, "sd": 7.64}, "foie": {"moy": 148.97, "sd": 33.85}, "rate": {"moy": 12.43, "sd": 3.48}, "pancreas": {"moy": 5.71, "sd": 1.67}, "surrenales": {"moy": 8.83, "sd": 1.17}, "reins": {"moy": 26.45, "sd": 3.04}},
    "41-42": {"thymus": {"moy": 22.34, "sd": 6.44}, "coeur": {"moy": 24.49, "sd": 5.58}, "poumons": {"moy": 67.6, "sd": 8.28}, "foie": {"moy": 161.94, "sd": 37.78}, "rate": {"moy": 15.85, "sd": 4.25}, "pancreas": {"moy": 5.9, "sd": 1.87}, "surrenales": {"moy": 9.92, "sd": 1.22}, "reins": {"moy": 28.28, "sd": 3.45}},
}


# ══════════════════════════════════════════════════════════════════════════
# GUIHARD-COSTA 2002 — Organes PAIRS individuels
# TODO: à compléter avec les données publiées si disponibles.
# En attendant, on dérive depuis les données combinées :
#   moy_individuel = moy_combiné / 2
#   sd_individuel  = sd_combiné / sqrt(2)   (indépendance supposée)
# Ce fichier sera le seul à modifier quand les vraies données seront ajoutées.
# ══════════════════════════════════════════════════════════════════════════

import math as _math

def _derive_individual(combined_table: dict, organ_key: str) -> dict:
    """Dérive les références individuelles depuis les combinées (moy/2, sd/√2)."""
    result = {}
    for classe, organs in combined_table.items():
        if organ_key in organs:
            ref = organs[organ_key]
            result[classe] = {
                "moy": round(ref["moy"] / 2, 4),
                "sd": round(ref["sd"] / _math.sqrt(2), 4),
            }
    return result

# Organes pairs dérivés — remplacer par les vraies données quand disponibles
GC_POUMON_INDIVIDUEL = _derive_individual(GC_ORGANES, "poumons")
GC_REIN_INDIVIDUEL = _derive_individual(GC_ORGANES, "reins")
GC_SURRENALE_INDIVIDUELLE = _derive_individual(GC_ORGANES, "surrenales")


# ══════════════════════════════════════════════════════════════════════════
# MAROUN 2017 — par SA, stratifié par macération (0-1, 2, 3)
# Sélection de SA représentatives. Format: {SA: {"Mean": {...}, "SD": {...}}}
# ══════════════════════════════════════════════════════════════════════════

MAROUN = {
    12: {"Mean": {"FL": 9, "CR": 7.4, "CH": 9.8, "HDC": 7.1, "Body": 29.6, "brain": 4.8, "heart": 0.1, "lungs 0 1": 0.6, "lungs 2 3": 0.9, "liver 0 1": 1.5, "liver 2": 1.4, "liver 3": 1.3, "thymus 0 1": 0.03, "thymus 2": 0.01, "thymus 3": 0.25, "spleen 0 1": 0.19, "spleen 2 3": 0.04, "kidneys 0 1": 0.11, "kidneys 2 3": None, "adrenals 0 1": None, "adrenals 2 3": None}, "SD": {"FL": 3, "CR": 1.1, "CH": 1.7, "HDC": 1.1, "Body": 14.9, "brain": 1.4, "heart": 0.14, "lungs 0 1": 0.9, "lungs 2 3": 0.9, "liver 0 1": 1.2, "liver 2": 1.2, "liver 3": 1.2, "thymus 0 1": 0.06, "thymus 2": 0.02, "thymus 3": 0.15, "spleen 0 1": 0.15, "spleen 2 3": 0.18, "kidneys 0 1": 0.18, "kidneys 2 3": None, "adrenals 0 1": None, "adrenals 2 3": None}},
    16: {"Mean": {"FL": 21, "CR": 12.4, "CH": 17.5, "HDC": 12.4, "Body": 108, "brain": 17.3, "heart": 0.8, "lungs 0 1": 3.9, "lungs 2 3": 2.7, "liver 0 1": 5.9, "liver 2": 4.5, "liver 3": 4.2, "thymus 0 1": 0.11, "thymus 2": 0.12, "thymus 3": 0.09, "spleen 0 1": 0.09, "spleen 2 3": 0.17, "kidneys 0 1": 0.9, "kidneys 2 3": 0.8, "adrenals 0 1": 0.6, "adrenals 2 3": 0.4}, "SD": {"FL": 3, "CR": 1.3, "CH": 1.8, "HDC": 1.3, "Body": 41, "brain": 5.4, "heart": 0.2, "lungs 0 1": 1.2, "lungs 2 3": 1.2, "liver 0 1": 1.5, "liver 2": 1.5, "liver 3": 1.5, "thymus 0 1": 0.06, "thymus 2": 0.06, "thymus 3": 0.06, "spleen 0 1": 0.08, "spleen 2 3": 0.08, "kidneys 0 1": 0.4, "kidneys 2 3": 0.4, "adrenals 0 1": 0.3, "adrenals 2 3": 0.3}},
    20: {"Mean": {"FL": 33, "CR": 17, "CH": 24.6, "HDC": 17.2, "Body": 312, "brain": 45.5, "heart": 2.1, "lungs 0 1": 9.5, "lungs 2 3": 6.5, "liver 0 1": 17.2, "liver 2": 12.5, "liver 3": 10.2, "thymus 0 1": 0.6, "thymus 2": 0.5, "thymus 3": 0.3, "spleen 0 1": 0.4, "spleen 2 3": 0.17, "kidneys 0 1": 3, "kidneys 2 3": 2.5, "adrenals 0 1": 1.4, "adrenals 2 3": 1}, "SD": {"FL": 3, "CR": 1.4, "CH": 1.9, "HDC": 1.4, "Body": 92, "brain": 11.3, "heart": 0.8, "lungs 0 1": 3.4, "lungs 2 3": 3.4, "liver 0 1": 7.5, "liver 2": 7.5, "liver 3": 7.5, "thymus 0 1": 0.4, "thymus 2": 0.4, "thymus 3": 0.4, "spleen 0 1": 0.3, "spleen 2 3": 0.29, "kidneys 0 1": 1.2, "kidneys 2 3": 1.2, "adrenals 0 1": 0.6, "adrenals 2 3": 0.6}},
    24: {"Mean": {"FL": 44, "CR": 21.5, "CH": 31.2, "HDC": 21.6, "Body": 641, "brain": 89.3, "heart": 4.2, "lungs 0 1": 17.3, "lungs 2 3": 12.4, "liver 0 1": 35.4, "liver 2": 25.2, "liver 3": 19.5, "thymus 0 1": 1.6, "thymus 2": 1.3, "thymus 3": 0.8, "spleen 0 1": 1.1, "spleen 2 3": 0.6, "kidneys 0 1": 6.5, "kidneys 2 3": 5.5, "adrenals 0 1": 2.5, "adrenals 2 3": 1.8}, "SD": {"FL": 4, "CR": 1.5, "CH": 2, "HDC": 1.5, "Body": 137, "brain": 17.2, "heart": 1.4, "lungs 0 1": 5.9, "lungs 2 3": 5.9, "liver 0 1": 13.4, "liver 2": 13.4, "liver 3": 13.4, "thymus 0 1": 0.9, "thymus 2": 0.9, "thymus 3": 0.9, "spleen 0 1": 0.6, "spleen 2 3": 0.6, "kidneys 0 1": 2.1, "kidneys 2 3": 2.1, "adrenals 0 1": 0.9, "adrenals 2 3": 0.9}},
    28: {"Mean": {"FL": 55, "CR": 25.7, "CH": 37.3, "HDC": 25.5, "Body": 1096, "brain": 149, "heart": 7.1, "lungs 0 1": 27.4, "lungs 2 3": 20.2, "liver 0 1": 60.6, "liver 2": 42.7, "liver 3": 32, "thymus 0 1": 3.1, "thymus 2": 2.5, "thymus 3": 1.6, "spleen 0 1": 2.5, "spleen 2 3": 1.8, "kidneys 0 1": 11.4, "kidneys 2 3": 9.6, "adrenals 0 1": 3.7, "adrenals 2 3": 2.8}, "SD": {"FL": 4, "CR": 1.6, "CH": 2.2, "HDC": 1.6, "Body": 206, "brain": 23, "heart": 2, "lungs 0 1": 8.7, "lungs 2 3": 8.7, "liver 0 1": 19.3, "liver 2": 19.3, "liver 3": 19.3, "thymus 0 1": 1.6, "thymus 2": 1.6, "thymus 3": 1.6, "spleen 0 1": 1.1, "spleen 2 3": 1.1, "kidneys 0 1": 3.3, "kidneys 2 3": 3.3, "adrenals 0 1": 1.3, "adrenals 2 3": 1.3}},
    32: {"Mean": {"FL": 64, "CR": 29.7, "CH": 42.8, "HDC": 28.9, "Body": 1677, "brain": 224, "heart": 10.6, "lungs 0 1": 39.6, "lungs 2 3": 30, "liver 0 1": 92.6, "liver 2": 65, "liver 3": 47.6, "thymus 0 1": 5, "thymus 2": 4.2, "thymus 3": 2.6, "spleen 0 1": 4.8, "spleen 2 3": 3.9, "kidneys 0 1": 17.7, "kidneys 2 3": 14.9, "adrenals 0 1": 5.2, "adrenals 2 3": 4.1}, "SD": {"FL": 4, "CR": 1.7, "CH": 2.3, "HDC": 1.7, "Body": 285, "brain": 29, "heart": 2.6, "lungs 0 1": 11.8, "lungs 2 3": 11.8, "liver 0 1": 25.3, "liver 2": 25.3, "liver 3": 25.3, "thymus 0 1": 2.5, "thymus 2": 2.5, "thymus 3": 2.5, "spleen 0 1": 1.8, "spleen 2 3": 1.8, "kidneys 0 1": 4.6, "kidneys 2 3": 4.6, "adrenals 0 1": 1.6, "adrenals 2 3": 1.6}},
    36: {"Mean": {"FL": 73, "CR": 33.4, "CH": 47.7, "HDC": 31.9, "Body": 2383, "brain": 315, "heart": 14.8, "lungs 0 1": 54.1, "lungs 2 3": 41.9, "liver 0 1": 132, "liver 2": 92.1, "liver 3": 66.5, "thymus 0 1": 7.5, "thymus 2": 6.2, "thymus 3": 3.8, "spleen 0 1": 8.1, "spleen 2 3": 6.7, "kidneys 0 1": 25.4, "kidneys 2 3": 21.4, "adrenals 0 1": 6.9, "adrenals 2 3": 5.6}, "SD": {"FL": 5, "CR": 1.8, "CH": 2.4, "HDC": 1.8, "Body": 373, "brain": 35, "heart": 3.2, "lungs 0 1": 15.2, "lungs 2 3": 15.2, "liver 0 1": 31, "liver 2": 31.2, "liver 3": 31.2, "thymus 0 1": 3.6, "thymus 2": 3.6, "thymus 3": 3.6, "spleen 0 1": 2.5, "spleen 2 3": 2.5, "kidneys 0 1": 6.2, "kidneys 2 3": 6.2, "adrenals 0 1": 2, "adrenals 2 3": 2}},
    40: {"Mean": {"FL": 82, "CR": 37, "CH": 52.1, "HDC": 34.4, "Body": 3215, "brain": 422, "heart": 19.8, "lungs 0 1": 70.9, "lungs 2 3": 55.7, "liver 0 1": 177, "liver 2": 124, "liver 3": 88.6, "thymus 0 1": 10.5, "thymus 2": 8.6, "thymus 3": 5.4, "spleen 0 1": 12.4, "spleen 2 3": 9.9, "kidneys 0 1": 34.5, "kidneys 2 3": 29, "adrenals 0 1": 8.8, "adrenals 2 3": 7.4}, "SD": {"FL": 5, "CR": 1.9, "CH": 2.5, "HDC": 1.9, "Body": 471, "brain": 41, "heart": 3.7, "lungs 0 1": 18.9, "lungs 2 3": 18.9, "liver 0 1": 37, "liver 2": 37, "liver 3": 37.1, "thymus 0 1": 4.9, "thymus 2": 4.9, "thymus 3": 4.9, "spleen 0 1": 3.4, "spleen 2 3": 3.4, "kidneys 0 1": 8, "kidneys 2 3": 8, "adrenals 0 1": 2.4, "adrenals 2 3": 2.4}},
}


# ══════════════════════════════════════════════════════════════════════════
# Labels lisibles pour l'affichage
# ══════════════════════════════════════════════════════════════════════════

ORGAN_LABELS = {
    "coeur": "Cœur", "thymus": "Thymus",
    "poumons": "Poumons (D+G)", "poumon_d": "Poumon droit", "poumon_g": "Poumon gauche",
    "foie": "Foie", "rate": "Rate", "pancreas": "Pancréas",
    "surrenales": "Surrénales (D+G)", "surrenale_d": "Surrénale droite", "surrenale_g": "Surrénale gauche",
    "reins": "Reins (D+G)", "rein_d": "Rein droit", "rein_g": "Rein gauche",
    "cerveau": "Cerveau",
}

BIO_LABELS = {
    "masse": "Masse (g)", "VT": "VT (mm)", "VC": "VC (mm)", "PC": "PC (mm)", "pied": "Pied (mm)",
}
