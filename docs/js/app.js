/**
 * App module - main controller, data loading, and initialization.
 */
(async function () {
    'use strict';

    // Init
    initMap();
    initSidebar();
    renderLegend();

    const loading = document.getElementById('loading');

    try {
        // Load data in parallel
        const [segmentsRes, pointsRes, metricsRes] = await Promise.all([
            fetch('data/segments.geojson'),
            fetch('data/count_points.geojson'),
            fetch('data/model_metrics.json')
        ]);

        const segments = await segmentsRes.json();
        const points = await pointsRes.json();
        const metrics = await metricsRes.json();

        // Store globally for search
        window.segmentsData = segments;

        // Update header stats
        let totalKm = 0, observed = 0, predicted = 0;
        segments.features.forEach(f => {
            totalKm += f.properties.extensao || 0;
            if (f.properties.vmd_source === 'observed') observed++;
            else predicted++;
        });
        document.getElementById('stat-total-km').textContent = Math.round(totalKm).toLocaleString('pt-BR');
        document.getElementById('stat-observed').textContent = observed.toLocaleString('pt-BR');
        document.getElementById('stat-predicted').textContent = predicted.toLocaleString('pt-BR');

        // Render map layers
        addSegmentsLayer(segments);
        addPointsLayer(points);
        const confLayer = addConfidenceLayer(segments);

        // Fit bounds
        if (segmentsLayer) {
            map.fitBounds(segmentsLayer.getBounds(), { padding: [20, 20] });
        }

        // Render charts
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
        document.getElementById('layer-segments').addEventListener('change', e => {
            if (e.target.checked) segmentsLayer.addTo(map);
            else map.removeLayer(segmentsLayer);
        });

        document.getElementById('layer-points').addEventListener('change', e => {
            if (e.target.checked) pointsLayer.addTo(map);
            else map.removeLayer(pointsLayer);
        });

        document.getElementById('layer-confidence').addEventListener('change', e => {
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
        document.getElementById('btn-apply-filter').addEventListener('click', () => {
            const filter = getFilterState();
            filterSegments(segments, filter);
        });

        // Hide loading
        loading.classList.add('hidden');
        setTimeout(() => loading.style.display = 'none', 300);

    } catch (err) {
        console.error('Failed to load data:', err);
        loading.innerHTML = `<p style="color:#ef4444;">Erro ao carregar dados: ${err.message}</p>`;
    }
})();
