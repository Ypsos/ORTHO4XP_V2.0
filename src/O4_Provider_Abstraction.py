"""
O4_Provider_Abstraction.py
Ortho4XP V3 — Lot B / Livrable B1
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)
Version : 1.0 — Mai 2026

Rôle :
    - Couche d'abstraction minimale entre le pipeline et les providers
    - Failover automatique et sûr : si un provider échoue, on passe au suivant
    - Blacklist temporaire des providers défaillants (reset automatique)
    - Zéro cassure V2 : module autonome, rien n'est modifié dans les fichiers existants
    - S'appuie sur providers_dict existant de O4_Imagery_Utils (pas de duplication)

Utilisation depuis un autre module :
    from O4_Provider_Abstraction import ProviderAbstraction
    pa = ProviderAbstraction(providers_list=["FR_IGN", "OSM", "Bing"])
    best = pa.get_active_provider()
    pa.report_failure("FR_IGN", reason="HTTP 503")
    pa.report_success("OSM")
"""

import time
import threading
import json
import os
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Import système de logs Ortho4XP (O4_UI_Utils)
# Fallback print si indisponible
# ---------------------------------------------------------------------------
try:
    import O4_UI_Utils as UI
    def _log(msg):
        UI.lvprint(1, "[PROVIDER] " + msg)
    def _logwarn(msg):
        UI.lvprint(1, "[PROVIDER] ATTENTION : " + msg)
except ImportError:
    def _log(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [PROVIDER] " + msg)
    def _logwarn(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [PROVIDER] ATTENTION : " + msg)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Durée de blacklist d'un provider défaillant (secondes) — 5 minutes par défaut
BLACKLIST_DURATION_SEC = 300

# Nombre max d'échecs consécutifs avant blacklist
MAX_FAILURES_BEFORE_BLACKLIST = 3

# Fichier de persistance des stats failover (optionnel)
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_FAILOVER_LOG = os.path.join(_SCRIPT_DIR, "_failover_log.json")


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class ProviderAbstraction:
    """
    Couche d'abstraction minimale pour la gestion des providers.

    Gère :
        - Liste ordonnée de providers (priorité = ordre de la liste)
        - Failover automatique si un provider est blacklisté
        - Blacklist temporaire avec reset automatique après BLACKLIST_DURATION_SEC
        - Stats d'échecs / succès par provider
        - Thread-safe

    Utilisation typique dans O4_Imagery_Utils :
        pa = ProviderAbstraction(["FR_IGN", "OSM", "Bing"])
        provider = pa.get_active_provider()
        try:
            # ... téléchargement ...
            pa.report_success(provider)
        except Exception as e:
            pa.report_failure(provider, reason=str(e))
            provider = pa.get_active_provider()  # failover automatique
    """

    def __init__(self, providers_list=None):
        """
        Paramètres :
            providers_list : liste ordonnée de codes provider
                             ex: ["FR_IGN", "OSM", "Bing"]
                             None = liste vide (à remplir via add_provider)
        """
        self._lock        = threading.Lock()
        self._providers   = list(providers_list) if providers_list else []

        # Stats par provider : {code: {failures, successes, last_failure, blacklisted_until}}
        self._stats       = {}
        self._init_stats()

    # ------------------------------------------------------------------
    # Initialisation interne
    # ------------------------------------------------------------------

    def _init_stats(self):
        """Initialise les stats pour tous les providers de la liste."""
        for code in self._providers:
            if code not in self._stats:
                self._stats[code] = {
                    "failures"         : 0,
                    "successes"        : 0,
                    "consecutive_fails": 0,
                    "last_failure"     : None,
                    "last_success"     : None,
                    "blacklisted_until": 0.0,
                    "last_reason"      : "",
                }

    # ------------------------------------------------------------------
    # Gestion de la liste de providers
    # ------------------------------------------------------------------

    def add_provider(self, code):
        """
        Ajoute un provider en fin de liste (priorité la plus basse).

        Paramètres :
            code : code provider (ex: "FR_IGN")
        """
        with self._lock:
            if code not in self._providers:
                self._providers.append(code)
                self._stats[code] = {
                    "failures"         : 0,
                    "successes"        : 0,
                    "consecutive_fails": 0,
                    "last_failure"     : None,
                    "last_success"     : None,
                    "blacklisted_until": 0.0,
                    "last_reason"      : "",
                }
                _log(f"Provider ajouté : {code}")

    def remove_provider(self, code):
        """
        Retire un provider de la liste.

        Paramètres :
            code : code provider à retirer
        """
        with self._lock:
            if code in self._providers:
                self._providers.remove(code)
                _log(f"Provider retiré : {code}")

    def set_providers(self, providers_list):
        """
        Remplace toute la liste de providers.
        Conserve les stats existantes pour les providers déjà connus.

        Paramètres :
            providers_list : nouvelle liste ordonnée
        """
        with self._lock:
            self._providers = list(providers_list)
            self._init_stats()
            _log(f"Liste providers mise à jour : {self._providers}")

    # ------------------------------------------------------------------
    # Blacklist
    # ------------------------------------------------------------------

    def _is_blacklisted(self, code):
        """
        Vérifie si un provider est blacklisté.
        Libère automatiquement si la durée est expirée.
        Doit être appelé sous lock.
        """
        stats = self._stats.get(code, {})
        until = stats.get("blacklisted_until", 0.0)
        if until == 0.0:
            return False
        if time.time() >= until:
            # Durée expirée → on libère
            stats["blacklisted_until"]  = 0.0
            stats["consecutive_fails"]  = 0
            _log(f"Provider {code} sorti de blacklist automatiquement")
            return False
        return True

    def blacklist(self, code, reason="manuel"):
        """
        Blackliste manuellement un provider pour BLACKLIST_DURATION_SEC secondes.

        Paramètres :
            code   : code provider
            reason : motif affiché dans les logs
        """
        with self._lock:
            if code not in self._stats:
                return
            until = time.time() + BLACKLIST_DURATION_SEC
            self._stats[code]["blacklisted_until"] = until
            self._stats[code]["last_reason"]       = reason
            expiry = datetime.fromtimestamp(until).strftime("%H:%M:%S")
            _logwarn(f"Provider {code} blacklisté jusqu'à {expiry} [{reason}]")

    def unblacklist(self, code):
        """
        Retire manuellement un provider de la blacklist.

        Paramètres :
            code : code provider à libérer
        """
        with self._lock:
            if code in self._stats:
                self._stats[code]["blacklisted_until"] = 0.0
                self._stats[code]["consecutive_fails"] = 0
                _log(f"Provider {code} retiré manuellement de la blacklist")

    # ------------------------------------------------------------------
    # Rapport de succès / échec (appelé par le pipeline)
    # ------------------------------------------------------------------

    def report_success(self, code):
        """
        À appeler après un téléchargement réussi.
        Remet le compteur d'échecs consécutifs à zéro.

        Paramètres :
            code : code provider ayant réussi
        """
        with self._lock:
            if code not in self._stats:
                return
            self._stats[code]["successes"]          += 1
            self._stats[code]["consecutive_fails"]   = 0
            self._stats[code]["last_success"]        = time.time()

    def report_failure(self, code, reason="inconnu"):
        """
        À appeler après un échec de téléchargement.
        Blackliste automatiquement si MAX_FAILURES_BEFORE_BLACKLIST atteint.

        Paramètres :
            code   : code provider ayant échoué
            reason : motif de l'échec (ex: "HTTP 503", "timeout")
        """
        with self._lock:
            if code not in self._stats:
                return
            self._stats[code]["failures"]           += 1
            self._stats[code]["consecutive_fails"]  += 1
            self._stats[code]["last_failure"]        = time.time()
            self._stats[code]["last_reason"]         = reason

            consec = self._stats[code]["consecutive_fails"]
            _logwarn(f"Provider {code} — échec #{consec} [{reason}]")

            if consec >= MAX_FAILURES_BEFORE_BLACKLIST:
                until  = time.time() + BLACKLIST_DURATION_SEC
                self._stats[code]["blacklisted_until"] = until
                expiry = datetime.fromtimestamp(until).strftime("%H:%M:%S")
                _logwarn(f"Provider {code} blacklisté automatiquement "
                         f"({consec} échecs consécutifs) jusqu'à {expiry}")

    # ------------------------------------------------------------------
    # Sélection du provider actif (cœur du failover)
    # ------------------------------------------------------------------

    def get_active_provider(self):
        """
        Retourne le premier provider non-blacklisté dans la liste (ordre priorité).

        Retourne :
            code du provider actif, ou None si tous blacklistés.

        Comportement failover :
            - Parcourt la liste dans l'ordre de priorité
            - Saute les providers blacklistés
            - Vérifie automatiquement si une blacklist est expirée
            - Si tous blacklistés → retourne None + log d'avertissement
        """
        with self._lock:
            for code in self._providers:
                if not self._is_blacklisted(code):
                    return code
            _logwarn("Tous les providers sont blacklistés ! "
                     "Vérifiez votre connexion réseau.")
            return None

    def get_all_active(self):
        """
        Retourne la liste de tous les providers non-blacklistés.

        Retourne :
            Liste ordonnée de codes providers actifs.
        """
        with self._lock:
            return [c for c in self._providers if not self._is_blacklisted(c)]

    # ------------------------------------------------------------------
    # Stats et rapport
    # ------------------------------------------------------------------

    def get_stats(self, code=None):
        """
        Retourne les statistiques d'un provider ou de tous.

        Paramètres :
            code : code provider, ou None pour tous

        Retourne :
            dict stats du provider, ou dict {code: stats} pour tous
        """
        with self._lock:
            if code:
                return dict(self._stats.get(code, {}))
            return {c: dict(s) for c, s in self._stats.items()}

    def report_text(self):
        """
        Retourne un rapport lisible de l'état des providers.

        Retourne :
            str — tableau formaté
        """
        now = time.time()
        lines = [
            f"\n{'='*65}",
            f"  ÉTAT DES PROVIDERS — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'='*65}",
            f"  {'Provider':<20} {'Succès':>7} {'Échecs':>7} {'Consec':>7}  État",
            f"  {'-'*55}",
        ]
        with self._lock:
            for code in self._providers:
                s     = self._stats.get(code, {})
                succ  = s.get("successes", 0)
                fail  = s.get("failures",  0)
                consec= s.get("consecutive_fails", 0)
                until = s.get("blacklisted_until", 0.0)

                if until > now:
                    remaining = int(until - now)
                    etat = f"🔴 Blacklisté ({remaining}s restantes)"
                elif self._is_blacklisted(code):
                    etat = "🔴 Blacklisté"
                else:
                    etat = "✅ Actif"

                lines.append(f"  {code:<20} {succ:>7} {fail:>7} {consec:>7}  {etat}")

        lines.append(f"{'='*65}\n")
        return "\n".join(lines)

    def save_log(self):
        """
        Sauvegarde les stats courantes dans _failover_log.json.
        Utile pour audit ou diagnostic post-build.
        """
        try:
            data = {
                "timestamp"  : datetime.now().isoformat(),
                "providers"  : self._providers,
                "stats"      : {
                    c: {k: v for k, v in s.items() if k != "blacklisted_until"}
                    for c, s in self._stats.items()
                },
            }
            with open(_FAILOVER_LOG, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            _log(f"Stats failover sauvegardées : {_FAILOVER_LOG}")
        except Exception as e:
            _logwarn(f"Impossible de sauvegarder le log failover : {e}")

    def reset_all(self):
        """
        Remet tous les compteurs à zéro et retire toutes les blacklists.
        À utiliser en début de session ou après un problème réseau résolu.
        """
        with self._lock:
            for code in self._stats:
                self._stats[code] = {
                    "failures"         : 0,
                    "successes"        : 0,
                    "consecutive_fails": 0,
                    "last_failure"     : None,
                    "last_success"     : None,
                    "blacklisted_until": 0.0,
                    "last_reason"      : "",
                }
            _log("Tous les compteurs providers remis à zéro")


# ---------------------------------------------------------------------------
# Instance globale partagée (optionnelle — compatible avec usage local aussi)
# ---------------------------------------------------------------------------
default_abstraction = ProviderAbstraction()


# ---------------------------------------------------------------------------
# Test standalone (python O4_Provider_Abstraction.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Test O4_Provider_Abstraction ===\n")

    pa = ProviderAbstraction(["FR_IGN", "OSM", "Bing"])

    # Test 1 : provider actif = premier de la liste
    active = pa.get_active_provider()
    assert active == "FR_IGN", f"ERREUR : attendu FR_IGN, obtenu {active}"
    print(f"[OK] get_active_provider() = {active}")

    # Test 2 : échecs → blacklist automatique
    for i in range(MAX_FAILURES_BEFORE_BLACKLIST):
        pa.report_failure("FR_IGN", reason=f"HTTP 503 test {i+1}")
    active2 = pa.get_active_provider()
    assert active2 == "OSM", f"ERREUR : failover attendu OSM, obtenu {active2}"
    print(f"[OK] Failover après {MAX_FAILURES_BEFORE_BLACKLIST} échecs → {active2}")

    # Test 3 : succès sur OSM
    pa.report_success("OSM")
    stats = pa.get_stats("OSM")
    assert stats["successes"] == 1
    print("[OK] report_success() comptabilisé")

    # Test 4 : unblacklist manuel
    pa.unblacklist("FR_IGN")
    active3 = pa.get_active_provider()
    assert active3 == "FR_IGN", f"ERREUR : attendu FR_IGN après unblacklist"
    print("[OK] unblacklist() + get_active_provider() restauré")

    # Test 5 : get_all_active
    pa.blacklist("Bing", reason="test blacklist manuel")
    actives = pa.get_all_active()
    assert "Bing" not in actives
    assert "FR_IGN" in actives
    print(f"[OK] get_all_active() = {actives}")

    # Test 6 : report_text
    txt = pa.report_text()
    assert "FR_IGN" in txt and "OSM" in txt
    print("[OK] report_text() généré")

    # Test 7 : reset_all
    pa.reset_all()
    active4 = pa.get_active_provider()
    assert active4 == "FR_IGN"
    stats_reset = pa.get_stats("Bing")
    assert stats_reset["failures"] == 0
    print("[OK] reset_all() remet tout à zéro")

    # Test 8 : tous providers blacklistés → None
    for code in ["FR_IGN", "OSM", "Bing"]:
        for _ in range(MAX_FAILURES_BEFORE_BLACKLIST):
            pa.report_failure(code, reason="test tous blacklistés")
    result = pa.get_active_provider()
    assert result is None, f"ERREUR : attendu None, obtenu {result}"
    print("[OK] Tous blacklistés → get_active_provider() retourne None")

    print("\n✅ Tous les tests O4_Provider_Abstraction passés.")
