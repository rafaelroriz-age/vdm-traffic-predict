/**
 * Map module — Leaflet map, per-tab layers, popups.
 */
var map;
var currentLayers = [];

function initMap() {
    map = L.map('map', { center: [-15.5, -49.5], zoom: 7, zoomControl: false, preferCanvas: true });
    L.control.zoom({ position: 'topright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CARTO', subdomains: 'abcd', maxZoom: 19
    }).addTo(map);
    return map;
}

function clearLayers() {
    currentLayers.forEach(function(l) { map.removeLayer(l); });
    currentLayers = [];
}

function fitToSegments(segments) {
    var layer = L.geoJSON(segments);
    var bounds = layer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20] });
}

/* === Popup === */
function createPopup(props) {
    var vmd = props.vmd || 0;
    var src = props.vmd_source || 'estimated';
    var srcLabel = SOURCE_LABELS[src] || src;
    return '<div class="popup-content">' +
        '<div class="popup-header">' +
            '<span class="popup-sre">' + (props.sre || '-') + '</span>' +
            '<span class="popup-badge ' + src + '">' + srcLabel + '</span>' +
        '</div>' +
        '<div class="popup-vmd" style="color:' + getVMDColor(vmd) + '">' + Math.round(vmd).toLocaleString('pt-BR') + '</div>' +
        '<div class="popup-vmd-label">veículos/dia</div>' +
        '<div class="popup-details">' +
            _popDetail('GO', props.go || '-') +
            _popDetail('Regional', props.regional || '-') +
            _popDetail('Classe', props.classe || '-') +
            _popDetail('Extensão', (props.extensao || 0) + ' km') +
            _popDetail('Revest.', props.revest || '-') +
            _popDetail('Capacidade', Math.round(props.capacity || 0).toLocaleString('pt-BR')) +
            _popDetail('V/C', (props.vc_ratio || 0).toFixed(2)) +
            _popDetail('Vel. Livre', (props.free_flow_speed || 0) + ' km/h') +
        '</div></div>';
}

function _popDetail(label, value) {
    return '<div class="popup-detail"><span class="popup-detail-label">' + label + '</span><br><span class="popup-detail-value">' + value + '</span></div>';
}

/* === Tab-specific map views === */

function showRedeView(segments) {
    clearLayers();
    var layer = L.geoJSON(segments, {
        style: function(f) {
            return { color: getClassColor(f.properties.classe), weight: 2.5, opacity: 0.8, lineCap: 'round' };
        },
        onEachFeature: function(f, l) {
            l.bindPopup(createPopup(f.properties), { maxWidth: 300 });
            l.on('mouseover', function() { this.setStyle({ weight: 5, opacity: 1 }); this.bringToFront(); });
            l.on('mouseout', function() { layer.resetStyle(this); });
        }
    }).addTo(map);
    currentLayers.push(layer);
    renderLegend('classe');
}

function showContagensView(segments, points) {
    clearLayers();
    // Dim all segments
    var bgLayer = L.geoJSON(segments, {
        style: function(f) {
            var isObs = f.properties.vmd_source === 'observed';
            return {
                color: isObs ? '#22c55e' : '#475569',
                weight: isObs ? 3 : 1.5,
                opacity: isObs ? 0.7 : 0.2,
                lineCap: 'round'
            };
        },
        onEachFeature: function(f, l) {
            l.bindPopup(createPopup(f.properties), { maxWidth: 300 });
        }
    }).addTo(map);
    currentLayers.push(bgLayer);

    // Count points
    var ptLayer = L.geoJSON(points, {
        pointToLayer: function(f, ll) {
            var vmd = f.properties.vmd || 0;
            var r = Math.max(4, Math.min(14, Math.log10(vmd + 1) * 3));
            return L.circleMarker(ll, { radius: r, fillColor: getVMDColor(vmd), fillOpacity: 0.9, color: '#fff', weight: 1.5 });
        },
        onEachFeature: function(f, l) {
            var p = f.properties;
            l.bindPopup('<div class="popup-content"><div class="popup-header"><span class="popup-sre">' + p.sre + '</span><span class="popup-badge observed">Contagem</span></div>' +
                '<div class="popup-vmd" style="color:' + getVMDColor(p.vmd) + '">' + Math.round(p.vmd).toLocaleString('pt-BR') + '</div>' +
                '<div class="popup-vmd-label">veículos/dia</div></div>', { maxWidth: 260 });
        }
    }).addTo(map);
    currentLayers.push(ptLayer);
    renderLegend('count');
}

function showPropagacaoView(segments, step) {
    clearLayers();
    // step: 0=observed only, 1=+propagated, 2=+estimated (all)
    var layer = L.geoJSON(segments, {
        style: function(f) {
            var src = f.properties.vmd_source;
            var visible = (step >= 2) ||
                          (step >= 1 && (src === 'observed' || src === 'propagated')) ||
                          (step === 0 && src === 'observed');
            return {
                color: getSourceColor(src),
                weight: src === 'observed' ? 3 : 2,
                opacity: visible ? 0.8 : 0.05,
                lineCap: 'round'
            };
        },
        onEachFeature: function(f, l) {
            l.bindPopup(createPopup(f.properties), { maxWidth: 300 });
        }
    }).addTo(map);
    currentLayers.push(layer);
    renderLegend('source');
}

function showGravitacionalView(gravityData) {
    clearLayers();
    // Desire lines
    if (gravityData.desire_lines) {
        var maxFlow = Math.max.apply(null, gravityData.desire_lines.map(function(d) { return d.flow; }));
        gravityData.desire_lines.forEach(function(dl) {
            var w = Math.max(0.5, (dl.flow / maxFlow) * 4);
            var line = L.polyline([[dl.o_lat, dl.o_lon], [dl.d_lat, dl.d_lon]], {
                color: '#ef4444', weight: w, opacity: 0.3, dashArray: '4 4'
            }).addTo(map);
            line.bindPopup('Fluxo: ' + Math.round(dl.flow).toLocaleString('pt-BR') + ' viagens/dia');
            currentLayers.push(line);
        });
    }
    // Zone markers
    if (gravityData.zones) {
        gravityData.zones.forEach(function(z) {
            var r = Math.max(4, Math.min(16, z.degree * 1.5));
            var color = z.is_urban ? '#f59e0b' : (z.is_federal ? '#ef4444' : '#3b82f6');
            var marker = L.circleMarker([z.lat, z.lon], {
                radius: r, fillColor: color, fillOpacity: 0.7, color: '#fff', weight: 1
            }).addTo(map);
            marker.bindPopup('Zona #' + z.id + '<br>Grau: ' + z.degree + '<br>' +
                (z.is_urban ? 'Urbana' : 'Rural') + ' | ' + (z.is_federal ? 'Federal' : 'Estadual'));
            currentLayers.push(marker);
        });
    }
    renderLegend('gravity');
}

function showAlocacaoView(segments) {
    clearLayers();
    var layer = L.geoJSON(segments, {
        style: function(f) {
            var vc = f.properties.vc_ratio || 0;
            return { color: getVCColor(vc), weight: Math.max(1.5, Math.min(5, vc * 3)), opacity: 0.8, lineCap: 'round' };
        },
        onEachFeature: function(f, l) {
            l.bindPopup(createPopup(f.properties), { maxWidth: 300 });
            l.on('mouseover', function() { this.setStyle({ weight: 6, opacity: 1 }); this.bringToFront(); });
            l.on('mouseout', function() { layer.resetStyle(this); });
        }
    }).addTo(map);
    currentLayers.push(layer);
    renderLegend('vc');
}

function showCalibracaoView(segments, scatterData) {
    clearLayers();
    // Build lookup of GEH by sre
    var gehMap = {};
    if (scatterData) {
        scatterData.forEach(function(d) { gehMap[d.sre] = d.geh; });
    }
    var layer = L.geoJSON(segments, {
        filter: function(f) { return f.properties.vmd_source === 'observed'; },
        style: function(f) {
            var geh = gehMap[f.properties.sre] || 0;
            return { color: getGEHColor(geh), weight: 3.5, opacity: 0.8, lineCap: 'round' };
        },
        onEachFeature: function(f, l) {
            var geh = gehMap[f.properties.sre] || 0;
            l.bindPopup(createPopup(f.properties) + '<br><b>GEH: ' + geh.toFixed(1) + '</b>', { maxWidth: 300 });
        }
    }).addTo(map);
    currentLayers.push(layer);
    renderLegend('geh');
}

function showResultadoView(segments, filter) {
    clearLayers();
    var features = segments;
    if (filter) {
        features = { type: 'FeatureCollection', features: segments.features.filter(function(f) {
            var p = f.properties;
            if (filter.source !== 'all' && p.vmd_source !== filter.source) return false;
            if (p.vmd < filter.vmdMin || p.vmd > filter.vmdMax) return false;
            if (filter.regional !== 'all' && String(p.regional) !== filter.regional) return false;
            if (filter.classe !== 'all' && p.classe !== filter.classe) return false;
            return true;
        })};
    }
    var layer = L.geoJSON(features, {
        style: function(f) {
            var p = f.properties;
            var isObs = p.vmd_source === 'observed';
            return {
                color: getVMDColor(p.vmd || 0),
                weight: isObs ? 3.5 : 2.5,
                opacity: isObs ? 0.9 : 0.7,
                dashArray: isObs ? null : (p.vmd_source === 'estimated' ? '4 4' : null),
                lineCap: 'round'
            };
        },
        onEachFeature: function(f, l) {
            l.bindPopup(createPopup(f.properties), { maxWidth: 300 });
            l.on('mouseover', function() { this.setStyle({ weight: 6, opacity: 1 }); this.bringToFront(); });
            l.on('mouseout', function() { layer.resetStyle(this); });
        }
    }).addTo(map);
    currentLayers.push(layer);
    renderLegend('vmd');
    return layer;
}

window.zoomToFeature = function(feature) {
    if (!feature.geometry) return;
    var l = L.geoJSON(feature);
    map.fitBounds(l.getBounds(), { padding: [50, 50], maxZoom: 14 });
};
