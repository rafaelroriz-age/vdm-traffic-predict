/**
 * Map module - Leaflet map initialization and layer management.
 */
var map;
var segmentsLayer;
var pointsLayer;
var confidenceLayer;

function initMap() {
    map = L.map('map', {
        center: [-15.5, -49.5],
        zoom: 7,
        zoomControl: false
    });

    L.control.zoom({ position: 'topright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(map);

    return map;
}

function createPopupContent(props) {
    var vmd = props.vmd || 0;
    var vmdFormatted = Math.round(vmd).toLocaleString('pt-BR');
    var sourceLabel = props.vmd_source === 'observed' ? 'Observado' : 'Estimado';
    var sourceBadge = props.vmd_source === 'observed' ? 'observed' : 'predicted';
    var confClass = 'confidence-' + (props.confidence || 'unknown');

    var modelsHTML = '';
    if (props.vmd_rf) {
        modelsHTML = '<div class="popup-models">' +
            '<h5>Estimativas por Modelo</h5>' +
            '<div class="popup-model-row"><span>Random Forest</span><span>' + Math.round(props.vmd_rf).toLocaleString('pt-BR') + '</span></div>' +
            '<div class="popup-model-row"><span>XGBoost</span><span>' + Math.round(props.vmd_xgb).toLocaleString('pt-BR') + '</span></div>' +
            '<div class="popup-model-row"><span>IDW</span><span>' + Math.round(props.vmd_idw).toLocaleString('pt-BR') + '</span></div>' +
            '<div class="popup-model-row"><span>Ensemble</span><span><strong>' + Math.round(props.vmd_ensemble).toLocaleString('pt-BR') + '</strong></span></div>' +
            '</div>';
    }

    var vehicleHTML = '';
    if (props.pct_light !== undefined && props.pct_light !== null) {
        vehicleHTML = '<div class="popup-detail"><span class="popup-detail-label">% Leves</span><br><span class="popup-detail-value">' + (props.pct_light * 100).toFixed(1) + '%</span></div>' +
            '<div class="popup-detail"><span class="popup-detail-label">% Pesados</span><br><span class="popup-detail-value">' + ((props.pct_heavy || 0) * 100).toFixed(1) + '%</span></div>';
    }

    return '<div class="popup-content">' +
        '<div class="popup-header">' +
            '<span class="popup-sre">' + (props.sre || '-') + '</span>' +
            '<span class="popup-badge ' + sourceBadge + '">' + sourceLabel + '</span>' +
        '</div>' +
        '<div class="popup-vmd" style="color:' + getVMDColor(vmd) + '">' + vmdFormatted + '</div>' +
        '<div class="popup-vmd-label">veículos/dia</div>' +
        '<div class="popup-details">' +
            '<div class="popup-detail"><span class="popup-detail-label">GO</span><br><span class="popup-detail-value">' + (props.go || '-') + '</span></div>' +
            '<div class="popup-detail"><span class="popup-detail-label">Regional</span><br><span class="popup-detail-value">' + (props.regional || '-') + '</span></div>' +
            '<div class="popup-detail"><span class="popup-detail-label">Classe</span><br><span class="popup-detail-value">' + (props.classe || '-') + '</span></div>' +
            '<div class="popup-detail"><span class="popup-detail-label">Extensão</span><br><span class="popup-detail-value">' + (props.extensao || 0) + ' km</span></div>' +
            '<div class="popup-detail"><span class="popup-detail-label">Revestimento</span><br><span class="popup-detail-value">' + (props.revest || '-') + '</span></div>' +
            '<div class="popup-detail"><span class="popup-detail-label">Confiança</span><br><span class="popup-detail-value ' + confClass + '">' + (props.confidence || '-') + '</span></div>' +
            vehicleHTML +
        '</div>' +
        modelsHTML +
    '</div>';
}

function addSegmentsLayer(geojson) {
    console.log('[Map] Adding ' + geojson.features.length + ' segments...');
    if (segmentsLayer) map.removeLayer(segmentsLayer);

    segmentsLayer = L.geoJSON(geojson, {
        style: function(feature) {
            var p = feature.properties;
            var isObserved = p.vmd_source === 'observed';
            return {
                color: getVMDColor(p.vmd || 0),
                weight: isObserved ? 4 : 3,
                opacity: isObserved ? 0.9 : 0.65,
                dashArray: isObserved ? null : '6 4',
                lineCap: 'round'
            };
        },
        onEachFeature: function(feature, layer) {
            layer.bindPopup(createPopupContent(feature.properties), { maxWidth: 320 });
            layer.on('mouseover', function() {
                this.setStyle({ weight: 6, opacity: 1 });
                this.bringToFront();
            });
            layer.on('mouseout', function() {
                segmentsLayer.resetStyle(this);
            });
        }
    });

    segmentsLayer.addTo(map);
    console.log('[Map] Segments layer added successfully');
    return segmentsLayer;
}

function addConfidenceLayer(geojson) {
    if (confidenceLayer) map.removeLayer(confidenceLayer);

    confidenceLayer = L.geoJSON(geojson, {
        filter: function(f) { return f.properties.vmd_source === 'predicted'; },
        style: function(feature) {
            return {
                color: getConfidenceColor(feature.properties.confidence),
                weight: 3,
                opacity: 0.7,
                lineCap: 'round'
            };
        },
        onEachFeature: function(feature, layer) {
            layer.bindPopup(createPopupContent(feature.properties), { maxWidth: 320 });
        }
    });

    return confidenceLayer;
}

function addPointsLayer(geojson) {
    console.log('[Map] Adding ' + geojson.features.length + ' count points...');
    if (pointsLayer) map.removeLayer(pointsLayer);

    pointsLayer = L.geoJSON(geojson, {
        pointToLayer: function(feature, latlng) {
            var vmd = feature.properties.vmd || 0;
            var radius = Math.max(4, Math.min(12, Math.log10(vmd + 1) * 3));
            return L.circleMarker(latlng, {
                radius: radius,
                fillColor: getVMDColor(vmd),
                fillOpacity: 0.9,
                color: '#ffffff',
                weight: 2
            });
        },
        onEachFeature: function(feature, layer) {
            var p = feature.properties;
            layer.bindPopup(
                '<div class="popup-content">' +
                    '<div class="popup-header">' +
                        '<span class="popup-sre">' + (p.sre || '-') + '</span>' +
                        '<span class="popup-badge observed">Contagem</span>' +
                    '</div>' +
                    '<div class="popup-vmd" style="color:' + getVMDColor(p.vmd) + '">' + Math.round(p.vmd).toLocaleString('pt-BR') + '</div>' +
                    '<div class="popup-vmd-label">veículos/dia</div>' +
                    '<div class="popup-details">' +
                        '<div class="popup-detail"><span class="popup-detail-label">GO</span><br><span class="popup-detail-value">' + (p.go || '-') + '</span></div>' +
                        '<div class="popup-detail"><span class="popup-detail-label">Regional</span><br><span class="popup-detail-value">' + (p.regional || '-') + '</span></div>' +
                    '</div>' +
                '</div>',
                { maxWidth: 280 }
            );
        }
    });

    pointsLayer.addTo(map);
    console.log('[Map] Points layer added successfully');
    return pointsLayer;
}

function filterSegments(geojson, filter) {
    var filtered = {
        type: 'FeatureCollection',
        features: geojson.features.filter(function(f) { return featureMatchesFilter(f, filter); })
    };
    addSegmentsLayer(filtered);
}

window.zoomToFeature = function(feature) {
    if (!feature.geometry) return;
    var layer = L.geoJSON(feature);
    map.fitBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 14 });
};
