"""
O4_Score_Logger.py
Ortho4XP V3 — Lot B / Livrable B2
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)
Version : 1.0 — Mai 2026

Rôle :
    - Enregistrer les scores providers avec horodatage complet
    - Exporter les scores au format CSV et JSON
    - Fournir des statistiques agrégées par provider
    - S'appuie sur O4_Provider_Score.py existant (pas de duplication)
    - Zéro cassure V2 : module autonome, rien modifié dans les fichiers existants

Utilisation :
    from O4_Score_Logger import ScoreLogger
    logger = ScoreLogger()
    logger.log(score)                     # enregistre un ProviderScore
    logger.export_csv("scores.csv")       # export CSV
    logger.export_json("scores.json")     # export JSON
    logger.print_summary()                # résumé console
"""

import os
import csv
import json
import time
import threading
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Import O4_Provider_Score (scoring existant — pas de duplication)
# ---------------------------------------------------------------------------
try:
    from O4_Provider_Score import ProviderScore
    _has_provider_score = True
except ImportError:
    _has_provider_score = False
    # Classe minimale pour fonctionner sans O4_Provider_Score
    class ProviderScore:
        def __init__(self, provider_code="", tile_id=""):
            self.provider_code = provider_code
            self.tile_id       = tile_id
            self.noise         = 100.0
            self.compression   = 100.0
            self.cloud         = 100.0
            self.color_drift   = 100.0
            self.seam_risk     = 100.0
            self.global_score  = 100.0
            self.timestamp     = time.time()
            self.details       = {}
        def to_dict(self):
            return {
                "provider_code": self.provider_code,
                "tile_id"      : self.tile_id,
                "noise"        : self.noise,
                "compression"  : self.compression,
                "cloud"        : self.cloud,
                "color_drift"  : self.color_drift,
                "seam_risk"    : self.seam_risk,
                "global_score" : self.global_score,
                "timestamp"    : self.timestamp,
                "details"      : self.details,
            }

# ---------------------------------------------------------------------------
# Import système de logs Ortho4XP
# ---------------------------------------------------------------------------
try:
    import O4_UI_Utils as UI
    def _log(msg):
        UI.lvprint(1, "[SCORE_LOG] " + msg)
    def _logwarn(msg):
        UI.lvprint(1, "[SCORE_LOG] ATTENTION : " + msg)
except ImportError:
    def _log(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [SCORE_LOG] " + msg)
    def _logwarn(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [SCORE_LOG] ATTENTION : " + msg)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))

# Dossier de sortie des exports
EXPORT_DIR       = os.path.join(_SCRIPT_DIR, "_score_exports")

# Fichier de log JSON interne (toutes les sessions)
_LOG_FILE        = os.path.join(EXPORT_DIR, "_score_log.json")

# Colonnes CSV exportées
CSV_COLUMNS = [
    "timestamp_iso", "provider_code", "tile_id",
    "global_score", "noise", "compression", "cloud",
    "color_drift", "seam_risk", "label",
]


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class ScoreLogger:
    """
    Logger de scores providers avec export CSV et JSON.

    Stocke tous les scores en mémoire pendant la session,
    et peut les exporter ou les persister à tout moment.
    """

    def __init__(self, auto_persist=True):
        """
        Paramètres :
            auto_persist : si True, chaque log() est aussi écrit dans
                           _score_log.json sur disque
        """
        self._lock         = threading.Lock()
        self._entries      = []       # liste de dicts — toutes les entrées session
        self._auto_persist = auto_persist
        os.makedirs(EXPORT_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Enregistrement d'un score
    # ------------------------------------------------------------------

    def log(self, score, extra=None):
        """
        Enregistre un score dans le logger.

        Paramètres :
            score : objet ProviderScore (de O4_Provider_Score.py)
                    ou dict compatible
            extra : dict optionnel de champs supplémentaires
                    ex: {"zoomlevel": 17, "lat": 48, "lon": 2}

        Retourne :
            dict de l'entrée enregistrée
        """
        # Accepte ProviderScore ou dict directement
        if hasattr(score, "to_dict"):
            d = score.to_dict()
        elif isinstance(score, dict):
            d = dict(score)
        else:
            _logwarn(f"log() : type non reconnu {type(score)}")
            return None

        # Enrichissement
        ts   = d.get("timestamp", time.time())
        entry = {
            "timestamp_iso" : datetime.fromtimestamp(ts).isoformat(),
            "timestamp"     : ts,
            "provider_code" : d.get("provider_code", "?"),
            "tile_id"       : d.get("tile_id",       "?"),
            "global_score"  : round(d.get("global_score",  0.0), 1),
            "noise"         : round(d.get("noise",         0.0), 1),
            "compression"   : round(d.get("compression",   0.0), 1),
            "cloud"         : round(d.get("cloud",         0.0), 1),
            "color_drift"   : round(d.get("color_drift",   0.0), 1),
            "seam_risk"     : round(d.get("seam_risk",     0.0), 1),
            "label"         : _score_label(d.get("global_score", 0.0)),
            "details"       : d.get("details", {}),
        }

        if extra and isinstance(extra, dict):
            entry.update(extra)

        with self._lock:
            self._entries.append(entry)

        if self._auto_persist:
            self._persist_entry(entry)

        _log(f"Score loggé : {entry['provider_code']} / "
             f"{entry['tile_id']} → {entry['global_score']}/100 "
             f"{entry['label']}")

        return entry

    # ------------------------------------------------------------------
    # Persistance interne
    # ------------------------------------------------------------------

    def _persist_entry(self, entry):
        """Ajoute l'entrée au fichier JSON de log interne."""
        try:
            existing = []
            if os.path.isfile(_LOG_FILE):
                with open(_LOG_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing.append(entry)
            with open(_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _logwarn(f"Persistance échouée : {e}")

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------

    def export_csv(self, filepath=None):
        """
        Exporte tous les scores de la session en CSV.

        Paramètres :
            filepath : chemin du fichier CSV
                       si None → EXPORT_DIR/scores_YYYYMMDD_HHMMSS.csv

        Retourne :
            Chemin du fichier créé, ou None en cas d'erreur.
        """
        if not filepath:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(EXPORT_DIR, f"scores_{ts}.csv")

        with self._lock:
            entries = list(self._entries)

        if not entries:
            _logwarn("export_csv() : aucun score à exporter")
            return None

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=CSV_COLUMNS,
                    extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(entries)

            _log(f"Export CSV : {len(entries)} ligne(s) → {filepath}")
            return filepath

        except Exception as e:
            _logwarn(f"export_csv() échoué : {e}")
            return None

    # ------------------------------------------------------------------
    # Export JSON
    # ------------------------------------------------------------------

    def export_json(self, filepath=None, pretty=True):
        """
        Exporte tous les scores de la session en JSON.

        Paramètres :
            filepath : chemin du fichier JSON
                       si None → EXPORT_DIR/scores_YYYYMMDD_HHMMSS.json
            pretty   : si True, JSON indenté (lisible)

        Retourne :
            Chemin du fichier créé, ou None en cas d'erreur.
        """
        if not filepath:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(EXPORT_DIR, f"scores_{ts}.json")

        with self._lock:
            entries = list(self._entries)

        if not entries:
            _logwarn("export_json() : aucun score à exporter")
            return None

        try:
            export_data = {
                "exported_at"   : datetime.now().isoformat(),
                "total_entries" : len(entries),
                "scores"        : entries,
            }
            indent = 2 if pretty else None
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=indent, ensure_ascii=False)

            _log(f"Export JSON : {len(entries)} entrée(s) → {filepath}")
            return filepath

        except Exception as e:
            _logwarn(f"export_json() échoué : {e}")
            return None

    # ------------------------------------------------------------------
    # Statistiques agrégées
    # ------------------------------------------------------------------

    def stats_by_provider(self):
        """
        Retourne des statistiques agrégées par provider.

        Retourne :
            dict {provider_code: {count, avg_score, min_score, max_score,
                                  avg_noise, avg_cloud, avg_compression,
                                  avg_color_drift, avg_seam_risk}}
        """
        with self._lock:
            entries = list(self._entries)

        if not entries:
            return {}

        agg = {}
        for e in entries:
            code = e.get("provider_code", "?")
            if code not in agg:
                agg[code] = {
                    "scores"       : [],
                    "noise"        : [],
                    "compression"  : [],
                    "cloud"        : [],
                    "color_drift"  : [],
                    "seam_risk"    : [],
                }
            agg[code]["scores"].append(e.get("global_score", 0.0))
            agg[code]["noise"].append(e.get("noise", 0.0))
            agg[code]["compression"].append(e.get("compression", 0.0))
            agg[code]["cloud"].append(e.get("cloud", 0.0))
            agg[code]["color_drift"].append(e.get("color_drift", 0.0))
            agg[code]["seam_risk"].append(e.get("seam_risk", 0.0))

        result = {}
        for code, data in agg.items():
            sc = data["scores"]
            result[code] = {
                "count"           : len(sc),
                "avg_score"       : round(sum(sc) / len(sc), 1),
                "min_score"       : round(min(sc), 1),
                "max_score"       : round(max(sc), 1),
                "avg_noise"       : round(sum(data["noise"])       / len(sc), 1),
                "avg_compression" : round(sum(data["compression"]) / len(sc), 1),
                "avg_cloud"       : round(sum(data["cloud"])       / len(sc), 1),
                "avg_color_drift" : round(sum(data["color_drift"]) / len(sc), 1),
                "avg_seam_risk"   : round(sum(data["seam_risk"])   / len(sc), 1),
            }
        return result

    def best_provider(self):
        """
        Retourne le code du meilleur provider (score moyen le plus élevé).

        Retourne :
            str code provider, ou None si aucun score enregistré.
        """
        stats = self.stats_by_provider()
        if not stats:
            return None
        return max(stats, key=lambda c: stats[c]["avg_score"])

    def print_summary(self):
        """
        Affiche un résumé lisible dans les logs Ortho4XP.
        """
        stats = self.stats_by_provider()
        if not stats:
            _log("Aucun score enregistré pour cette session.")
            return

        lines = [
            f"\n{'='*70}",
            f"  RÉSUMÉ SCORES PROVIDERS — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'='*70}",
            f"  {'Provider':<18} {'N':>4} {'Moy':>6} {'Min':>6} {'Max':>6}  "
            f"{'Bruit':>6} {'Nuages':>7} {'Seam':>6}  Qualité",
            f"  {'-'*65}",
        ]

        for code, s in sorted(stats.items(),
                               key=lambda x: -x[1]["avg_score"]):
            label = _score_label(s["avg_score"])
            lines.append(
                f"  {code:<18} {s['count']:>4} {s['avg_score']:>6.1f} "
                f"{s['min_score']:>6.1f} {s['max_score']:>6.1f}  "
                f"{s['avg_noise']:>6.1f} {s['avg_cloud']:>7.1f} "
                f"{s['avg_seam_risk']:>6.1f}  {label}"
            )

        lines.append(f"{'='*70}\n")
        msg = "\n".join(lines)
        try:
            import O4_UI_Utils as _UI
            _UI.vprint(1, msg)
        except Exception:
            print(msg)

    def clear(self):
        """Vide les entrées en mémoire (ne supprime pas les fichiers sur disque)."""
        with self._lock:
            n = len(self._entries)
            self._entries.clear()
        _log(f"Logger vidé — {n} entrée(s) supprimées de la mémoire")

    def count(self):
        """Retourne le nombre de scores enregistrés dans cette session."""
        with self._lock:
            return len(self._entries)


# ---------------------------------------------------------------------------
# Fonction utilitaire interne
# ---------------------------------------------------------------------------

def _score_label(g):
    """Retourne le label qualité correspondant à un score global."""
    if g >= 85: return "✅ Excellent"
    if g >= 70: return "🟡 Correct"
    if g >= 50: return "🟠 Médiocre"
    return              "🔴 Mauvais"


# ---------------------------------------------------------------------------
# Instance globale partagée
# ---------------------------------------------------------------------------
default_logger = ScoreLogger()


# ---------------------------------------------------------------------------
# Test standalone (python O4_Score_Logger.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile

    print("=== Test O4_Score_Logger ===\n")

    logger = ScoreLogger(auto_persist=False)

    # Créer des scores de test
    def _make_score(code, tile, g, n=90, c=85, cl=95, cd=88, sr=92):
        s = ProviderScore(code, tile)
        s.noise        = n
        s.compression  = c
        s.cloud        = cl
        s.color_drift  = cd
        s.seam_risk    = sr
        s.global_score = g
        s.timestamp    = time.time()
        return s

    scores = [
        _make_score("FR_IGN", "+48+002", 88.5),
        _make_score("FR_IGN", "+49+002", 72.0, n=70, c=75),
        _make_score("OSM",    "+48+002", 65.0, cl=60),
        _make_score("Bing",   "+48+002", 91.0, n=95, c=92),
        _make_score("Bing",   "+49+002", 55.0, cl=40),
    ]

    # Test 1 : log()
    for s in scores:
        entry = logger.log(s)
        assert entry is not None
    assert logger.count() == len(scores)
    print(f"[OK] log() : {logger.count()} scores enregistrés")

    # Test 2 : log() avec dict directement
    entry_dict = logger.log({
        "provider_code": "TEST",
        "tile_id"      : "+50+003",
        "global_score" : 78.0,
        "noise"        : 80.0,
        "compression"  : 75.0,
        "cloud"        : 82.0,
        "color_drift"  : 77.0,
        "seam_risk"    : 76.0,
        "timestamp"    : time.time(),
    })
    assert entry_dict is not None
    print("[OK] log() avec dict fonctionne")

    # Test 3 : stats_by_provider
    stats = logger.stats_by_provider()
    assert "FR_IGN" in stats
    assert "Bing"   in stats
    assert stats["FR_IGN"]["count"] == 2
    assert stats["Bing"]["count"]   == 2
    print(f"[OK] stats_by_provider() : {list(stats.keys())}")

    # Test 4 : best_provider
    best = logger.best_provider()
    assert best is not None
    print(f"[OK] best_provider() = {best}")

    # Test 5 : export CSV
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        csv_path = f.name
    result_csv = logger.export_csv(csv_path)
    assert result_csv and os.path.isfile(result_csv)
    with open(result_csv) as f:
        lines = f.readlines()
    assert len(lines) == logger.count() + 1  # +1 pour l'entête
    print(f"[OK] export_csv() : {len(lines)-1} lignes exportées")
    os.remove(csv_path)

    # Test 6 : export JSON
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        json_path = f.name
    result_json = logger.export_json(json_path)
    assert result_json and os.path.isfile(result_json)
    with open(result_json) as f:
        data = json.load(f)
    assert data["total_entries"] == logger.count()
    assert len(data["scores"])   == logger.count()
    print(f"[OK] export_json() : {data['total_entries']} entrées exportées")
    os.remove(json_path)

    # Test 7 : print_summary (ne doit pas planter)
    logger.print_summary()
    print("[OK] print_summary() sans erreur")

    # Test 8 : clear
    logger.clear()
    assert logger.count() == 0
    print("[OK] clear() vide le logger")

    # Test 9 : export vide → None
    result_vide = logger.export_csv()
    assert result_vide is None
    print("[OK] export_csv() sur logger vide retourne None")

    print("\n✅ Tous les tests O4_Score_Logger passés.")
