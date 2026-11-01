# =====================================================================
# voice_polly.py (Phase 5 - étape 5.4) - Synthèse vocale avec Amazon Polly
# Lit la version courte de la recommandation (output/recommendation_voice.txt)
# et produit un fichier audio MP3 en français (voix neuronale « Léa »).
# Le fichier est ensuite lu automatiquement par l'interface Streamlit.
# Sortie : output/recommendation.mp3
# =====================================================================
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "output")
polly = boto3.client("polly", region_name=REGION)
MAX_CHARS = 2900                     # limite de Polly : 3000 caractères par appel


def prepare(text):
    """Rend le texte agréable à l'oral (noms techniques lisibles)."""
    text = text.replace("_", " ")                       # customer_id -> customer id
    text = text.replace("TOPSIS", "Topsis").replace("WSM", "score pondéré")
    return re.sub(r"\s+", " ", text).strip()


def chunks(text):
    """Découpe en morceaux de moins de 3000 caractères, sans couper une phrase."""
    parts, cur = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(cur) + len(sentence) + 1 > MAX_CHARS:
            parts.append(cur)
            cur = ""
        cur += sentence + " "
    return parts + ([cur] if cur.strip() else [])


def synthesize(text, voice="Lea"):
    """Appelle Polly ; voix neuronale si disponible, sinon voix standard."""
    for engine in ("neural", "standard"):
        try:
            r = polly.synthesize_speech(Text=text, OutputFormat="mp3", VoiceId=voice,
                                       Engine=engine, LanguageCode="fr-FR")
            return r["AudioStream"].read(), engine
        except polly.exceptions.EngineNotSupportedException:
            continue
        except Exception as e:
            if "engine" in str(e).lower():
                continue
            raise
    raise RuntimeError("Aucun moteur Polly disponible pour cette voix dans la région.")


if __name__ == "__main__":
    text = prepare(open(os.path.join(OUT, "recommendation_voice.txt"), encoding="utf-8").read())
    audio, engine = b"", None
    for part in chunks(text):
        data, engine = synthesize(part)
        audio += data                                   # les segments MP3 se concatènent
    path = os.path.join(OUT, "recommendation.mp3")
    open(path, "wb").write(audio)
    price = 16 if engine == "neural" else 4             # $ par million de caractères
    print(f"Voix : Léa (fr-FR, moteur {engine})")
    print(f"Texte : {len(text)} caractères | coût estimé : {len(text) / 1e6 * price:.4f} $")
    print(f"Audio : {path} ({len(audio) / 1024:.0f} Ko)")
    if "--play" in sys.argv:
        os.startfile(path) if os.name == "nt" else None