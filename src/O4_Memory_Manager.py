"""
O4_Memory_Manager.py
Ortho4XP V3 — Lot A / Livrable A3
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)
Version : 1.0 — Mai 2026

Rôle :
    - Surveiller l'utilisation RAM en temps réel (via psutil)
    - Nettoyer automatiquement la mémoire quand le seuil est dépassé
    - Exposer check_and_cleanup_memory() à appeler dans les boucles lourdes
      (O4_DEM_Utils, O4_Imagery_Utils, O4_DSF_Utils, etc.)
    - Zéro cassure V2 : module autonome, rien n'est modifié dans les fichiers existants

Paramètres configurables :
    max_ram_percent   : seuil RAM système (défaut 80%)
    max_cache_size_gb : taille max du cache interne (défaut 8 Go)

Utilisation depuis un autre module :
    from O4_Memory_Manager import check_and_cleanup_memory, memory_stats
"""

import gc
import os
import time
import threading
from datetime import datetime

# ---------------------------------------------------------------------------
# Import psutil (requis pour la surveillance RAM)
# ---------------------------------------------------------------------------
try:
    import psutil
    _has_psutil = True
except ImportError:
    _has_psutil = False

# ---------------------------------------------------------------------------
# Import du système de logs Ortho4XP existant (O4_UI_Utils)
# Si indisponible (tests standalone), on bascule sur print simple
# ---------------------------------------------------------------------------
try:
    import O4_UI_Utils as UI
    def _log(msg):
        UI.lvprint(1, "[MEMORY] " + msg)
    def _logwarn(msg):
        UI.lvprint(1, "[MEMORY] ATTENTION : " + msg)
except ImportError:
    def _log(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [MEMORY] " + msg)
    def _logwarn(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S") + " [MEMORY] ATTENTION : " + msg)


# ---------------------------------------------------------------------------
# Configuration — modifiable sans toucher au reste du code
# ---------------------------------------------------------------------------

# Seuil d'utilisation RAM système (%) au-delà duquel on nettoie
max_ram_percent    = 80.0

# Taille maximale du cache interne en Go
max_cache_size_gb  = 8.0

# Intervalle minimum entre deux nettoyages forcés (secondes)
# Évite de spammer gc.collect() dans les boucles très rapides
_MIN_CLEANUP_INTERVAL = 5.0

# ---------------------------------------------------------------------------
# Cache interne géré par ce module
# Dictionnaire simple : clé → valeur (ex: tuiles, images en mémoire)
# Les modules externes peuvent enregistrer/lire des objets via l'API ci-dessous
# ---------------------------------------------------------------------------
_cache         = {}
_cache_lock    = threading.Lock()
_last_cleanup  = 0.0       # timestamp du dernier gc.collect()
_cleanup_count = 0         # nombre total de nettoyages effectués


# ---------------------------------------------------------------------------
# Fonctions internes
# ---------------------------------------------------------------------------

def _ram_usage_percent():
    """
    Retourne le pourcentage d'utilisation RAM système.
    Retourne 0.0 si psutil n'est pas disponible.
    """
    if not _has_psutil:
        return 0.0
    try:
        return psutil.virtual_memory().percent
    except Exception:
        return 0.0


def _ram_available_gb():
    """
    Retourne la RAM disponible en Go.
    Retourne 999.0 si psutil n'est pas disponible (mode dégradé sans blocage).
    """
    if not _has_psutil:
        return 999.0
    try:
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        return 999.0


def _cache_size_gb():
    """
    Estime la taille du cache interne en Go.
    Utilise sys.getsizeof sur chaque valeur — estimation, pas mesure exacte.
    """
    import sys
    total = 0
    with _cache_lock:
        for v in _cache.values():
            try:
                total += sys.getsizeof(v)
            except Exception:
                pass
    return total / (1024 ** 3)


def _do_cleanup(reason="seuil dépassé"):
    """
    Effectue le nettoyage mémoire :
    1. Vide le cache interne si sa taille dépasse max_cache_size_gb
    2. Appelle gc.collect() pour libérer les objets Python non référencés
    3. Log le résultat
    """
    global _last_cleanup, _cleanup_count

    now = time.time()

    # Respecter l'intervalle minimum entre deux nettoyages
    if now - _last_cleanup < _MIN_CLEANUP_INTERVAL:
        return

    ram_before = _ram_usage_percent()
    cache_gb   = _cache_size_gb()

    # Vider le cache interne si trop grand
    cleared_keys = 0
    if cache_gb > max_cache_size_gb:
        with _cache_lock:
            cleared_keys = len(_cache)
            _cache.clear()
        _logwarn(f"Cache interne vidé ({cache_gb:.2f} Go > {max_cache_size_gb} Go) "
                 f"— {cleared_keys} entrée(s) supprimée(s)")

    # Nettoyage Python
    collected = gc.collect()

    _last_cleanup  = time.time()
    _cleanup_count += 1

    ram_after = _ram_usage_percent()
    _log(f"Nettoyage #{_cleanup_count} [{reason}] — "
         f"RAM : {ram_before:.1f}% → {ram_after:.1f}% — "
         f"Objets GC collectés : {collected}")


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def check_and_cleanup_memory(context=""):
    """
    Fonction principale à appeler dans les boucles lourdes.

    Vérifie si les seuils RAM ou cache sont dépassés.
    Si oui, déclenche un nettoyage automatique.
    Si psutil est absent, effectue uniquement gc.collect() par précaution.

    Paramètres :
        context : texte libre affiché dans les logs pour identifier l'appelant
                  ex: "boucle DEM", "conversion tuile ZL17", etc.

    Exemple d'utilisation dans O4_DEM_Utils.py :
        from O4_Memory_Manager import check_and_cleanup_memory
        for lat in range(...):
            check_and_cleanup_memory(context="build_dem")
            # ... traitement lourd ...
    """
    if not _has_psutil:
        # Mode dégradé : gc.collect() simple, sans surveillance
        now = time.time()
        global _last_cleanup, _cleanup_count
        if now - _last_cleanup >= _MIN_CLEANUP_INTERVAL:
            gc.collect()
            _last_cleanup  = time.time()
            _cleanup_count += 1
        return

    ram_pct  = _ram_usage_percent()
    cache_gb = _cache_size_gb()

    needs_cleanup = (
        ram_pct  > max_ram_percent   or
        cache_gb > max_cache_size_gb
    )

    if needs_cleanup:
        reason = []
        if ram_pct  > max_ram_percent:
            reason.append(f"RAM {ram_pct:.1f}% > {max_ram_percent}%")
        if cache_gb > max_cache_size_gb:
            reason.append(f"cache {cache_gb:.2f} Go > {max_cache_size_gb} Go")
        label = " | ".join(reason)
        if context:
            label = f"{context} — {label}"
        _do_cleanup(reason=label)


def memory_stats():
    """
    Retourne un dictionnaire avec l'état courant de la mémoire.

    Retourne :
        dict avec les clés :
            ram_percent      : % RAM système utilisée
            ram_available_gb : Go RAM disponible
            cache_size_gb    : taille estimée du cache interne
            cache_entries    : nombre d'entrées dans le cache
            cleanup_count    : nombre de nettoyages effectués depuis le démarrage
            psutil_available : True si psutil est installé
    """
    with _cache_lock:
        n_entries = len(_cache)

    return {
        "ram_percent"      : _ram_usage_percent(),
        "ram_available_gb" : _ram_available_gb(),
        "cache_size_gb"    : _cache_size_gb(),
        "cache_entries"    : n_entries,
        "cleanup_count"    : _cleanup_count,
        "psutil_available" : _has_psutil,
    }


def cache_set(key, value):
    """
    Stocke une valeur dans le cache interne géré par ce module.

    Paramètres :
        key   : clé string unique (ex: "dem_48_2", "tile_ZL17_x123_y456")
        value : objet Python à mettre en cache

    Note : après chaque écriture, check_and_cleanup_memory() est appelé
           automatiquement pour éviter un dépassement silencieux.
    """
    with _cache_lock:
        _cache[key] = value
    check_and_cleanup_memory(context=f"cache_set:{key}")


def cache_get(key, default=None):
    """
    Récupère une valeur du cache interne.

    Paramètres :
        key     : clé à chercher
        default : valeur retournée si la clé est absente (défaut : None)

    Retourne :
        La valeur mise en cache, ou default si absente.
    """
    with _cache_lock:
        return _cache.get(key, default)


def cache_delete(key):
    """
    Supprime une entrée du cache interne.

    Paramètres :
        key : clé à supprimer

    Retourne :
        True si la clé existait, False sinon.
    """
    with _cache_lock:
        if key in _cache:
            del _cache[key]
            return True
    return False


def cache_clear():
    """
    Vide entièrement le cache interne et force un gc.collect().
    À utiliser après une opération lourde (ex: fin de génération d'une tuile).
    """
    global _cleanup_count
    with _cache_lock:
        n = len(_cache)
        _cache.clear()
    collected = gc.collect()
    _cleanup_count += 1
    _log(f"Cache vidé manuellement — {n} entrée(s) supprimée(s), "
         f"{collected} objets GC collectés")


def set_limits(ram_percent=None, cache_size_gb=None):
    """
    Modifie les seuils à chaud, sans redémarrage.

    Paramètres :
        ram_percent   : nouveau seuil RAM (ex: 75.0)
        cache_size_gb : nouvelle taille max cache (ex: 6.0)
    """
    global max_ram_percent, max_cache_size_gb
    if ram_percent is not None:
        if 10.0 <= ram_percent <= 95.0:
            max_ram_percent = float(ram_percent)
            _log(f"Seuil RAM mis à jour : {max_ram_percent}%")
        else:
            _logwarn(f"Seuil RAM invalide ({ram_percent}) — doit être entre 10 et 95")
    if cache_size_gb is not None:
        if 0.1 <= cache_size_gb <= 64.0:
            max_cache_size_gb = float(cache_size_gb)
            _log(f"Taille max cache mise à jour : {max_cache_size_gb} Go")
        else:
            _logwarn(f"Taille cache invalide ({cache_size_gb}) — doit être entre 0.1 et 64")


# ---------------------------------------------------------------------------
# Test standalone (python O4_Memory_Manager.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Test O4_Memory_Manager ===\n")

    # Test 1 : memory_stats
    stats = memory_stats()
    print(f"[OK] memory_stats() : {stats}")
    assert "ram_percent"      in stats
    assert "cache_entries"    in stats
    assert "cleanup_count"    in stats
    assert "psutil_available" in stats
    print(f"     psutil disponible : {stats['psutil_available']}")
    if stats["psutil_available"]:
        print(f"     RAM utilisée      : {stats['ram_percent']:.1f}%")
        print(f"     RAM disponible    : {stats['ram_available_gb']:.2f} Go")

    # Test 2 : cache_set / cache_get
    cache_set("test_key", [1, 2, 3, 4, 5])
    val = cache_get("test_key")
    assert val == [1, 2, 3, 4, 5], "ERREUR : cache_get ne retrouve pas la valeur"
    print("[OK] cache_set / cache_get")

    # Test 3 : cache_delete
    ok = cache_delete("test_key")
    assert ok, "ERREUR : cache_delete a retourné False"
    assert cache_get("test_key") is None
    print("[OK] cache_delete")

    # Test 4 : check_and_cleanup_memory (ne doit pas planter)
    check_and_cleanup_memory(context="test unitaire")
    print("[OK] check_and_cleanup_memory")

    # Test 5 : set_limits
    set_limits(ram_percent=75.0, cache_size_gb=6.0)
    assert max_ram_percent   == 75.0
    assert max_cache_size_gb == 6.0
    print("[OK] set_limits")

    # Test 6 : cache_clear
    cache_set("a", "valeur_a")
    cache_set("b", "valeur_b")
    cache_clear()
    assert cache_get("a") is None
    assert cache_get("b") is None
    print("[OK] cache_clear")

    # Test 7 : set_limits avec valeurs invalides (ne doit pas planter)
    set_limits(ram_percent=5.0)    # trop bas → ignoré
    set_limits(cache_size_gb=100)  # trop haut → ignoré
    print("[OK] set_limits valeurs invalides correctement ignorées")

    print("\n✅ Tous les tests O4_Memory_Manager passés.")
