# FoetoPath — Contexte Projet

## Qui suis-je

Rémi, fœtopathologiste au CHU Besançon. Je développe **FoetoPath**, un écosystème open-source de gestion de cas en fœtopathologie. Le domaine est francophone, les termes cliniques sont en français, l'âge gestationnel s'exprime en **SA** (Semaines d'Aménorrhée).

---

## Vue d'ensemble

FoetoPath comporte deux composants interconnectés :

**1. Application portable (PWA)** — *pivot en cours*
- **Historique** : initialement une app Android native (`uk.pazuzu.foetus`) avec WebView + Kotlin bridge. L'approche est abandonnée au profit d'une **Progressive Web App (PWA)** cross-platform (Android, iOS, desktop) sans dépendance aux stores.
- Saisie au lit du patient : acquisition photos, biométries, données cliniques
- Modules : macro_frais, macro_autopsie, macro_fixe, neuropath (placeholder), placenta
- Avantages PWA : déploiement instantané, pas de Kotlin bridge, pas de contrainte ES5 WebView, fonctionne hors-ligne via Service Worker, un seul codebase pour tous les appareils

**2. Application serveur** (`server3/`)
- Flask + SQLite
- Moteur biométrique : `reference_data.py` + 4 classes dans `biometrics.py`
- Navigation JSON imbriqué pour extraction organes (ex. `thorax.thymus.masse`, sommation bilatérale)
- Terme lu depuis `macro_frais.terme.sa`
- Onglet CR avec templates Jinja2 (SOFFOET Type 1 + Court)
- Intégration Ollama/Mistral (température 0.2, préservation stricte des valeurs numériques, phrasé imposé : "on observe", "l'examen met en évidence")
- Viewer lames OpenSeadragon (MRXS, SVS, NDPI…) + viewer photos dédié (`/admin/viewer-photos`) avec lightbox (zoom, rotation, pan, clavier)
- 5 thèmes UI avec persistence localStorage : Sombre, Clair, Malvoyant, CLI, Windows 98

---

## Architecture technique

### Format d'échange & génération de données
- **JSON** est le format canonique entre la PWA et le serveur
- **Changement en cours** : la génération des données de saisie migre de l'app native Android vers la PWA. Les données sont désormais produites côté navigateur (IndexedDB / localStorage pour l'offline, sync serveur quand connecté) au lieu de transiter par le Kotlin bridge
- Export complet d'un dossier = agrégation de tous les modules (`pre-exam`, `externe`, `biometries`, `interne`, `imagerie`, `prelevements`, `placenta`, `synthese`)

### Modules frontend (app.html = shell SPA)
| Module | Fichier | Contenu |
|---|---|---|
| Pré-examen | `formulaire-pre-examen.html` | Administratif, ATCD maternels, obstétricaux, grossesse en cours, examens prénataux |
| Examen externe | `examen-externe.html` | Morphologie, score Genest (macération) |
| Biométries | `biometries.html` | Corporelles (masse, pied, VT, VC, PC, PT, PA) + céphaliques (BIP, FO, DICI, DICE, FPG, FPD, DIM), colonnes DS par référence |
| Examen interne | `examen-interne.html` | Organes par appareil |
| Imagerie | `imagerie.html` | Radio, données morpho/biométrique/maturation |
| Prélèvements | `prelevements.html` | Checklist organes prélevés |
| Placenta | `placenta.html` | Macro + micro, cordon, membranes |
| Synthèse | `synthese.html` | Résumé, diagnostics (HPO, ORPHA, CIM-10), génération CR |

### Serveur — Routes clés
- `/api/browse`, `/api/slides` — navigation dossiers/lames
- `/api/dzi/<path>` — tiles OpenSeadragon (DeepZoom)
- `/api/annotations/save`, `/api/annotations/load` — annotations GeoJSON avec coordonnées pixels + µm
- `/api/sync` — synchronisation ADB depuis Android (legacy, sera remplacé par sync PWA↔serveur)
- `/api/photo/serve`, `/api/photo/thumbnail` — service photos

### Références biométriques intégrées
- **Guihard-Costa 2002** — biométries corporelles et céphaliques
- **Maroun 2017** — Z-scores corporels, céphaliques et organes (12–41 SA, score macération 0–3)
- **Müller-Brochut 2018** — organes et biométries 12–20 SA

### Templates de compte-rendu
- `cr_soffoet_template.j2` — template SOFFOET Type 1 complet (pré-exam, externe, biométries, imagerie, prélèvements, placenta, synthèse)
- Template court en cours
- Limitation actuelle : examen interne pas encore exporté par FoetoPath v1 (placeholder manuel)

---

## Contraintes techniques importantes

### Actuelles (PWA + serveur)
- **Flask** : `app.json.sort_keys = False` obligatoire (sinon `OrderedDict` détruit)
- **Git** : `git add assets/` doit être explicite
- **PWA offline** : prévoir Service Worker + cache strategy pour fonctionnement sans réseau
- **Accès caméra/fichiers** : via les API Web standards (`navigator.mediaDevices`, File API) — plus de dépendance au bridge natif

### Legacy (app Android native — phase-out)
- Ne jamais modifier `MainActivity.kt` ou `AndroidManifest.xml` — tout passait par les assets HTML
- Doublons de méthodes Kotlin bridge = mode d'échec silencieux
- Compatibilité WebView ES5 : pas de `?.`, pas de `=>`, pas de `const`/`let`, pas de `.closest()` — **cette contrainte disparaît avec le passage en PWA** (JS moderne possible)
- Debug sans console : `gid('badge-dossier').textContent = msg`
- Samsung EU : `ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION` cassé → `ACTION_APPLICATION_DETAILS_SETTINGS`

---

## Gestion du cache — Lames (stratégie multi-utilisateurs)

FoetoPath doit supporter 4 utilisateurs simultanés consultant des lames. La stratégie de cache repose sur trois niveaux :

### Niveau 1 — Cache applicatif (Python/Flask)
- LRU cache en mémoire pour les objets OpenSlide (`maxsize=10`) et les DeepZoomGenerator (`maxsize=10`)
- Thumbnails de lames générés à la volée (300×300 JPEG quality 85)
- Annotation GeoJSON stockées sur disque (`{root}/annotations/{slide_stem}.geojson`)

### Niveau 2 — Reverse proxy Nginx (cache tuiles)
- **Nginx** en frontal de Flask, cache des tuiles JPEG (endpoint `/api/slide/tile/`)
- Configuration : `proxy_cache_path` avec stockage disque, clé basée sur `$request_uri`
- TTL long (tuiles immuables pour une lame donnée) : `proxy_cache_valid 200 30d`
- Headers : `X-Accel-Buffering: yes`, `Cache-Control: public, max-age=2592000`
- Avantages : décharge Flask du service des tuiles récurrentes, réduit la latence pour les 4 utilisateurs

### Niveau 3 — Redis (sessions & métadonnées)
- **Redis** pour les sessions Flask (remplace le cookie-based session par défaut)
- Cache des métadonnées fréquentes : propriétés slide, DZI XML, infos calibration
- `flask-caching` avec backend Redis, TTL configurable
- Pré-chargement optionnel des tuiles voisines (prefetch) via worker asyncio

### Configuration cible (4 utilisateurs simultanés)
- Nginx : `worker_processes auto`, `worker_connections 1024`
- Flask : `threaded=True` avec Gunicorn (`--workers 4 --threads 2`) en production
- Redis : instance locale, 512 Mo max, politique d'éviction `allkeys-lru`
- Monitoring : logs Nginx access avec temps de réponse, taux de cache hit/miss

---

## Attribution des cas & traçabilité

### Champs de suivi
- `assigned_to` : username de l'utilisateur assigné au cas (dropdown dans l'interface admin)
- `created_by` : username ayant créé le cas (auto-rempli à la création)
- `modified_by` : dernier username ayant modifié le cas (mis à jour à chaque sauvegarde)

### Fonctionnement
- Dans l'onglet Informations, un dropdown « Attribué à » est affiché à côté du statut du cas, listé avec tous les utilisateurs actifs (admin, admin_centre, user)
- La liste des cas affiche l'attribution sous chaque cas (icône utilisateur + nom)
- Les soumissions PWA enregistrent automatiquement `_submitted_by`, `_submitted_at`, `_submitted_via` dans les données module JSON
- Les endpoints `/api/dossiers/pre-examen` et `/admin/api/pwa/submit` trackent l'utilisateur via la session Flask ou le champ `user` du payload

### Migration BDD
- Les colonnes `assigned_to`, `created_by`, `modified_by` sont ajoutées automatiquement par migration safe (ALTER TABLE si colonne manquante) au démarrage du serveur

---

## Roadmap

### Court terme
- **Migration PWA** : réécriture de l'app portable en Progressive Web App (Service Worker, manifest, offline-first)
- Modules radio, neuropath, placenta (dev actif)
- Intégration données Müller-Brochut/Maroun, correspondance HPO, calculs RCIU
- Raffinement templates CR, export Word
- Template gémellaires pour placenta
- Refactors frontend prévus :
  - Fusion externe + biométries
  - Fusion examen interne + prélèvements
  - Sous-section gémellaire au placenta
  - Refacto synthèse autour Jinja2
  - Champs date + options IMG/FCS/MFIU dans ATCD obstétricaux
  - Nomenclature ISCN pour CGH
  - Intégration MobiDetails pour NGS

### Moyen terme
- DINOv2 embedding + cosine matching pour appairage lames
- RAG multimodal avec CLIP (recherche texte↔image)
- Module génétique (PubCaseFinder, CNV Hub, MobiDetails APIs)

### Long terme
- Export BaMaRa, support DICOM
- ArucoCube hardware (échelle/orientation automatique en macro photo)
- Pipeline photogrammétrie fœtale → maillage 3D fermé (viewer Three.js + atlas de référence)

---

## Contexte institutionnel

- Réseau **SOFFOET** (Société Française de Fœtopathologie)
- Registre maladies rares **BaMaRa**
- Codage : CIM-10, Orphanet, HPO
- Formats CR : SOFFOET Type 1 (détaillé), SOFFOET Court
- Atlas neuropath de référence : **Shirley Bayer** (coupes coronales cerveau fœtal, 6.5–39 SA par demi-termes)

---

## Stack technique

| Couche | Technologies |
|---|---|
| App portable (PWA) | HTML/CSS/JS moderne, Service Worker, IndexedDB, Web APIs (caméra, fichiers) |
| Serveur | Python, Flask, SQLite, Jinja2, OpenSeadragon, OpenSlide |
| Cache & Perf | Nginx (reverse proxy, cache tuiles), Redis (sessions, métadonnées), Gunicorn |
| IA | Ollama/Mistral (CR), DINOv2 + CLIP (prévu) |
| Auth & Attribution | SHA-256 + sel, rôles (admin, admin_centre, user, spectator), attribution cas par utilisateur |
| Packaging | PyInstaller + OpenSlide binaries (prévu) |
| Legacy Android | Kotlin, WebView bridge, ES5 — en cours de remplacement par PWA |
| Versioning | Git (explicit `git add assets/`) |

---

## Retours utilisateurs à intégrer

- Grossesses précédentes : ajouter date, IMG, FCS, MFIU
- Pré-examen : CGH → nomenclature ISCN auto, lien CNV Hub ; NGS → MobiDetails auto, lien VCF
- Simplifier export/enregistrement : sauvegarde à la frappe, auto JSON serveur local, SQLite secondaire
- Examen externe : fusionner morpho + biométries + photos, app-first avec autofill
- Examen interne : fusionner avec prélèvements, suivi temps autopsique par organe
- Imagerie : algo aide au diag si MOC
- Placenta : ajouter gémellaires
- CR : passer les résultats de calculs biométriques dans les templates, sections éditables

---

## Comment m'aider

Quand je te pose une question sur FoetoPath :
1. L'app portable migre vers **PWA** — JS moderne autorisé (plus de contrainte ES5)
2. Le serveur est en **Flask** pur (pas de Django, pas de FastAPI)
3. Les données circulent en **JSON**
4. La terminologie médicale est en **français**
5. Les biométries utilisent des **SA** (Semaines d'Aménorrhée), pas des semaines de grossesse
6. Les templates CR utilisent **Jinja2**
7. Le viewer de lames utilise **OpenSeadragon** avec **OpenSlide** en backend
8. Si je parle de l'app Android legacy, les contraintes ES5/Kotlin bridge s'appliquent encore
