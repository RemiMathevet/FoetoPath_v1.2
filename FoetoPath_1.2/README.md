# FoetoPath

Serveur tout-en-un pour la foetopathologie : administration des cas, calculs biométriques, génération de comptes-rendus, viewer de lames histologiques et viewer de photos macro.

## Architecture

```
server3/
├── app.py                    # Serveur Flask principal + viewer lames (OpenSlide/MRXS)
├── db.py                     # SQLite hybride (colonnes stables + JSON blobs par module)
├── admin_bp.py               # Blueprint admin (CRUD, sync, appairage, photos, Ollama)
├── biometrics.py             # Moteur de calcul (DS, ratios, LBWR) — 4 classes
├── reference_data.py         # Tables de référence (GC, Maroun, dérivés) — séparé pour maintenance
├── cr_templates.py           # Templates Jinja2 CR (SOFFOET, Court) + contexte unifié
├── viewer_autoload.js        # Script auto-load URL params → à coller dans index.html du viewer
├── templates/
│   ├── index.html            # Viewer lames existant (OpenSeadragon)
│   ├── admin.html            # Interface admin complète (5 onglets + 5 thèmes)
│   └── viewer_photos.html    # Galerie photos macro (lightbox zoom/rotation)
└── foetopath.db              # Base SQLite (créée au premier lancement)
```

## Installation

```bash
# Dépendances
pip install flask jinja2 requests python-docx

# Lancement
python app.py --port 5000 --host 127.0.0.1

# Avec un dossier de lames par défaut
python app.py --root /chemin/vers/lames
```

Accès :
- **Admin** : http://127.0.0.1:5000/admin/
- **Viewer lames** : http://127.0.0.1:5000/
- **Viewer photos** : http://127.0.0.1:5000/admin/viewer-photos?case_id=1

## Fonctionnalités

### Admin (`/admin/`)

5 onglets par cas :

| Onglet | Contenu |
|--------|---------|
| **Informations** | Formulaire pré-examen (5 sous-sections : Admin, ATCD maternels, ATCD obstétricaux, Grossesse, Examens prénataux). Auto-save à la frappe (1s debounce). |
| **Dossiers macro** | Grille 5 colonnes (Photos/Frais/Autopsie/Fixé/Neuropath). Boutons "Photos macro" et "Lames histo" vers les viewers. |
| **Appairage** | Tableau organe × photos frais × photos fixé × lames. Contrôle cassettes vs lames. |
| **Données modules** | Rendu structuré des JSON (macro_frais, macro_autopsie). Bouton "Calculer DS & Ratios". |
| **CR** | Sélection template → génération Jinja2 → passage Ollama/Mistral pour rédaction LLM. |

### Sync locale

Scanne `data_root` (configurable dans Paramètres), détecte les dossiers `Foetus/` et `Placentas/`, importe les JSON préfixés (`26P4381_macro_frais.json` → module `macro_frais`), fusionne avec les cas existants.

### Calculs biométriques (`biometrics.py`)

4 classes séparées :

- **`OrganExtractor`** — navigue la structure imbriquée du JSON autopsie, extrait les masses individuelles D/G + sommes combinées. Gère : `coeur`, `thorax.thymus`, `poumons.masse_d/g`, `digestif.foie/rate/pancreas`, `retroperitoine.reins/surrenales.masse_d/g`, `neuro.masse_cerveau`.

- **`DSCalculator`** — calcule les DS par rapport aux références :
  - `biometries()` : masse, VT, VC, PC, pied vs Guihard-Costa 2002
  - `organes_combines()` : organes D+G vs GC 2002
  - `organes_individuels()` : organes pairs D/G vs dérivés (moy/2, sd/√2) + DS poolé √(mean(ds²))

- **`RatioCalculator`** — ratios organe/masse corporelle + LBWR De Paepe (seuil 0.012 < 28 SA, 0.015 ≥ 28 SA)

- **`compute_all()`** — orchestration + alertes automatiques (|DS| > 2)

### Données de référence (`reference_data.py`)

Fichier séparé pour faciliter la maintenance :

| Table | Source | Couverture |
|-------|--------|------------|
| `GC_MACRO` | Guihard-Costa 2002 | Biométries 13-42 SA (classes bi-hebdomadaires) |
| `GC_ORGANES` | Guihard-Costa 2002 | Masses organes combinés 13-42 SA |
| `GC_POUMON_INDIVIDUEL` | Dérivé GC (moy/2, sd/√2) | Poumons individuels D/G |
| `GC_REIN_INDIVIDUEL` | Dérivé GC | Reins individuels D/G |
| `GC_SURRENALE_INDIVIDUELLE` | Dérivé GC | Surrénales individuelles D/G |
| `MAROUN` | Maroun 2017 | Biométries + organes 12-43 SA, stratifié macération |

> Pour ajouter les vraies données d'organes pairs publiées, remplacer les tables `GC_*_INDIVIDUEL` dans `reference_data.py`. Pour ajouter Muller-Brochut 2018 (12-20 SA), ajouter un nouveau dict.

### Extraction du terme

Priorité de lecture pour le terme SA :

1. `macro_frais.terme.sa` ← structure réelle du JSON téléphone
2. `macro_frais.biometries.terme_sa` ← format alternatif
3. `case.terme_issue` ← formulaire admin (parse "24 SA + 3j" → 24)
4. `body.terme_sa` ← override manuel API

Macération : `macro_frais.maceration.maroun_score`

### Templates CR (`cr_templates.py`)

| Template | Description |
|----------|-------------|
| **SOFFOET** | CR type 1 complet : résumé clinique, aspect externe (morpho item par item), biométries avec DS, examen interne organe par organe, LBWR, prélèvements, conclusion |
| **Court** | Synthèse 1 page : identification, anomalies externes auto-détectées, biométries + organes en une ligne, alertes |

`build_cr_context()` construit un contexte unifié depuis case + modules + calculs. Les templates utilisent des helpers `_ds()` et `_morpho()` pour le formatage.

### Ollama / LLM

- **Auto-démarrage** : la route `/api/ollama/status` vérifie si Ollama tourne, le lance via `ollama serve` si besoin, attend 10s, puis liste les modèles installés.
- **Sélecteur de modèles** : dropdown dans l'onglet CR avec nom, taille, paramètres.
- **Prompts expert** : deux prompts spécialisés foetopathologie :
  - Biométries : regroupe les normaux, détaille les anomalies, prose pure
  - CR complet : structure SOFFOET, tournures imposées ("on observe", "l'examen met en évidence"), interdiction de modifier les valeurs numériques, regroupement des normaux, mise en évidence des anomalies
- **Temperature** : 0.2 pour rester collé aux données
- **Sauvegarde** : le texte généré est sauvegardé dans le module `last_cr_ollama`

### Viewer photos (`/admin/viewer-photos`)

- **Catégorisation** : suit l'ordre exact des JSON `macro_frais.photos` puis `macro_autopsie.photos`
- **Ordre d'affichage** : Anomalies → Examen externe → Suppl. externe → Autopsie → Suppl. autopsie
- **Labels** : traduction automatique des clés (`p_od_fo` → "OD / FO", `photo_face` → "Face")
- **Extras D/G** : classés selon leur contexte (entre `photo_` = externe, entre `p_` = autopsie)
- **Lightbox** : zoom molette/pinch/boutons, rotation R/Shift+R, drag pour pan, double-clic toggle 100%↔300%, raccourcis clavier (+/-/0/Escape/flèches)

### Viewer lames (`/`)

- Viewer OpenSeadragon existant pour MRXS/SVS
- Auto-load depuis URL : `/?root=/chemin/lames&slide=nom.mrxs`
- Script `viewer_autoload.js` à coller à la fin du `<script>` de `index.html`

### Thèmes

5 thèmes sélectionnables dans Paramètres (roue dentée), persistés en localStorage :

| Thème | Description |
|-------|-------------|
| **Sombre** | Thème par défaut, fond sombre, accent violet |
| **Clair** | Fond blanc, texte noir, pour impression ou travail en journée |
| **Malvoyant** | Haut contraste, fond noir, texte blanc/jaune, accent cyan, police 16px, bordures épaisses |
| **CLI** | Terminal années 80, vert phosphore, monospace, bordures tirets, text-shadow |
| **Win 98** | Fenêtres grises 3D, barre de titre bleue, boutons relief, scrollbar 16px |

Le thème s'applique aussi au viewer photos automatiquement.

## Structure des données

### SQLite (`foetopath.db`)

```
cases           → id, numero_dossier (UNIQUE), identité, terme, sexe, chemins, workflow, statut
module_data     → case_id FK, module_name, data_json (blob), UNIQUE(case_id, module_name)
macro_folders   → case_id FK, folder_type, photo_count
settings        → key/value (slides_root, data_root, ollama_url, ollama_model, viewer_port)
```

### JSON téléphone (structure réelle)

```
FoetoPath/
├── Foetus/
│   └── 26P4381/
│       ├── 26P4381_macro_frais.json      # terme.sa, biometries, morphologie, maceration, photos[]
│       ├── 26P4381_macro_autopsie.json   # ouverture, coeur, poumons, digestif, retroperitoine, neuro, photos[]
│       └── photos/
│           ├── 26P4381_photo_face.jpg    # photo_ = examen externe
│           ├── 26P4381_p_situs.jpg       # p_ = autopsie
│           ├── 26P4381_anomaly_yeux_*.jpg # anomaly_ = anomalies
│           └── 26P4381_extra_1.jpg       # extra_ = supplémentaires (classé par contexte)
└── Placentas/
    └── 26P4061/
```

## API principales

| Route | Méthode | Description |
|-------|---------|-------------|
| `/admin/api/cases` | GET | Liste tous les cas |
| `/admin/api/cases` | POST | Créer un cas |
| `/admin/api/cases/<id>` | GET/PUT/DELETE | CRUD cas |
| `/admin/api/cases/<id>/compute` | POST | Calculer DS + ratios |
| `/admin/api/cr/templates` | GET | Templates CR disponibles |
| `/admin/api/cases/<id>/cr/generate` | POST | Générer un CR (`{template_id}`) |
| `/admin/api/cases/<id>/cr/ollama` | POST | Rédaction LLM (`{text, model}`) |
| `/admin/api/ollama/status` | POST | Démarrer Ollama + lister modèles |
| `/admin/api/photos/list` | POST | Photos catégorisées (`{case_id}`) |
| `/admin/api/sync` | POST | Sync locale depuis data_root |
| `/api/browse` | POST | Lister les cas dans un dossier de lames |
| `/api/slides` | POST | Lister lames + photos d'un dossier |

## TODO

- [ ] Muller-Brochut 2018 (organes 12-20 SA) dans `reference_data.py`
- [ ] Maroun stratifié par macération dans les calculs
- [ ] Organes pairs individuels : données publiées (remplacer dérivés moy/2, sd/√2)
- [ ] Module radio (examen radiographique)
- [ ] Module neuropathologie
- [ ] Module placenta (macro + micro, Amsterdam)
- [ ] Template CR exhaustif
- [ ] Export Word (.docx) des CR
- [ ] Remplissage des étapes macro (frais/autopsie/fixé/neuropath) dans l'onglet Dossiers
- [ ] Affinage de l'appairage (photos fixé × lames par organe)
