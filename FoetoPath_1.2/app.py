#!/usr/bin/env python3
"""
FoetoPath Server — Viewer + Admin + Appairage

Flask server combining:
  - MRXS/WSI slide viewer (OpenSlide + OpenSeadragon)
  - Case administration & SQLite database
  - Phone sync (ADB) with auto-import
  - Slide/macro photo pairing table

Usage:
    python app.py                                    # Start on port 5000
    python app.py --port 8080                        # Custom port
    python app.py --root /path/to/slides             # Pre-set slide folder
    python app.py --data-dir /path/to/foetopath/data # DB & foetus data dir
"""

import argparse
import io
import json
import logging
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, send_from_directory, url_for
from openslide import OpenSlide
from openslide.deepzoom import DeepZoomGenerator
from PIL import Image

log = logging.getLogger(__name__)

# ── Setup structured logging ───────────────────────────────────────────────
from utils.logging_config import setup_logging
setup_logging()

# ── Admin & BDD ────────────────────────────────────────────────────────────
import db as foetopath_db
from admin_bp import admin_bp

# ── Placenta ──────────────────────────────────────────────────────────────
import placenta_db
from placenta_bp import placenta_bp

# ── Authentification ─────────────────────────────────────────────────────
import auth_db
from auth_bp import auth_bp, login_required

app = Flask(__name__)
app.json.sort_keys = False  # Préserver l'ordre des OrderedDict dans les réponses JSON
app.secret_key = os.environ.get("FOETOPATH_SECRET", "foetopath-dev-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 480  # 8 minutes par défaut

# Rafraîchir la session à chaque requête + adapter le timeout dynamique
from flask import session as flask_session
from datetime import timedelta
@app.before_request
def _refresh_session():
    flask_session.modified = True
    # Adapter le lifetime au paramètre idle_timeout_min (1-30, défaut 8)
    try:
        settings = db.get_all_settings()
        mins = int(settings.get('idle_timeout_min', 8))
        mins = max(1, min(30, mins))
        app.permanent_session_lifetime = timedelta(minutes=mins)
    except Exception:
        log.debug("Failed to update session lifetime from settings", exc_info=True)

# ── Enregistrer les blueprints ────────────────────────────────────────────
app.register_blueprint(auth_bp)           # /auth
app.register_blueprint(admin_bp)          # /admin
app.register_blueprint(placenta_bp)       # /placenta

# ── Configuration (centralisée dans config.py) ────────────────────────────
from config import (
    TILE_SIZE, TILE_OVERLAP, TILE_FORMAT, TILE_QUALITY, THUMBNAIL_SIZE,
    SLIDE_EXTENSIONS, PHOTO_EXTENSIONS, MIME_MAP,
)


# ── Slide Cache ────────────────────────────────────────────────────────────
@lru_cache(maxsize=10)
def get_slide(slide_path: str) -> OpenSlide:
    """Open and cache an OpenSlide object."""
    return OpenSlide(slide_path)


@lru_cache(maxsize=10)
def get_dz(slide_path: str) -> DeepZoomGenerator:
    """Create and cache a DeepZoomGenerator."""
    slide = get_slide(slide_path)
    return DeepZoomGenerator(slide, tile_size=TILE_SIZE, overlap=TILE_OVERLAP, limit_bounds=True)


def find_slides(folder: str) -> list[dict]:
    """Find all supported slide files in a folder."""
    slides = []
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return slides
    for f in sorted(folder_path.iterdir()):
        if f.suffix.lower() in SLIDE_EXTENSIONS and f.is_file():
            slides.append({
                "name": f.stem,
                "filename": f.name,
                "path": str(f),
                "extension": f.suffix.lower(),
            })
    return slides


def find_photos(folder: str) -> list[dict]:
    """Find all photo/image files in a folder."""
    photos = []
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return photos
    for f in sorted(folder_path.iterdir()):
        if f.suffix.lower() in PHOTO_EXTENSIONS and f.is_file():
            # Skip very small files (thumbnails, icons)
            try:
                size = f.stat().st_size
                if size < 1024:  # < 1KB
                    continue
            except OSError:
                log.debug("File stat error: %s", f, exc_info=True)
                continue
            photos.append({
                "name": f.stem,
                "filename": f.name,
                "path": str(f),
                "extension": f.suffix.lower(),
                "size_kb": round(size / 1024, 1),
            })
    return photos


def find_cases(root: str) -> list[dict]:
    """Find all subfolders (cases) that contain slides or photos."""
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    cases = []
    # Check root itself
    root_slides = find_slides(root)
    root_photos = find_photos(root)
    if root_slides or root_photos:
        cases.append({
            "name": root_path.name,
            "path": str(root_path),
            "slide_count": len(root_slides),
            "photo_count": len(root_photos),
            "is_root": True,
        })

    # Check subfolders
    for d in sorted(root_path.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            slides = find_slides(str(d))
            photos = find_photos(str(d))
            if slides or photos:
                cases.append({
                    "name": d.name,
                    "path": str(d),
                    "slide_count": len(slides),
                    "photo_count": len(photos),
                    "is_root": False,
                })
    return cases


# ── Routes PWA (servies à la racine pour accès direct) ────────────────────

def _check_pwa_access():
    """Refuse l'accès aux PWA pour les spectateurs (lecture seule)."""
    role = session.get("user_role", "")
    if role == "spectator":
        return redirect(url_for("hub"))
    return None


PWA_PLACENTAS_DIR = Path(__file__).parent / "pwa" / "placentas"


@app.route("/pwa/placentas/")
def pwa_placentas_index():
    """Sert la page d'accueil de la PWA Placenta."""
    block = _check_pwa_access()
    if block:
        return block
    return send_from_directory(str(PWA_PLACENTAS_DIR), "index.html")


@app.route("/pwa/placentas/<path:filename>")
def pwa_placentas_static(filename):
    """Sert les fichiers statiques de la PWA Placenta."""
    block = _check_pwa_access()
    if block:
        return block
    return send_from_directory(str(PWA_PLACENTAS_DIR), filename)


# ── PWA Fœtus ─────────────────────────────────────────────────────────────

PWA_FOET_DIR = Path(__file__).parent / "pwa" / "foet"


@app.route("/pwa/foet/")
def pwa_foet_index():
    """Sert la page d'accueil de la PWA Fœtus."""
    block = _check_pwa_access()
    if block:
        return block
    return send_from_directory(str(PWA_FOET_DIR), "index.html")


@app.route("/pwa/foet/<path:filename>")
def pwa_foet_static(filename):
    """Sert les fichiers statiques de la PWA Fœtus."""
    block = _check_pwa_access()
    if block:
        return block
    return send_from_directory(str(PWA_FOET_DIR), filename)


# ── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def hub():
    """Page hub — point d'entrée principal avec navigation."""
    return render_template("hub.html")


@app.route("/viewer")
@login_required
def viewer():
    """Viewer de lames. Accepts query params:
       ?root=/path/to/slides          → pre-fill and auto-load folder
       ?slide=/path/to.mrxs           → auto-open specific slide
    """
    default_root = app.config.get("DEFAULT_ROOT", "")
    auto_root = request.args.get("root", "")
    auto_slide = request.args.get("slide", "")
    case_id = request.args.get("case_id", "")
    return render_template(
        "index.html",
        default_root=auto_root or default_root,
        auto_root=auto_root,
        auto_slide=auto_slide,
        case_id=case_id,
    )


@app.route("/api/browse", methods=["POST"])
def browse():
    """List cases (subfolders with slides) in a root directory."""
    data = request.get_json()
    root = data.get("root", "")
    if not root or not os.path.isdir(root):
        return jsonify({"error": "Dossier invalide", "cases": []}), 400
    cases = find_cases(root)
    return jsonify({"cases": cases, "root": root})


@app.route("/api/slides", methods=["POST"])
def slides():
    """List slides and photos in a case folder."""
    data = request.get_json()
    folder = data.get("folder", "")
    if not folder or not os.path.isdir(folder):
        return jsonify({"error": "Dossier invalide", "slides": [], "photos": []}), 400
    slide_list = find_slides(folder)
    photo_list = find_photos(folder)
    return jsonify({"slides": slide_list, "photos": photo_list, "folder": folder})


@app.route("/api/slide/info", methods=["POST"])
def slide_info():
    """Get slide metadata."""
    data = request.get_json()
    path = data.get("path", "")
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        slide = get_slide(path)
        dz = get_dz(path)
        props = dict(slide.properties)
        return jsonify({
            "dimensions": slide.dimensions,
            "level_count": slide.level_count,
            "level_dimensions": list(slide.level_dimensions),
            "dz_level_count": dz.level_count,
            "tile_size": TILE_SIZE,
            "overlap": TILE_OVERLAP,
            "properties": {k: v for k, v in props.items() if len(v) < 500},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/slide/dzi", methods=["POST"])
def slide_dzi():
    """Generate DZI XML descriptor for OpenSeadragon."""
    data = request.get_json()
    path = data.get("path", "")
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        dz = get_dz(path)
        resp = dz.get_dzi(TILE_FORMAT)
        return Response(resp, mimetype="application/xml")
    except Exception as e:
        return Response(f"<error>{e}</error>", status=500, mimetype="application/xml")


@app.route("/api/slide/tile/<int:level>/<int:col>_<int:row>.<fmt>")
def slide_tile(level: int, col: int, row: int, fmt: str):
    """Serve a single tile. Slide path passed as query param."""
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        dz = get_dz(path)
        tile = dz.get_tile(level, (col, row))
        buf = io.BytesIO()
        tile.save(buf, format=TILE_FORMAT, quality=TILE_QUALITY)
        buf.seek(0)
        return Response(buf.read(), mimetype=f"image/{TILE_FORMAT}")
    except (ValueError, KeyError):
        abort(404)
    except Exception as e:
        abort(500)


@app.route("/api/slide/thumbnail")
def slide_thumbnail():
    """Generate a thumbnail for the carousel."""
    path = request.args.get("path", "")
    width = int(request.args.get("w", THUMBNAIL_SIZE[0]))
    height = int(request.args.get("h", THUMBNAIL_SIZE[1]))
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        slide = get_slide(path)
        thumb = slide.get_thumbnail((width, height))
        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return Response(buf.read(), mimetype="image/jpeg")
    except Exception as e:
        # Return a placeholder
        img = Image.new("RGB", (width, height), (40, 40, 50))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return Response(buf.read(), mimetype="image/jpeg")


@app.route("/api/slide/label")
def slide_label():
    """Get the label/macro image if available."""
    path = request.args.get("path", "")
    img_type = request.args.get("type", "label")  # label or macro
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        slide = get_slide(path)
        images = slide.associated_images
        if img_type in images:
            img = images[img_type]
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            buf.seek(0)
            return Response(buf.read(), mimetype="image/jpeg")
        abort(404)
    except Exception:
        log.debug("Failed to load associated image %s", img_type, exc_info=True)
        abort(404)


# ── Photo Routes ───────────────────────────────────────────────────────────
# MIME_MAP importé depuis config.py


@app.route("/api/photo/serve")
def photo_serve():
    """Serve a full-resolution photo."""
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        abort(404)
    ext = Path(path).suffix.lower()
    if ext not in PHOTO_EXTENSIONS:
        abort(403)
    mime = MIME_MAP.get(ext, "image/jpeg")
    try:
        with open(path, "rb") as f:
            data = f.read()
        return Response(data, mimetype=mime)
    except Exception:
        log.warning("Failed to serve photo: %s", path, exc_info=True)
        abort(500)


@app.route("/api/photo/thumbnail")
def photo_thumbnail():
    """Generate a thumbnail for a photo."""
    path = request.args.get("path", "")
    width = int(request.args.get("w", 192))
    height = int(request.args.get("h", 192))
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        img = Image.open(path)
        img.thumbnail((width, height), Image.LANCZOS)
        # Convert to RGB if needed (for RGBA/palette images)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        buf_format = "JPEG"
        img.save(buf, format=buf_format, quality=85)
        buf.seek(0)
        return Response(buf.read(), mimetype="image/jpeg")
    except Exception:
        log.debug("Failed to generate thumbnail for photo: %s", path, exc_info=True)
        # Placeholder
        img = Image.new("RGB", (width, height), (40, 40, 50))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return Response(buf.read(), mimetype="image/jpeg")


# ── Annotation Routes ──────────────────────────────────────────────────────

def get_annotation_path(root: str, slide_path: str) -> Path:
    """Get the GeoJSON annotation file path for a given slide.
    Stored in {root}/annotations/{slide_stem}.geojson
    """
    root_path = Path(root)
    slide_stem = Path(slide_path).stem
    ann_dir = root_path / "annotations"
    ann_dir.mkdir(parents=True, exist_ok=True)
    return ann_dir / f"{slide_stem}.geojson"


def get_slide_calibration(slide_path: str) -> dict:
    """Extract calibration metadata from a slide."""
    try:
        slide = get_slide(slide_path)
        props = slide.properties
        w, h = slide.dimensions

        # MPP (microns per pixel)
        mpp_x = float(props.get("openslide.mpp-x", 0))
        mpp_y = float(props.get("openslide.mpp-y", 0))

        # Bounds
        bounds_x = int(props.get("openslide.bounds-x", 0))
        bounds_y = int(props.get("openslide.bounds-y", 0))
        bounds_w = int(props.get("openslide.bounds-width", w))
        bounds_h = int(props.get("openslide.bounds-height", h))

        # Objective power
        objective = props.get("openslide.objective-power", "")

        return {
            "dimensions_px": [w, h],
            "mpp_x": mpp_x,
            "mpp_y": mpp_y,
            "bounds": {
                "x": bounds_x,
                "y": bounds_y,
                "width": bounds_w,
                "height": bounds_h,
            },
            "objective_power": objective,
            "vendor": props.get("openslide.vendor", ""),
        }
    except Exception:
        log.debug("Failed to extract slide metadata", exc_info=True)
        return {}


@app.route("/api/annotations/save", methods=["POST"])
def annotations_save():
    """Save annotations as GeoJSON."""
    data = request.get_json()
    root = data.get("root", "")
    slide_path = data.get("slide_path", "")
    features = data.get("features", [])

    if not root or not slide_path:
        return jsonify({"error": "Paramètres manquants"}), 400

    # Get calibration from the slide
    calibration = get_slide_calibration(slide_path)
    mpp_x = calibration.get("mpp_x", 0)
    mpp_y = calibration.get("mpp_y", 0)

    # Build features with dual coordinates (pixels + micrometers)
    geojson_features = []
    for feat in features:
        coords_px = feat.get("coordinates", [])
        props = feat.get("properties", {})

        # Convert pixel coordinates to micrometers
        coords_um = []
        if mpp_x > 0 and mpp_y > 0:
            for ring in coords_px:
                coords_um.append([[pt[0] * mpp_x, pt[1] * mpp_y] for pt in ring])

        geojson_feat = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": coords_px,
            },
            "properties": {
                **props,
                "coordinates_um": coords_um if coords_um else None,
                "unit_px": "pixels (absolute, level 0)",
                "unit_um": f"micrometers (mpp_x={mpp_x}, mpp_y={mpp_y})" if mpp_x > 0 else None,
            },
        }
        geojson_features.append(geojson_feat)

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "slide_name": Path(slide_path).name,
            "slide_path": slide_path,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "generator": "FoetoPath Slide Viewer",
            "annotation_levels": {
                "1": "Macro",
                "2": "Cytoarchitecture",
                "3": "Cellulaire",
            },
            **calibration,
        },
        "features": geojson_features,
    }

    # Write file
    try:
        ann_path = get_annotation_path(root, slide_path)
        with open(ann_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, indent=2, ensure_ascii=False)
        return jsonify({
            "ok": True,
            "path": str(ann_path),
            "feature_count": len(geojson_features),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/annotations/load")
def annotations_load():
    """Load annotations GeoJSON for a slide."""
    root = request.args.get("root", "")
    slide_path = request.args.get("slide_path", "")

    if not root or not slide_path:
        return jsonify({"error": "Paramètres manquants"}), 400

    ann_path = get_annotation_path(root, slide_path)
    if not ann_path.is_file():
        return jsonify({"features": [], "exists": False})

    try:
        with open(ann_path, "r", encoding="utf-8") as f:
            geojson = json.load(f)
        return jsonify({
            "exists": True,
            "path": str(ann_path),
            **geojson,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/slide/macro/info")
def slide_macro_info():
    """Get macro image dimensions for annotation coordinate mapping."""
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        abort(404)
    try:
        slide = get_slide(path)
        images = slide.associated_images
        for img_type in ("macro", "label"):
            if img_type in images:
                img = images[img_type]
                w, h = img.size
                return jsonify({
                    "type": img_type,
                    "width": w,
                    "height": h,
                    "available_types": list(images.keys()),
                })
        return jsonify({"error": "Pas d'image macro disponible"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Endpoint pour le formulaire pré-examen ─────────────────────────────────

@app.route("/api/dossiers/pre-examen", methods=["POST"])
def receive_pre_exam():
    """
    Endpoint appelé par le formulaire pré-examen (sendToServer).
    Importe les données directement dans la BDD SQLite.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données requises"}), 400

    admin_data = data.get("case_admin", data)
    numero = admin_data.get("numero_dossier")
    if not numero:
        return jsonify({"error": "Numéro de dossier requis"}), 400

    # Tracking utilisateur (session si connecté, sinon champ 'user' du payload)
    submit_user = session.get("username", "") or data.get("user", "pwa")
    admin_data["modified_by"] = submit_user

    existing = foetopath_db.get_case_by_numero(numero)
    if existing:
        case_id = existing["id"]
        foetopath_db.update_case(case_id, admin_data)
    else:
        admin_data.setdefault("created_by", submit_user)
        case_id = foetopath_db.create_case(admin_data)

    # Sauvegarder les sous-tables comme données de modules
    for key in ["atcd_maternels", "grossesse_en_cours", "examens_prenataux", "atcd_obstetricaux"]:
        if key in data:
            foetopath_db.save_module_data(case_id, key, data[key])

    return jsonify({"id": case_id, "message": "Dossier enregistré"})


# ── Main ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FoetoPath Server (Viewer + Admin)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--root", default="", help="Default root folder for slides")
    parser.add_argument("--data-dir", default="", help="Directory for FoetoPath data (DB, foetus folders)")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    app.config["DEFAULT_ROOT"] = args.root

    # ── Initialiser les BDD SQLite ────────────────────────────────────────
    data_dir = args.data_dir or os.path.expanduser("~/Documents/FoetoPath")
    db_path = foetopath_db.init_db(data_dir)
    plac_db_path = placenta_db.init_db(data_dir)
    auth_db_path = auth_db.init_db(data_dir)

    # Mettre à jour les settings depuis les arguments CLI
    if args.root:
        foetopath_db.set_setting("slides_root", args.root)

    print(f"\n{'='*60}")
    print(f"  FoetoPath Server")
    print(f"  Hub         : http://{args.host}:{args.port}/")
    print(f"  Viewer      : http://{args.host}:{args.port}/viewer")
    print(f"  Admin Fœtus : http://{args.host}:{args.port}/admin")
    print(f"  Admin Plac. : http://{args.host}:{args.port}/admin/placenta")
    print(f"  PWA Fœtus   : http://{args.host}:{args.port}/pwa/foet/")
    print(f"  PWA Placenta: http://{args.host}:{args.port}/pwa/placentas/")
    if args.root:
        print(f"  Slides      : {args.root}")
    print(f"  DB Fœtus    : {db_path}")
    print(f"  DB Placenta : {plac_db_path}")
    print(f"  DB Auth     : {auth_db_path}")
    print(f"  Login       : http://{args.host}:{args.port}/auth/login")
    print(f"  Admin défaut: Remi_Mathevet / R1m2E3a4")
    print(f"{'='*60}\n")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
