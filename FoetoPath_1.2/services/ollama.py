"""
Ollama service: LLM integration for text generation and reformulation.
"""

import logging
import subprocess as sp
import shutil
import time

import requests as http_requests

import db

log = logging.getLogger(__name__)


def _ollama_url() -> str:
    """Get configured Ollama URL."""
    return db.get_setting("ollama_url", "http://localhost:11434")


def check_ollama_status() -> dict:
    """
    Vérifie si Ollama tourne, le démarre si besoin, puis liste les modèles.
    Workflow : check → start si down → attente ready → ollama list

    Returns:
        Dictionary with status, running flag, started flag, url, and models list
    """
    url = _ollama_url()

    # 1. Check si déjà en ligne
    running = False
    try:
        r = http_requests.get(f"{url}/api/tags", timeout=3)
        if r.status_code == 200:
            running = True
    except Exception:
        log.debug("Ollama not running on %s", url, exc_info=True)

    # 2. Si pas en ligne, tenter de le démarrer
    started = False
    if not running:
        # Vérifier que ollama est installé
        if not shutil.which("ollama"):
            raise RuntimeError("Ollama n'est pas installé. Installez-le depuis https://ollama.ai")

        # Lancer 'ollama serve' en arrière-plan
        try:
            sp.Popen(
                ["ollama", "serve"],
                stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                start_new_session=True,
            )
            started = True
        except Exception as e:
            raise RuntimeError(f"Impossible de démarrer Ollama: {e}")

        # Attendre qu'il soit prêt (max 10s)
        for _ in range(20):
            time.sleep(0.5)
            try:
                r = http_requests.get(f"{url}/api/tags", timeout=2)
                if r.status_code == 200:
                    running = True
                    break
            except Exception:
                log.debug("Waiting for Ollama to start", exc_info=True)
                continue

        if not running:
            raise RuntimeError("Ollama démarré mais pas encore prêt. Réessayez dans quelques secondes.")

    # 3. Lister les modèles
    try:
        r = http_requests.get(f"{url}/api/tags", timeout=5)
        data = r.json()
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size_gb = round(m.get("size", 0) / (1024**3), 1)
            family = m.get("details", {}).get("family", "")
            params = m.get("details", {}).get("parameter_size", "")
            models.append({
                "name": name,
                "size_gb": size_gb,
                "family": family,
                "params": params,
            })

        return {
            "running": True,
            "started": started,
            "url": url,
            "models": models,
        }

    except Exception as e:
        raise RuntimeError(f"Erreur listing modèles: {e}")


def run_ollama_biometrics(case_id: int, report_text: str, model: str = None) -> dict:
    """
    Envoie le rapport biométrique à Ollama pour reformulation
    en texte médical rédigé.

    Args:
        case_id: Case ID
        report_text: Biometric report text
        model: Ollama model name (default: from settings)

    Returns:
        Dictionary with generated text, model, and token counts
    """
    if model is None:
        model = db.get_setting("ollama_model", "mistral")

    url = _ollama_url()

    prompt = f"""Tu es un médecin anatomopathologiste spécialisé en fœtopathologie, rédacteur expérimenté de comptes-rendus médicaux. Tu dois rédiger un texte médical professionnel à partir des données biométriques brutes ci-dessous.

═══ RÈGLES ABSOLUES ═══

1. VALEURS NUMÉRIQUES : tu ne MODIFIES, ARRONDIS ou OMETS aucune valeur numérique. Chaque masse, DS, ratio, mesure est retranscrite EXACTEMENT.

2. STYLE DE RÉDACTION :
   - Utiliser « on observe », « on note », « l'examen met en évidence », « il est retrouvé »
   - Phrases complètes, fluides, au présent de l'indicatif
   - Vocabulaire anatomopathologique standard français
   - Pas de tirets ni de listes à puces — que de la prose

3. REGROUPEMENT DES RÉSULTATS NORMAUX :
   - Les mesures et organes NORMAUX (entre -2 et +2 DS) sont regroupés en une ou deux phrases synthétiques
   - Exemple : « Les biométries corporelles (masse, VT, VC, PC, pied) sont dans les limites de la normale pour le terme de XX SA (réf. Guihard-Costa 2002). »
   - Exemple : « Les masses du thymus, du cœur, du foie, de la rate et des surrénales sont en accord avec le terme. »

4. MISE EN ÉVIDENCE DES ANOMALIES :
   - Chaque anomalie (|DS| > 2) fait l'objet d'une phrase dédiée avec la valeur, la DS, et le qualificatif
   - Exemple : « On note une diminution significative de la masse rénale combinée à 3,44 g (-3,14 DS), en dessous du 5ème percentile. »
   - Les anomalies modérées (1 < |DS| < 2) peuvent être signalées comme « à la limite inférieure/supérieure de la normale »

5. RATIOS :
   - Mentionner le LBWR (rapport poumon/poids corporel) avec sa valeur et son interprétation
   - Les ratios organe/masse ne sont mentionnés que s'ils sont anormaux

6. TU NE RAJOUTES AUCUNE :
   - Interprétation diagnostique ou étiologique
   - Hypothèse non contenue dans les données
   - Recommandation clinique
   - Référence bibliographique non citée dans les données

═══ DONNÉES À RÉDIGER ═══

{report_text}

═══ TEXTE RÉDIGÉ ═══
"""

    try:
        resp = http_requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 3000},
            },
            timeout=180,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama erreur {resp.status_code}: {resp.text}")

        result = resp.json()
        generated_text = result.get("response", "")

        # Save to database
        computed = db.get_module_data(case_id, "computed_biometrics") or {}
        computed["ollama_text"] = generated_text
        computed["ollama_model"] = model
        db.save_module_data(case_id, "computed_biometrics", computed)

        return {
            "generated_text": generated_text,
            "model": model,
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "completion_tokens": result.get("eval_count", 0),
        }

    except http_requests.ConnectionError:
        raise RuntimeError(f"Ollama non accessible sur {url}")
    except Exception as e:
        raise RuntimeError(f"Erreur Ollama: {e}")


def run_ollama_cr(case_id: int, cr_text: str, model: str = None) -> dict:
    """
    Envoie un texte CR à Ollama pour rédaction en langage naturel médical.

    Args:
        case_id: Case ID
        cr_text: Clinical report text
        model: Ollama model name (default: from settings)

    Returns:
        Dictionary with generated text, model, and token count
    """
    if model is None:
        model = db.get_setting("ollama_model", "mistral")

    url = _ollama_url()

    prompt = f"""Tu es un médecin anatomopathologiste spécialisé en fœtopathologie. Tu rédiges des comptes-rendus d'examen fœtopathologique depuis 20 ans. Tu dois transformer le compte-rendu structuré ci-dessous en un texte médical professionnel, tel qu'il serait envoyé à l'obstétricien prescripteur.

═══ RÈGLES ABSOLUES — VIOLATION INTERDITE ═══

1. VALEURS NUMÉRIQUES : tu RETRANSCRIS EXACTEMENT chaque valeur (masses en grammes, mesures en mm, DS, ratios, LBWR, scores). Aucun arrondi, aucune omission.

2. STYLE DE RÉDACTION :
   - Prose médicale professionnelle, phrases complètes au présent
   - Tournures : « on observe », « l'examen met en évidence », « on note », « il est retrouvé », « il n'est pas mis en évidence »
   - PAS de listes à puces, PAS de tirets — uniquement de la prose en paragraphes
   - Employer le « nous » de modestie quand nécessaire (« nous avons examiné »)

3. STRUCTURE À RESPECTER — tu conserves ces sections dans cet ordre :
   • RÉSUMÉ CLINIQUE : contexte obstétrical, indication, terme
   • ASPECT EXTERNE : état du fœtus, macération, puis morphologie. REGROUPER tout ce qui est normal en une phrase (« L'examen externe ne révèle pas de particularité morphologique significative au niveau du crâne, de la face, des oreilles, du nez, du cou, du thorax, de l'abdomen, du dos et des membres. »). Chaque anomalie fait l'objet d'une phrase dédiée.
   • BIOMÉTRIES : les mesures normales sont groupées (« Les biométries corporelles sont dans les limites de la normale pour XX SA »). Les mesures hors normes sont détaillées individuellement.
   • EXAMEN INTERNE : organe par organe. Les organes normaux peuvent être groupés. Les anomalies sont décrites en détail avec masse et DS. Mentionner le LBWR. Conclure sur la concordance des pesées avec le terme.
   • PRÉLÈVEMENTS : liste concise
   • CONCLUSION : synthèse en un paragraphe avec sexe, terme estimé, anomalies principales

4. REGROUPEMENT DES NORMAUX :
   - Morphologie externe : une phrase listant tous les items normaux
   - Biométries : une phrase regroupant les mesures concordantes
   - Organes : une phrase pour les organes dont la masse est en accord avec le terme
   - Puis chaque anomalie séparément

5. ANOMALIES :
   - Chaque anomalie morphologique est décrite en une phrase précise
   - Chaque anomalie biométrique mentionne la valeur exacte et la DS
   - Utiliser « significativement diminué » (|DS| > 2), « modérément diminué » (1-2 DS), « à la limite inférieure de la normale »

6. INTERDICTIONS STRICTES :
   - NE PAS inventer de données absentes du texte source
   - NE PAS ajouter d'interprétation diagnostique ou étiologique
   - NE PAS suggérer d'examens complémentaires
   - NE PAS ajouter de références bibliographiques
   - NE PAS modifier la conclusion si elle est déjà présente

═══ COMPTE-RENDU SOURCE ═══

{cr_text}

═══ COMPTE-RENDU RÉDIGÉ ═══
"""

    try:
        resp = http_requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 4000},
            },
            timeout=180,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama erreur {resp.status_code}")

        result = resp.json()
        generated = result.get("response", "")

        # Save to database
        db.save_module_data(case_id, "last_cr_ollama", {
            "text": generated,
            "model": model,
        })

        return {
            "generated_text": generated,
            "model": model,
            "tokens": result.get("eval_count", 0),
        }

    except Exception as e:
        raise RuntimeError(f"Erreur Ollama: {e}")
