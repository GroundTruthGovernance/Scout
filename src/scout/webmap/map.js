// Scout embedded map. One QWebEngineView page, one or more MapLibre GL JS
// instances keyed by "pane id" (today: a single pane "main"; the Run
// Compare / Tiled Product View work described in docs/ARCHITECTURE.md
// extends `panes` to more entries rather than requiring a rewrite).
//
// Python talks to this file via QWebEngineView.page().runJavaScript(...)
// calling the functions below directly. This file talks back to Python via
// window.bridge (a QWebChannel-exposed QObject; see app/panels/map_panel.py)
// for the two events Python needs to react to: a polygon finished drawing,
// and a map click (used for pins and the analytical eyedropper).

(function () {
  "use strict";

  const panes = {}; // paneId -> { map, drawState, layers: {layerId: true}, markers: {markerId: maplibregl.Marker} }

  const OSM_STYLE = {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "&copy; OpenStreetMap contributors",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  };

  // No Google Maps Platform / Bing key is bundled with Scout (see
  // docs/ARCHITECTURE.md — the desktop app is a client of the user's own
  // accounts, not a wrapper around a shared key). Esri World Imagery's
  // public tile endpoint is used as the no-key satellite default; a
  // Sentinel-2 composite rendered from Earth Engine is the analytically
  // meaningful "satellite" layer for actual work, added as a raster layer
  // on top rather than as the basemap.
  const SATELLITE_STYLE = {
    version: 8,
    sources: {
      esri: {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        attribution: "Esri, Maxar, Earthstar Geographics",
      },
    },
    layers: [{ id: "esri", type: "raster", source: "esri" }],
  };

  const BASE_STYLES = { osm: OSM_STYLE, satellite: SATELLITE_STYLE };

  function paneOrThrow(paneId) {
    const pane = panes[paneId];
    if (!pane) throw new Error("Unknown map pane: " + paneId);
    return pane;
  }

  function createMap(paneId, containerId, centerLon, centerLat, zoom, styleName) {
    const map = new maplibregl.Map({
      container: containerId,
      style: BASE_STYLES[styleName] || OSM_STYLE,
      center: [centerLon, centerLat],
      zoom: zoom,
      attributionControl: true,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

    panes[paneId] = { map: map, drawState: null, layers: {}, markers: {} };

    map.on("load", function () {
      map.addSource("scout-draw", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "scout-draw-fill",
        type: "fill",
        source: "scout-draw",
        filter: ["==", "$type", "Polygon"],
        paint: { "fill-color": "#00FFFF", "fill-opacity": 0.15 },
      });
      map.addLayer({
        id: "scout-draw-line",
        type: "line",
        source: "scout-draw",
        paint: { "line-color": "#00FFFF", "line-width": 2 },
      });
      map.addLayer({
        id: "scout-draw-points",
        type: "circle",
        source: "scout-draw",
        filter: ["==", "$type", "Point"],
        paint: { "circle-radius": 4, "circle-color": "#00FFFF" },
      });
    });

    map.on("click", function (e) {
      onMapClick(paneId, e.lngLat.lng, e.lngLat.lat);
    });

    return paneId;
  }

  function setBaseStyle(paneId, styleName) {
    const pane = paneOrThrow(paneId);
    pane.map.setStyle(BASE_STYLES[styleName] || OSM_STYLE);
  }

  // -- Drawing ------------------------------------------------------------
  //
  // Hand-rolled rather than a plugin (mapbox-gl-draw et al.) to keep exact
  // control over the interaction Scout needs: click to add a vertex,
  // double-click or Enter to finish, Escape to cancel — matching the
  // single-reference-polygon-at-a-time drawing tool the GEE prototype used.

  function refreshDrawSource(paneId) {
    const pane = paneOrThrow(paneId);
    const source = pane.map.getSource("scout-draw");
    if (!source || !pane.drawState) return;

    const coords = pane.drawState.coords;
    const features = [];
    coords.forEach(function (c) {
      features.push({ type: "Feature", geometry: { type: "Point", coordinates: c }, properties: {} });
    });
    if (coords.length >= 2) {
      const ring = coords.concat(pane.drawState.mode === "polygon" ? [coords[0]] : []);
      features.push({
        type: "Feature",
        geometry: { type: pane.drawState.mode === "polygon" ? "Polygon" : "LineString",
                    coordinates: pane.drawState.mode === "polygon" ? [ring] : ring },
        properties: {},
      });
    }
    source.setData({ type: "FeatureCollection", features: features });
  }

  function enableDrawPolygon(paneId) {
    const pane = paneOrThrow(paneId);
    pane.drawState = { mode: "polygon", coords: [] };
    pane.map.getCanvasContainer().classList.add("scout-cursor-crosshair");
    refreshDrawSource(paneId);
  }

  function enablePinDrop(paneId) {
    const pane = paneOrThrow(paneId);
    pane.drawState = { mode: "point", coords: [] };
    pane.map.getCanvasContainer().classList.add("scout-cursor-crosshair");
  }

  function disableDrawing(paneId) {
    const pane = paneOrThrow(paneId);
    pane.drawState = null;
    pane.map.getCanvasContainer().classList.remove("scout-cursor-crosshair");
  }

  function clearDrawnGeometry(paneId) {
    const pane = paneOrThrow(paneId);
    if (pane.drawState) pane.drawState.coords = [];
    refreshDrawSource(paneId);
  }

  function finishPolygon(paneId) {
    const pane = paneOrThrow(paneId);
    if (!pane.drawState || pane.drawState.coords.length < 3) return;
    const ring = pane.drawState.coords.concat([pane.drawState.coords[0]]);
    const geojson = { type: "Polygon", coordinates: [ring] };
    disableDrawing(paneId);
    if (window.bridge) window.bridge.on_polygon_drawn(JSON.stringify(geojson));
  }

  function onMapClick(paneId, lon, lat) {
    const pane = paneOrThrow(paneId);
    if (pane.drawState && pane.drawState.mode === "polygon") {
      pane.drawState.coords.push([lon, lat]);
      refreshDrawSource(paneId);
      return;
    }
    if (pane.drawState && pane.drawState.mode === "point") {
      disableDrawing(paneId);
      if (window.bridge) window.bridge.on_point_clicked(lon, lat);
      return;
    }
    // Not in a drawing mode: still report the click for coordinate readout
    // / the analytical eyedropper, which reads the active layer at a point
    // without needing "arm pin" first.
    if (window.bridge) window.bridge.on_map_clicked(lon, lat);
  }

  document.addEventListener("keydown", function (e) {
    const mainPane = panes["main"];
    if (!mainPane || !mainPane.drawState) return;
    if (e.key === "Enter") finishPolygon("main");
    if (e.key === "Escape") disableDrawing("main");
  });

  document.addEventListener("dblclick", function () {
    if (panes["main"] && panes["main"].drawState && panes["main"].drawState.mode === "polygon") {
      finishPolygon("main");
    }
  });

  // -- Raster layers (EE tile overlays: AE responses, HSV masks, S2, etc) -

  function addRasterLayer(paneId, layerId, tileUrlTemplate, opacity) {
    const pane = paneOrThrow(paneId);
    const map = pane.map;
    if (map.getLayer(layerId)) removeLayer(paneId, layerId);
    map.addSource(layerId, { type: "raster", tiles: [tileUrlTemplate], tileSize: 256 });
    map.addLayer({ id: layerId, type: "raster", source: layerId, paint: { "raster-opacity": opacity } });
    pane.layers[layerId] = true;
  }

  function setLayerOpacity(paneId, layerId, opacity) {
    const pane = paneOrThrow(paneId);
    if (pane.map.getLayer(layerId)) pane.map.setPaintProperty(layerId, "raster-opacity", opacity);
  }

  function setLayerVisible(paneId, layerId, visible) {
    const pane = paneOrThrow(paneId);
    if (pane.map.getLayer(layerId)) {
      pane.map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
    }
  }

  function removeLayer(paneId, layerId) {
    const pane = paneOrThrow(paneId);
    if (pane.map.getLayer(layerId)) pane.map.removeLayer(layerId);
    if (pane.map.getSource(layerId)) pane.map.removeSource(layerId);
    delete pane.layers[layerId];
  }

  function flyTo(paneId, lon, lat, zoom) {
    paneOrThrow(paneId).map.flyTo({ center: [lon, lat], zoom: zoom });
  }

  // -- Point markers (saved pins: observations + probes) ------------------

  function addMarker(paneId, markerId, lon, lat, color, popupText) {
    const pane = paneOrThrow(paneId);
    if (pane.markers[markerId]) removeMarker(paneId, markerId);
    const marker = new maplibregl.Marker({ color: color || "#00FFFF" }).setLngLat([lon, lat]);
    if (popupText) marker.setPopup(new maplibregl.Popup({ offset: 12 }).setText(popupText));
    marker.addTo(pane.map);
    pane.markers[markerId] = marker;
  }

  function removeMarker(paneId, markerId) {
    const pane = paneOrThrow(paneId);
    const marker = pane.markers[markerId];
    if (marker) {
      marker.remove();
      delete pane.markers[markerId];
    }
  }

  function setMarkerVisible(paneId, markerId, visible) {
    const pane = paneOrThrow(paneId);
    const marker = pane.markers[markerId];
    if (!marker) return;
    marker.getElement().style.display = visible ? "" : "none";
  }

  function clearMarkers(paneId) {
    const pane = paneOrThrow(paneId);
    Object.keys(pane.markers).forEach(function (markerId) {
      pane.markers[markerId].remove();
    });
    pane.markers = {};
  }

  window.scoutMap = {
    createMap: createMap,
    setBaseStyle: setBaseStyle,
    enableDrawPolygon: enableDrawPolygon,
    enablePinDrop: enablePinDrop,
    disableDrawing: disableDrawing,
    clearDrawnGeometry: clearDrawnGeometry,
    addRasterLayer: addRasterLayer,
    setLayerOpacity: setLayerOpacity,
    setLayerVisible: setLayerVisible,
    removeLayer: removeLayer,
    flyTo: flyTo,
    addMarker: addMarker,
    removeMarker: removeMarker,
    setMarkerVisible: setMarkerVisible,
    clearMarkers: clearMarkers,
  };

  if (typeof qt !== "undefined" && qt.webChannelTransport) {
    new QWebChannel(qt.webChannelTransport, function (channel) {
      window.bridge = channel.objects.bridge;
      window.scoutMap.createMap("main", "map-root", -2.95, 53.79, 10, "osm");
      if (window.bridge && window.bridge.on_map_ready) window.bridge.on_map_ready();
    });
  }
})();
