"""
O4_Benchmark.py
Ortho4XP V3 — Phase 3 / Points 3+4
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)
Version : 1.0 — Mai 2026

Rôle :
    - Benchmark CPU vs GPU pour les opérations lourdes
    - Debug visualizations : seam risk, blur, color transfer
    - Timeline simple des étapes du build
    - Zéro cassure V2 : module autonome

Utilisation :
    from O4_Benchmark import Benchmark, Timeline, DebugViz
    bench = Benchmark()
    bench.run()
    tl = Timeline()
    tl.start("Step 1")
    tl.end("Step 1")
    tl.report()
"""

import os
import time
import json
import threading
import numpy
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Import système de logs Ortho4XP
# ---------------------------------------------------------------------------
try:
    import O4_UI_Utils as UI
    def _log(msg):  UI.lvprint(1, "[BENCH] " + msg)
    def _warn(msg): UI.lvprint(1, "[BENCH] ATTENTION : " + msg)
except ImportError:
    def _log(msg):  print(time.strftime("%Y-%m-%d %H:%M:%S") + " [BENCH] " + msg)
    def _warn(msg): print(time.strftime("%Y-%m-%d %H:%M:%S") + " [BENCH] ATTENTION : " + msg)

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_BENCH_FILE  = os.path.join(_SCRIPT_DIR, "_bench_results.json")
_DEBUG_DIR   = os.path.join(_SCRIPT_DIR, "_debug_viz")


# ===========================================================================
# TIMELINE — suivi des étapes du build
# ===========================================================================
class Timeline:
    """
    Suivi chronologique des étapes du build.

    Utilisation :
        tl = Timeline()
        tl.start("Step 1 — Vectors")
        # ... travail ...
        tl.end("Step 1 — Vectors")
        tl.report()
    """

    def __init__(self):
        self._lock   = threading.Lock()
        self._steps  = {}   # {nom: {start, end, duration}}
        self._order  = []   # ordre des étapes

    def start(self, name: str):
        with self._lock:
            self._steps[name] = {"start": time.time(), "end": None,
                                  "duration": None}
            if name not in self._order:
                self._order.append(name)

    def end(self, name: str):
        t = time.time()
        with self._lock:
            if name in self._steps:
                self._steps[name]["end"]      = t
                self._steps[name]["duration"] = t - self._steps[name]["start"]
            else:
                _warn(f"Timeline.end() : étape inconnue '{name}'")

    def duration(self, name: str) -> float:
        """Retourne la durée en secondes d'une étape (0 si inconnue)."""
        with self._lock:
            s = self._steps.get(name, {})
            return s.get("duration") or 0.0

    def report(self) -> str:
        """Retourne un rapport lisible de toutes les étapes."""
        lines = [
            f"\n{'='*60}",
            f"  TIMELINE BUILD — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'='*60}",
            f"  {'Étape':<35} {'Durée':>10}",
            f"  {'-'*48}",
        ]
        total = 0.0
        with self._lock:
            for name in self._order:
                s = self._steps[name]
                dur = s.get("duration")
                if dur is not None:
                    total += dur
                    m, sec = divmod(int(dur), 60)
                    lines.append(f"  {name:<35} {m:>3}m{sec:02d}s")
                else:
                    lines.append(f"  {name:<35} {'en cours':>10}")
        m_t, s_t = divmod(int(total), 60)
        lines.append(f"  {'-'*48}")
        lines.append(f"  {'TOTAL':<35} {m_t:>3}m{s_t:02d}s")
        lines.append(f"{'='*60}\n")
        msg = "\n".join(lines)
        return msg  # Affichage uniquement dans la fenêtre Timeline — pas dans le log

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "timestamp": datetime.now().isoformat(),
                "steps": {
                    k: {
                        "duration_sec": round(v.get("duration") or 0, 2),
                        "start_iso"   : datetime.fromtimestamp(
                            v["start"]).isoformat() if v.get("start") else None,
                    }
                    for k, v in self._steps.items()
                }
            }


# ===========================================================================
# BENCHMARK — CPU vs GPU
# ===========================================================================
class Benchmark:
    """
    Benchmark des opérations lourdes Ortho4XP : histogramme, color transfer,
    DeltaE, feathering. Compare CPU vs GPU si disponible.
    """

    def __init__(self):
        self._results = {}
        self._gpu_available = self._check_gpu()

    def _check_gpu(self) -> bool:
        """Détecte GPU CUDA via cupy ou torch."""
        try:
            import cupy
            _log("GPU détecté (CuPy)")
            return True
        except ImportError:
            pass
        try:
            import torch
            if torch.cuda.is_available():
                _log("GPU détecté (PyTorch CUDA)")
                return True
        except ImportError:
            pass
        _log("GPU non disponible — mode CPU uniquement")
        return False

    def _bench_histogram(self, size: int = 2048) -> dict:
        """Benchmark calcul histogramme RGB."""
        arr = numpy.random.randint(0, 256, (size, size, 3), dtype='uint8')
        # CPU
        t0 = time.perf_counter()
        for c in range(3):
            numpy.histogram(arr[:,:,c], bins=256, range=(0, 256))
        cpu_ms = (time.perf_counter() - t0) * 1000

        result = {"cpu_ms": round(cpu_ms, 2)}

        # GPU si disponible
        if self._gpu_available:
            try:
                import cupy as cp
                arr_gpu = cp.array(arr)
                t1 = time.perf_counter()
                for c in range(3):
                    cp.histogram(arr_gpu[:,:,c], bins=256, range=(0, 256))
                cp.cuda.Stream.null.synchronize()
                result["gpu_ms"] = round((time.perf_counter() - t1) * 1000, 2)
                result["speedup"] = round(cpu_ms / result["gpu_ms"], 1)
            except Exception as e:
                result["gpu_error"] = str(e)

        return result

    def _bench_color_transfer(self, size: int = 1024) -> dict:
        """Benchmark color transfer (normalisation LAB)."""
        arr = numpy.random.randint(50, 200, (size, size, 3), dtype='uint8')
        img = Image.fromarray(arr, 'RGB')

        t0 = time.perf_counter()
        # Simulation color transfer : calcul moyennes/écarts par canal
        arr_f = arr.astype(numpy.float32)
        for c in range(3):
            mean = arr_f[:,:,c].mean()
            std  = arr_f[:,:,c].std()
            if std > 0:
                arr_f[:,:,c] = (arr_f[:,:,c] - mean) / std * 50 + 128
        numpy.clip(arr_f, 0, 255, out=arr_f)
        cpu_ms = (time.perf_counter() - t0) * 1000

        return {"cpu_ms": round(cpu_ms, 2)}

    def _bench_feathering(self, size: int = 512) -> dict:
        """Benchmark feathering (convolution gaussienne)."""
        from PIL import ImageFilter
        arr = numpy.random.randint(0, 256, (size, size, 3), dtype='uint8')
        img = Image.fromarray(arr, 'RGB')

        t0 = time.perf_counter()
        img.filter(ImageFilter.GaussianBlur(radius=3))
        cpu_ms = (time.perf_counter() - t0) * 1000

        return {"cpu_ms": round(cpu_ms, 2)}

    def run(self, verbose: bool = True) -> dict:
        """
        Exécute tous les benchmarks et retourne les résultats.

        Paramètres :
            verbose : si True, affiche le rapport dans les logs

        Retourne :
            dict avec les résultats par opération
        """
        _log("Démarrage benchmark...")

        tests = [
            ("Histogramme 2048x2048", self._bench_histogram),
            ("Color Transfer 1024x1024", self._bench_color_transfer),
            ("Feathering 512x512", self._bench_feathering),
        ]

        results = {
            "timestamp"     : datetime.now().isoformat(),
            "gpu_available" : self._gpu_available,
            "tests"         : {},
        }

        for name, fn in tests:
            try:
                r = fn()
                results["tests"][name] = r
                if verbose:
                    cpu = r.get("cpu_ms", "?")
                    gpu = r.get("gpu_ms")
                    spd = r.get("speedup")
                    if gpu:
                        _log(f"  {name} : CPU={cpu}ms  GPU={gpu}ms  "
                             f"accélération x{spd}")
                    else:
                        _log(f"  {name} : CPU={cpu}ms  (GPU non dispo)")
            except Exception as e:
                results["tests"][name] = {"error": str(e)}
                _warn(f"  {name} : erreur — {e}")

        self._results = results
        self._save(results)

        if verbose:
            self._print_summary(results)

        return results

    def _print_summary(self, results: dict):
        lines = [
            f"\n{'='*60}",
            f"  BENCHMARK — {results['timestamp'][:19]}",
            f"  GPU disponible : {'Oui' if results['gpu_available'] else 'Non'}",
            f"{'='*60}",
        ]
        for name, r in results["tests"].items():
            if "error" in r:
                lines.append(f"  {name} : ❌ {r['error']}")
            elif "speedup" in r:
                lines.append(f"  {name} :"
                             f" CPU={r['cpu_ms']}ms "
                             f"GPU={r.get('gpu_ms','?')}ms "
                             f"→ x{r['speedup']}")
            else:
                lines.append(f"  {name} : CPU={r['cpu_ms']}ms")
        lines.append(f"{'='*60}\n")
        try:
            import O4_UI_Utils as _UI
            _UI.vprint(1, "\n".join(lines))
        except Exception:
            print("\n".join(lines))

    def _save(self, results: dict):
        try:
            with open(_BENCH_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
        except Exception as e:
            _warn(f"Impossible de sauvegarder les résultats : {e}")


# ===========================================================================
# DEBUG VISUALIZATIONS
# ===========================================================================
class DebugViz:
    """
    Génère des images de debug pour analyser seam risk, blur, color transfer.
    Les images sont sauvegardées dans _debug_viz/.
    Non bloquant : toute erreur est loggée sans planter le build.
    """

    def __init__(self):
        os.makedirs(_DEBUG_DIR, exist_ok=True)

    def seam_risk_map(self, image: Image.Image,
                      tile_id: str, seam_score: float) -> str | None:
        """
        Génère une image de visualisation du risque de jointure.
        Superpose les zones à risque en rouge sur l'image originale.

        Paramètres :
            image      : image PIL originale
            tile_id    : identifiant tuile (pour le nom de fichier)
            seam_score : score seam risk [0-100]

        Retourne :
            Chemin de l'image générée, ou None en cas d'erreur.
        """
        try:
            thumb  = image.convert("RGB").resize((256, 256), Image.BICUBIC)
            arr    = numpy.array(thumb, dtype=numpy.float32)
            h, w   = arr.shape[:2]
            margin = max(4, h // 16)

            # Créer overlay rouge sur les zones de bord à risque
            overlay = numpy.zeros((h, w, 4), dtype=numpy.uint8)

            # Calculer drift par zone de bordure
            center_mean = arr[h//4:3*h//4, w//4:3*w//4, :].mean(axis=(0,1))
            zones = [
                (slice(0, margin), slice(None)),           # haut
                (slice(h-margin, h), slice(None)),         # bas
                (slice(None), slice(0, margin)),           # gauche
                (slice(None), slice(w-margin, w)),         # droite
            ]
            for sy, sx in zones:
                zone_mean = arr[sy, sx, :].mean(axis=(0,1))
                drift = float(numpy.abs(zone_mean - center_mean).mean())
                # Plus le drift est fort, plus le rouge est intense
                intensity = min(255, int(drift * 3))
                overlay[sy, sx, 0] = intensity   # Rouge
                overlay[sy, sx, 3] = min(180, intensity)  # Alpha

            # Composer
            base   = thumb.convert("RGBA")
            ov_img = Image.fromarray(overlay, "RGBA")
            result = Image.alpha_composite(base, ov_img).convert("RGB")

            # Ajouter texte score
            draw = ImageDraw.Draw(result)
            color = (255, 80, 80) if seam_score < 70 else (80, 255, 80)
            draw.rectangle([0, 0, 256, 18], fill=(0, 0, 0))
            draw.text((4, 2),
                      f"Seam risk : {100-seam_score:.0f}%  "
                      f"Score : {seam_score:.0f}/100",
                      fill=color)

            out = os.path.join(_DEBUG_DIR,
                               f"seam_{tile_id.replace('/', '_')}.png")
            result.save(out)
            return out

        except Exception as e:
            _warn(f"seam_risk_map() erreur : {e}")
            return None

    def color_transfer_compare(self, before: Image.Image,
                               after: Image.Image,
                               tile_id: str) -> str | None:
        """
        Génère une image côte-à-côte avant/après color transfer.

        Paramètres :
            before  : image avant correction
            after   : image après correction
            tile_id : identifiant tuile

        Retourne :
            Chemin de l'image générée, ou None en cas d'erreur.
        """
        try:
            size   = (256, 256)
            b_img  = before.convert("RGB").resize(size, Image.BICUBIC)
            a_img  = after.convert("RGB").resize(size, Image.BICUBIC)

            result = Image.new("RGB", (512, 256 + 20), (0, 0, 0))
            result.paste(b_img, (0, 20))
            result.paste(a_img, (256, 20))

            draw = ImageDraw.Draw(result)
            draw.text((4,   4), "AVANT", fill=(200, 200, 200))
            draw.text((260, 4), "APRÈS", fill=(200, 200, 200))

            out = os.path.join(_DEBUG_DIR,
                               f"colortransfer_{tile_id.replace('/','_')}.png")
            result.save(out)
            return out

        except Exception as e:
            _warn(f"color_transfer_compare() erreur : {e}")
            return None

    def blur_map(self, image: Image.Image, tile_id: str) -> str | None:
        """
        Génère une carte de netteté (blur map) de l'image.
        Les zones floues apparaissent en bleu, les zones nettes en vert.

        Paramètres :
            image   : image PIL
            tile_id : identifiant tuile

        Retourne :
            Chemin de l'image générée, ou None en cas d'erreur.
        """
        try:
            from PIL import ImageFilter
            thumb = image.convert("L").resize((256, 256), Image.BICUBIC)
            arr   = numpy.array(thumb, dtype=numpy.float32)

            # Netteté locale = différence image originale vs image floutée
            from PIL import ImageFilter
            blurred = thumb.filter(ImageFilter.GaussianBlur(radius=1))
            lap     = numpy.abs(
                arr - numpy.array(blurred, dtype=numpy.float32)
            )
            # Normaliser [0-255]
            lap_n = numpy.clip(lap / (lap.max() + 1e-5) * 255, 0, 255).astype('uint8')

            # Coloriser : flou = bleu, net = vert
            colored = numpy.zeros((256, 256, 3), dtype='uint8')
            colored[:,:,1] = lap_n           # vert = net
            colored[:,:,2] = 255 - lap_n     # bleu = flou

            result = Image.fromarray(colored, "RGB")
            draw   = ImageDraw.Draw(result)
            draw.rectangle([0, 0, 256, 14], fill=(0,0,0))
            draw.text((4, 2), f"Blur map — {tile_id}", fill=(200,200,200))

            out = os.path.join(_DEBUG_DIR,
                               f"blur_{tile_id.replace('/','_')}.png")
            result.save(out)
            return out

        except Exception as e:
            _warn(f"blur_map() erreur : {e}")
            return None


# ---------------------------------------------------------------------------
# Instance globale partagée
# ---------------------------------------------------------------------------
default_timeline = Timeline()


# ---------------------------------------------------------------------------
# Test standalone
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Test O4_Benchmark ===\n")

    # Test Timeline
    tl = Timeline()
    tl.start("Step 1 — Vectors")
    time.sleep(0.05)
    tl.end("Step 1 — Vectors")
    tl.start("Step 2 — Mesh")
    time.sleep(0.03)
    tl.end("Step 2 — Mesh")
    assert tl.duration("Step 1 — Vectors") > 0
    tl.report()
    print("[OK] Timeline")

    # Test Benchmark
    bench = Benchmark()
    results = bench.run(verbose=True)
    assert "tests" in results
    assert "Histogramme 2048x2048" in results["tests"]
    print("[OK] Benchmark CPU")

    # Test DebugViz
    dbg = DebugViz()
    arr = numpy.random.randint(80, 180, (64,64,3), dtype='uint8')
    arr[:4,:,:] = 220  # bord clair
    img = Image.fromarray(arr, 'RGB')

    p1 = dbg.seam_risk_map(img, "test_seam_46224_64784_ZL17", 65.0)
    assert p1 and os.path.isfile(p1)
    print(f"[OK] seam_risk_map : {os.path.basename(p1)}")

    p2 = dbg.color_transfer_compare(img, img, "test_ct_46224")
    assert p2 and os.path.isfile(p2)
    print(f"[OK] color_transfer_compare : {os.path.basename(p2)}")

    p3 = dbg.blur_map(img, "test_blur_46224")
    assert p3 and os.path.isfile(p3)
    print(f"[OK] blur_map : {os.path.basename(p3)}")

    print("\n✅ Tous les tests O4_Benchmark passés.")
