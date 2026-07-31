#!/usr/bin/env python3
"""Build a static HTML review map with embedded GeoJSON layers."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QGIS_REVIEW_DIR = PROJECT_ROOT / "data/qgis-review"
WEBMAP_DIR = PROJECT_ROOT / "webmap"
OUT_PATH = WEBMAP_DIR / "index.html"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    layers = {
        "review_points": load_json(QGIS_REVIEW_DIR / "review_points.geojson"),
        "positive_seed_buffers_120m": load_json(QGIS_REVIEW_DIR / "positive_seed_buffers_120m.geojson"),
        "tile_windows_512m": load_json(QGIS_REVIEW_DIR / "tile_windows_512m.geojson"),
        "pba_geocoding_candidates": load_json(QGIS_REVIEW_DIR / "pba_geocoding_candidates.geojson"),
        "hard_negative_candidates": load_json(QGIS_REVIEW_DIR / "hard_negative_candidates.geojson"),
        "trasancos_aoi": load_json(QGIS_REVIEW_DIR / "trasancos_aoi.geojson"),
    }
    WEBMAP_DIR.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(layers, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Castros IA Galicia - revisión</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    html, body {{ height: 100%; margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ display: grid; grid-template-columns: 340px 1fr; background: #f4f5f3; color: #202421; }}
    aside {{ border-right: 1px solid #cfd5cf; padding: 16px; overflow: auto; background: #fbfcfa; }}
    h1 {{ font-size: 20px; margin: 0 0 8px; }}
    h2 {{ font-size: 14px; margin: 18px 0 8px; }}
    p, label, li {{ font-size: 13px; line-height: 1.35; }}
    .metric {{ display: grid; grid-template-columns: 1fr auto; gap: 8px; border-bottom: 1px solid #e2e6e2; padding: 6px 0; }}
    .legend {{ display: grid; gap: 6px; }}
    .swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; border: 1px solid #333; }}
    .line {{ border-radius: 0; height: 8px; }}
    .controls {{ display: grid; gap: 8px; }}
    .hint {{ color: #58615b; }}
    #map {{ height: 100vh; width: 100%; }}
    @media (max-width: 800px) {{
      body {{ grid-template-columns: 1fr; grid-template-rows: auto 1fr; }}
      aside {{ max-height: 42vh; border-right: 0; border-bottom: 1px solid #cfd5cf; }}
      #map {{ height: 58vh; }}
    }}
  </style>
</head>
<body>
  <aside>
    <h1>Castros IA Galicia</h1>
    <p class="hint">Vista rápida de revisión. Las etiquetas finales se dibujan en QGIS, no aquí.</p>
    <section id="metrics"></section>
    <h2>Capas</h2>
    <div class="controls">
      <label><input type="checkbox" data-layer="review_points" checked> Puntos revisables</label>
      <label><input type="checkbox" data-layer="positive_seed_buffers_120m" checked> Buffers positivos</label>
      <label><input type="checkbox" data-layer="tile_windows_512m"> Ventanas raster</label>
      <label><input type="checkbox" data-layer="pba_geocoding_candidates" checked> Candidatos PBA</label>
      <label><input type="checkbox" data-layer="hard_negative_candidates"> Negativos candidatos</label>
      <label><input type="checkbox" data-layer="trasancos_aoi" checked> AOI Trasancos</label>
    </div>
    <h2>Leyenda</h2>
    <div class="legend">
      <span><i class="swatch" style="background:#1677ff"></i> train/test/val</span>
      <span><i class="swatch" style="background:#e04f2f"></i> P0</span>
      <span><i class="swatch" style="background:#f2b705"></i> P1</span>
      <span><i class="swatch" style="background:#8a8f98"></i> P2/review</span>
      <span><i class="swatch" style="background:#00a693"></i> PBA geocoding</span>
      <span><i class="swatch line" style="background:#29a36a"></i> buffer/ventana</span>
    </div>
    <h2>Bloqueo actual</h2>
    <p>El entrenamiento sigue bloqueado hasta que QGIS produzca polígonos aceptados en <code>labels_reviewed</code> y negativos aceptados en <code>negative_areas_reviewed</code>.</p>
  </aside>
  <main id="map"></main>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const data = {data_json};
    const map = L.map('map').setView([43.55, -8.18], 11);
    L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    function colorByPriority(props) {{
      if (props.review_priority === 'P0') return '#e04f2f';
      if (props.review_priority === 'P1') return '#f2b705';
      if (props.review_priority === 'P2') return '#8a8f98';
      if (props.split === 'test_o_val') return '#7b3fe4';
      return '#1677ff';
    }}

    function popup(props) {{
      const title = props.primary_name || props.negative_id || props.aoi_id || 'feature';
      const rows = ['site_id','municipality','parish','split','dataset_use','current_dataset_use','pba_decision','pba_name','pba_id_ipaga','pba_tipoloxia','review_priority','qgis_action','suggested_decision','reason','notes']
        .filter(k => props[k])
        .map(k => `<b>${{k}}</b>: ${{String(props[k]).slice(0, 350)}}`);
      return `<b>${{title}}</b><br>${{rows.join('<br>')}}`;
    }}

    const layerMap = {{}};
    layerMap.review_points = L.geoJSON(data.review_points, {{
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, {{
        radius: 6, color: '#1b1f22', weight: 1, fillColor: colorByPriority(feature.properties), fillOpacity: 0.82
      }}),
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }}).addTo(map);

    layerMap.positive_seed_buffers_120m = L.geoJSON(data.positive_seed_buffers_120m, {{
      style: feature => {{ return {{ color: '#29a36a', weight: 2, fillOpacity: 0.08 }}; }},
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }}).addTo(map);

    layerMap.tile_windows_512m = L.geoJSON(data.tile_windows_512m, {{
      style: feature => {{ return {{ color: '#0c8ea0', weight: 1, fillOpacity: 0.04 }}; }},
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }});

    layerMap.pba_geocoding_candidates = L.geoJSON(data.pba_geocoding_candidates, {{
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, {{
        radius: 7, color: '#005c50', weight: 2, fillColor: '#00a693', fillOpacity: 0.72
      }}),
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }}).addTo(map);

    layerMap.hard_negative_candidates = L.geoJSON(data.hard_negative_candidates, {{
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, {{
        radius: 3, color: '#545a60', weight: 1, fillColor: '#c3c8cd', fillOpacity: 0.72
      }}),
      onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties))
    }});

    layerMap.trasancos_aoi = L.geoJSON(data.trasancos_aoi, {{
      style: {{ color: '#111', weight: 2, dashArray: '6 6', fillOpacity: 0 }}
    }}).addTo(map);

    const metrics = document.getElementById('metrics');
    const counts = Object.fromEntries(Object.entries(data).map(([key, value]) => [key, value.features.length]));
    metrics.innerHTML = `
      <div class="metric"><span>Puntos</span><b>${{counts.review_points}}</b></div>
      <div class="metric"><span>Buffers</span><b>${{counts.positive_seed_buffers_120m}}</b></div>
      <div class="metric"><span>Ventanas</span><b>${{counts.tile_windows_512m}}</b></div>
      <div class="metric"><span>PBA</span><b>${{counts.pba_geocoding_candidates}}</b></div>
      <div class="metric"><span>Negativos</span><b>${{counts.hard_negative_candidates}}</b></div>
    `;

    document.querySelectorAll('[data-layer]').forEach(input => {{
      input.addEventListener('change', () => {{
        const layer = layerMap[input.dataset.layer];
        if (input.checked) layer.addTo(map);
        else map.removeLayer(layer);
      }});
    }});

    const group = L.featureGroup([layerMap.review_points, layerMap.positive_seed_buffers_120m, layerMap.pba_geocoding_candidates, layerMap.trasancos_aoi]);
    map.fitBounds(group.getBounds().pad(0.08));
  </script>
</body>
</html>
"""
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    for name, payload in layers.items():
        print(f"{name}={len(payload['features'])}")


if __name__ == "__main__":
    main()
