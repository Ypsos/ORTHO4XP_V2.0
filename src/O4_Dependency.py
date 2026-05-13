# src/O4_Dependency.py
import json
import hashlib
from pathlib import Path

class TileDependency:
    def __init__(self, lat=0, lon=0, zoomlevel=17):
        self.lat = float(lat)
        self.lon = float(lon)
        self.zoomlevel = int(zoomlevel)
        self.tile_id = f"{self.lat:.2f}_{self.lon:.2f}_ZL{self.zoomlevel}"
        self.base_dir = Path(f"Ortho/{self.tile_id}")
        self.meta_file = self.base_dir / "tile_meta.json"

    def compute_hash(self, data):
        return hashlib.sha256(str(data).encode()).hexdigest()[:16]

    def get_meta(self):
        if self.meta_file.exists():
            try:
                return json.loads(self.meta_file.read_text(encoding="utf-8"))
            except:
                return {}
        return {}

    def needs_rebuild(self, inputs):
        old = self.get_meta()
        current_hash = self.compute_hash(inputs)
        if old.get("input_hash") != current_hash:
            return True
        return False

    def save_meta(self, inputs):
        """
        Sauvegarde le hash des inputs après un build réussi.
        À appeler en fin de build_tile() uniquement si succès.
        Sans cette méthode, needs_rebuild() retourne toujours True
        et le cache ne sert à rien.
        """
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "tile_id":    self.tile_id,
                "input_hash": self.compute_hash(inputs),
                "lat":        self.lat,
                "lon":        self.lon,
                "zoomlevel":  self.zoomlevel,
            }
            self.meta_file.write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"[Dependency] Impossible de sauvegarder le cache : {e}")
