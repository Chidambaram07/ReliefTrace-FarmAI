"""Administrative boundary layers (FarmwiseAI Task-3 GeoJSON, WGS84). Missing files degrade to 'unavailable'.

Join key: the layer's `village_co` == the CSV's `village__1` (village code). The layer's `lgdvcode` disagrees with the
CSV's `Village LG` for two villages (CSV 642626 vs layer 642625; CSV 933538 vs layer 933537), so LGD is only a fallback.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import nearest_points, unary_union
from shapely.prepared import prep

from backend.utils.geo import haversine_m

log = logging.getLogger("reliefTrace.geo")
FOREST_CODE = "YYY"  # reserve-forest polygons carry no village code; excluded from village resolution


class AdminLayers:
    def __init__(self, geo_dir: Path | None):
        self.by_code: dict[str, dict] = {}
        self.code_by_layer_lgd: dict[str, str] = {}
        self.taluk = self.district = None
        self.taluk_name = self.district_name = None
        self.available = False
        self.error: str | None = None
        if geo_dir is None or not Path(geo_dir).is_dir():
            self.error = f"geo directory not found: {geo_dir}"
            return
        try:
            d = Path(geo_dir)
            parts: dict[str, list] = {}
            names: dict[str, str] = {}
            for f in json.loads((d / "Sivagiri_Villages.geojson").read_text(encoding="utf-8"))["features"]:
                p = f["properties"]
                code = str(p.get("village_co"))
                if code == FOREST_CODE:
                    continue
                parts.setdefault(code, []).append(shape(f["geometry"]))
                names[code] = p.get("vill_name")
                if p.get("lgdvcode"):
                    self.code_by_layer_lgd.setdefault(str(int(p["lgdvcode"])), code)
            for code, geoms in parts.items():
                g = unary_union(geoms)
                self.by_code[code] = {"code": code, "name": names[code], "geom": g, "prep": prep(g)}
            t = json.loads((d / "Taluk_boundary.geojson").read_text(encoding="utf-8"))["features"][0]
            self.taluk, self.taluk_name = shape(t["geometry"]), t["properties"].get("talukname")
            ds = json.loads((d / "Tenkasi_Boundary.geojson").read_text(encoding="utf-8"))["features"][0]
            self.district, self.district_name = shape(ds["geometry"]), ds["properties"].get("district_name")
            self.available = True
        except Exception as e:  # noqa: BLE001
            self.error = f"could not load boundary layers: {e}"
            log.warning(self.error)

    def village(self, code: str | None) -> dict | None:
        return self.by_code.get(str(code)) if code else None

    def resolve_code(self, lgd: str | None, lgd_map: dict | None) -> str | None:
        """CSV LGD -> village code, preferring the dataset's own mapping."""
        if not lgd:
            return None
        return (lgd_map or {}).get(str(lgd)) or self.code_by_layer_lgd.get(str(lgd))

    def locate(self, lat: float, lon: float) -> dict:
        p = Point(lon, lat)
        v = next((v for v in self.by_code.values() if v["prep"].contains(p)), None)
        return {"in_district": bool(self.district.contains(p)), "in_taluk": bool(self.taluk.contains(p)),
                "village_code": v["code"] if v else None, "village_name": v["name"] if v else None}

    def distance_to_village_m(self, lat: float, lon: float, code: str | None) -> float | None:
        v = self.village(code)
        if not v:
            return None
        p = Point(lon, lat)
        if v["prep"].contains(p):
            return 0.0
        q = nearest_points(p, v["geom"])[1]
        return round(haversine_m(lat, lon, q.y, q.x), 1)

    def centroid(self, code: str | None) -> tuple[float, float] | None:
        v = self.village(code)
        if not v:
            return None
        c = v["geom"].representative_point()
        return c.y, c.x
