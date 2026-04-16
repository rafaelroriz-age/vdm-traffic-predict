/**
 * App module - main controller, data loading, and initialization.
 */
(async function () {
    'use strict';

    const loading = document.getElementById('loading');

    function showError(msg) {
        loading.innerHTML = '<p style="color:#ef4444;padding:20px;">' + msg + '</p>';
        console.error(msg);
    }

    try {
        // Init map and sidebar
        console.log('[App] Initializing map...');
        initMap();
        initSidebar();
        renderLegend();

        // Determine base path for data files
        const basePath = 'data/';
        console.log('[App] Loading data from:', basePath);

        // Load data in parallel
        const [segmentsRes, pointsRes, metricsRes] = await Promise.all([
            fetch(basePath + 'segments.geojson'),
            fetch(basePath + 'count_points.geojson'),
            fetch(basePath + 'model_metrics.json')
        ]);

        if (!segmentsRes.ok) throw new Error('Failed to load segments.geojson: ' + segmentsRes.status);
        if (!pointsRes.ok) throw new Error('Failed to load count_points.geojson: ' + pointsRes.status);
        if (!metricsRes.ok) throw new Error('Failed to load model_metrics.json: ' + metricsRes.status);

        const segments = await segmentsRes.json();
        const points = await pointsRes.json();
        const metrics = await metricsRes.json();

        console.log('[App] Loaded segments:', segments.features.length);
        console.log('[App] Loaded points:', points.features.length);

        // Store globally for search
        window.segmentsData = segments;

        // Update header stats
        let totalKm = 0, observed = 0, predicted = 0;
        segments.features.forEach(function(f) {
            totalKm += f.properties.extensao || 0;
            if (f.properties.vmd_source === 'observed') observed++;
            else predicted++;
        });
        document.getElementById('stat-total-km').textContent = Math.round(totalKm).toLocaleString('pt-BR');
        document.getElementById('stat-observed').textContent = observed.toLocaleString('pt-BR');
        document.getElementById('stat-predicted').textContent = predicted.toLocaleString('pt-BR');

        // Render map layers
        console.log('[App] Adding segments layer...');
        addSegmentsLayer(segments);

        console.log('[App] Adding points layer...');
        addPointsLayer(points);

        var confLayer = addConfidenceLayer(segments);

        // Fit bounds to data
        if (segmentsLayer) {
            var bounds = segmentsLayer.getBounds();
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [20, 20] });
                console.log('[App] Map fitted to bounds:', bounds.toBBoxString());
            }
        }

        // Render charts
        console.log('[App] Rendering charts...');
        renderVMDDistribution(segments);
        renderRegionalChart(segments);
        renderVehicleChart(segments);
        renderModelR2Chart(metrics);
        renderModelRMSEChart(metrics);
        renderFeatureImportance(metrics);
        updateModelDetails(metrics);

        // Populate filters
        populateRegionalFilter(segments);

        // Layer toggles
        document.getElementById('layer-segments').addEventListener('change', function(e) {
            if (e.target.checked) segmentsLayer.addTo(map);
            else map.removeLayer(segmentsLayer);
        });

        document.getElementById('layer-points').addEventListener('change', function(e) {
            if (e.target.checked) pointsLayer.addTo(map);
            else map.removeLayer(pointsLayer);
        });

        document.getElementById('layer-confidence').addEventListener('change', function(e) {
            if (e.target.checked) {
                confLayer.addTo(map);
                if (segmentsLayer) map.removeLayer(segmentsLayer);
                document.getElementById('layer-segments').checked = false;
            } else {
                map.removeLayer(confLayer);
                segmentsLayer.addTo(map);
                document.getElementById('layer-segments').checked = true;
            }
        });

        // Filter apply
        document.getElementById('btn-apply-filter').addEventListener('click', function() {
            var filter = getFilterState();
            filterSegments(segments, filter);
        });

        // Hide loading
        console.log('[App] Done! Hiding loader.');
        loading.classList.add('hidden');
        setTimeout(function() { loading.style.display = 'none'; }, 300);

    } catch (err) {
        showError('Erro ao carregar dados: ' + err.message);
        console.error(err);
    }
})();
