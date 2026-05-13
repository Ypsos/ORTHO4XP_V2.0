# O4_Provider_Score.py
# Scoring qualité des providers ORTHO4XP V3
# Rôle : évalue automatiquement la qualité d'une image téléchargée
#         (bruit, compression, nuages, drift colorimétrique, risque seam)
#         et attribue un score global au provider pour cette tuile.
# Compatible V2 : ne modifie RIEN dans les fichiers existants.
# Multiplateforme : Windows, macOS, Linux.
# ------------------------------------------------------------------

import sys
import json
import time
import threading
import numpy
from pathlib import Path
from typing import Dict, Optional, Tuple
from PIL import Image

# Détection OS — même logique que O4_Imagery_Utils.py
if "dar" in sys.platform:
    _OS = "mac"
elif "win" in sys.platform:
    _OS = "windows"
else:
    _OS = "linux"

# Fichier de cache des scores — dans le dossier utilisateur
_SCORES_FILE = Path.home() / ".ortho4xp_provider_scores.json"
_lock        = threading.Lock()


# ------------------------------------------------------------------
# Structure d'un score
# ------------------------------------------------------------------
class ProviderScore:
    WEIGHTS = {
        "noise":       0.15,
        "compression": 0.20,
        "cloud":       0.30,
        "color_drift": 0.20,
        "seam_risk":   0.15,
    }

    def __init__(self, provider_code: str, tile_id: str):
        self.provider_code = provider_code
        self.tile_id       = tile_id
        self.noise         = 100.0
        self.compression   = 100.0
        self.cloud         = 100.0
        self.color_drift   = 100.0
        self.seam_risk     = 100.0
        self.global_score  = 100.0
        self.timestamp     = time.time()
        self.details       : Dict = {}

    def compute_global(self) -> float:
        self.global_score = (
            self.noise       * self.WEIGHTS["noise"]
          + self.compression * self.WEIGHTS["compression"]
          + self.cloud       * self.WEIGHTS["cloud"]
          + self.color_drift * self.WEIGHTS["color_drift"]
          + self.seam_risk   * self.WEIGHTS["seam_risk"]
        )
        return self.global_score

    def to_dict(self) -> Dict:
        return {
            "provider_code": self.provider_code,
            "tile_id":       self.tile_id,
            "noise":         round(self.noise,       1),
            "compression":   round(self.compression, 1),
            "cloud":         round(self.cloud,       1),
            "color_drift":   round(self.color_drift, 1),
            "seam_risk":     round(self.seam_risk,   1),
            "global_score":  round(self.global_score,1),
            "timestamp":     self.timestamp,
            "details":       self.details,
        }

    def label(self) -> str:
        g = self.global_score
        if g >= 85: return "✅ Excellent"
        if g >= 70: return "🟡 Correct"
        if g >= 50: return "🟠 Médiocre"
        return            "🔴 Mauvais"

    def __repr__(self):
        return (f"ProviderScore({self.provider_code} / {self.tile_id}) "
                f"→ {self.global_score:.1f}/100 {self.label()}")


# ------------------------------------------------------------------
# Analyse d'image — fonctions internes
# ------------------------------------------------------------------

def _score_noise(arr: numpy.ndarray) -> Tuple[float, Dict]:
    h, w = arr.shape[:2]
    block = 8
    stds  = []
    for y in range(0, h - block, block):
        for x in range(0, w - block, block):
            patch = arr[y:y+block, x:x+block].astype(numpy.float32)
            stds.append(patch.std())
    mean_std = float(numpy.mean(stds)) if stds else 0.0
    score = float(numpy.clip(100 - (mean_std - 5) * 2.5, 0, 100))
    return score, {"mean_local_std": round(mean_std, 2)}


def _score_compression(arr: numpy.ndarray) -> Tuple[float, Dict]:
    gray = arr.mean(axis=2).astype(numpy.float32)
    artifacts = []
    h, w = gray.shape
    for x in range(8, w, 8):
        if x < w:
            diff = numpy.abs(gray[:, x] - gray[:, x-1]).mean()
            artifacts.append(float(diff))
    mean_artifact = float(numpy.mean(artifacts)) if artifacts else 0.0
    score = float(numpy.clip(100 - mean_artifact * 3, 0, 100))
    return score, {"mean_block_gradient": round(mean_artifact, 2)}


def _score_cloud(arr: numpy.ndarray) -> Tuple[float, Dict]:
    r = arr[:,:,0].astype(numpy.float32)
    g = arr[:,:,1].astype(numpy.float32)
    b = arr[:,:,2].astype(numpy.float32)
    luminance  = (r + g + b) / 3.0
    saturation = (numpy.maximum(r, numpy.maximum(g, b))
                - numpy.minimum(r, numpy.minimum(g, b)))
    cloud_mask  = (luminance > 200) & (saturation < 30)
    cloud_ratio = float(cloud_mask.mean()) * 100.0
    score = float(numpy.clip(100 - cloud_ratio * 2, 0, 100))
    return score, {"cloud_ratio_pct": round(cloud_ratio, 2)}


def _score_color_drift(arr: numpy.ndarray) -> Tuple[float, Dict]:
    means = [arr[:,:,c].mean() for c in range(3)]
    spread = float(max(means) - min(means))
    score  = float(numpy.clip(100 - spread * 1.5, 0, 100))
    return score, {
        "mean_r": round(means[0], 1),
        "mean_g": round(means[1], 1),
        "mean_b": round(means[2], 1),
        "channel_spread": round(spread, 1),
    }


def _score_seam_risk(arr: numpy.ndarray) -> Tuple[float, Dict]:
    h, w   = arr.shape[:2]
    margin = max(1, h // 32)
    border = numpy.concatenate([
        arr[:margin,  :, :].reshape(-1, 3),
        arr[-margin:, :, :].reshape(-1, 3),
        arr[:, :margin,  :].reshape(-1, 3),
        arr[:, -margin:, :].reshape(-1, 3),
    ], axis=0).astype(numpy.float32)
    center      = arr[h//4:3*h//4, w//4:3*w//4, :].reshape(-1, 3).astype(numpy.float32)
    border_mean = border.mean(axis=0)
    center_mean = center.mean(axis=0)
    drift = float(numpy.abs(border_mean - center_mean).mean())
    score = float(numpy.clip(100 - drift * 2, 0, 100))
    return score, {
        "border_mean": [round(float(v), 1) for v in border_mean],
        "center_mean": [round(float(v), 1) for v in center_mean],
        "edge_drift":  round(drift, 1),
    }


# ------------------------------------------------------------------
# Affichage log ORTHO4XP
# ------------------------------------------------------------------
def _log_score(score: ProviderScore):
    msg = (
        f"[ProviderScore] {score.provider_code} / {score.tile_id}\n"
        f"  Bruit        : {score.noise:.1f}/100\n"
        f"  Compression  : {score.compression:.1f}/100\n"
        f"  Nuages       : {score.cloud:.1f}/100\n"
        f"  Colorimétrie : {score.color_drift:.1f}/100\n"
        f"  Seam risk    : {score.seam_risk:.1f}/100\n"
        f"  SCORE GLOBAL : {score.global_score:.1f}/100  {score.label()}"
    )
    try:
        import O4_UI_Utils as UI
        UI.vprint(1, msg)
    except Exception:
        print(msg)


# ------------------------------------------------------------------
# Fonction principale d'évaluation
# ------------------------------------------------------------------
def evaluate(image: Image.Image,
             provider_code: str,
             tile_id: str,
             save: bool = True) -> ProviderScore:
    score = ProviderScore(provider_code, tile_id)

    thumb = image.convert("RGB").resize((512, 512), Image.BICUBIC)
    arr   = numpy.array(thumb, dtype=numpy.uint8)

    score.noise,       d1 = _score_noise(arr)
    score.compression, d2 = _score_compression(arr)
    score.cloud,       d3 = _score_cloud(arr)
    score.color_drift, d4 = _score_color_drift(arr)
    score.seam_risk,   d5 = _score_seam_risk(arr)

    score.details = {**d1, **d2, **d3, **d4, **d5}
    score.compute_global()

    _log_score(score)

    if save:
        save_score(score)

    return score


# ------------------------------------------------------------------
# Cache des scores (lecture / écriture)
# ------------------------------------------------------------------
def save_score(score: ProviderScore):
    with _lock:
        try:
            data = _load_all_scores()
            key  = f"{score.provider_code}::{score.tile_id}"
            data[key] = score.to_dict()
            _SCORES_FILE.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


def _load_all_scores() -> Dict:
    try:
        if _SCORES_FILE.exists():
            return json.loads(_SCORES_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def get_score(provider_code: str, tile_id: str) -> Optional[Dict]:
    data = _load_all_scores()
    key  = f"{provider_code}::{tile_id}"
    return data.get(key)


def get_best_provider(tile_id: str, provider_codes: list) -> Optional[str]:
    best_code  = None
    best_score = -1.0
    for code in provider_codes:
        s = get_score(code, tile_id)
        if s and s.get("global_score", 0) > best_score:
            best_score = s["global_score"]
            best_code  = code
    return best_code


def clear_scores(provider_code: Optional[str] = None):
    with _lock:
        try:
            if provider_code is None:
                _SCORES_FILE.write_text("{}", encoding="utf-8")
                print("[ProviderScore] Cache vidé.")
            else:
                data = _load_all_scores()
                keys_to_del = [k for k in data if k.startswith(f"{provider_code}::")]
                for k in keys_to_del:
                    del data[k]
                _SCORES_FILE.write_text(
                    json.dumps(data, indent=2), encoding="utf-8"
                )
                print(f"[ProviderScore] {len(keys_to_del)} score(s) supprimé(s) pour {provider_code}.")
        except Exception:
            pass


def report_all() -> str:
    data = _load_all_scores()
    if not data:
        return "Aucun score enregistré."
    lines = [f"{'Provider':<20} {'Tuile':<25} {'Score':>6}  Qualité"]
    lines.append("-" * 70)
    for key, s in sorted(data.items(), key=lambda x: -x[1].get("global_score", 0)):
        code  = s.get("provider_code", "?")
        tid   = s.get("tile_id",       "?")
        g     = s.get("global_score",   0)
        label = ("✅ Excellent" if g >= 85 else
                 "🟡 Correct"  if g >= 70 else
                 "🟠 Médiocre" if g >= 50 else
                 "🔴 Mauvais")
        lines.append(f"{code:<20} {tid:<25} {g:>6.1f}  {label}")
    return "\n".join(lines)
