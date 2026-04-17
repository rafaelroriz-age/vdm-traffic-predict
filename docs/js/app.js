/**
 * App module — data loading, initialization, orchestration.
 */
(async function() {
    'use strict';

    var loading = document.getElementById('loading');

    function showError(msg) {
        loading.innerHTML = '<p style="color:#ef4444;padding:20px;max-width:600px;">' + msg + '</p>';
        console.error(msg);
    }

    try {
        console.log('[App] Initializing...');
        initMap();

        var basePath = 'data/';

        // Load all data files in parallel
        var responses = await Promise.all([
            fetch(basePath + 'segments.geojson'),
            fetch(basePath + 'count_points.geojson'),
            fetch(basePath + 'network_graph.json'),
            fetch(basePath + 'propagation_frames.json'),
            fetch(basePath + 'gravity_model.json'),
            fetch(basePath + 'calibration_report.json')
        ]);

        var names = ['segments.geojson', 'count_points.geojson', 'network_graph.json',
                     'propagation_frames.json', 'gravity_model.json', 'calibration_report.json'];
        for (var i = 0; i < responses.length; i++) {
            if (!responses[i].ok) throw new Error('Falha ao carregar ' + names[i] + ': ' + responses[i].status);
        }

        var segments = await responses[0].json();
        var points = await responses[1].json();
        var network = await responses[2].json();
        var frames = await responses[3].json();
        var gravity = await responses[4].json();
        var calibration = await responses[5].json();

        console.log('[App] Loaded: ' + segments.features.length + ' segments, ' +
            points.features.length + ' points, ' + network.nodes.length + ' nodes, ' +
            frames.length + ' frames, ' + gravity.zones.length + ' zones');

        // Store globally for search
        window.segmentsData = segments;

        // Bundle all data
        var data = {
            segments: segments,
            points: points,
            network: network,
            frames: frames,
            gravity: gravity,
            calibration: calibration
        };

        // Initialize sidebar (tab switching, controls, etc.)
        initSidebar(data);

        // Render stats for all tabs
        renderStats(data);

        // Render all charts
        renderClassKmChart(segments);
        renderSurfaceChart(segments);
        renderCoverageChart(segments);
        renderVMDDistribution(segments, 'vmd-dist');
        renderVehicleChart(segments);
        renderPropagationChart(frames);
        renderZoneTypeChart(gravity.zones);
        renderDesireLinesTable(gravity.desire_lines);
        renderVCDistChart(segments);
        renderSourcePieChart(segments);
        renderScatterChart(calibration.scatter_data);
        renderGEHChart(calibration.scatter_data);
        renderVMDDistribution(segments, 'resultado-dist');
        renderRegionalChart(segments);

        // Populate filters
        populateFilters(segments);

        // Hide loading first so map container gets proper dimensions
        console.log('[App] Ready!');
        loading.classList.add('hidden');
        setTimeout(function() {
            loading.style.display = 'none';
            // Ensure map knows its proper size after loading overlay is removed
            map.invalidateSize();
            console.log('[Map] After invalidateSize, size:', map.getSize());
            // Show initial view (Tab 1: Rede)
            showRedeView(segments);
            fitToSegments(segments);
            console.log('[Map] Layers on map:', currentLayers.length);
        }, 100);

    } catch (err) {
        showError('Erro ao carregar dados: ' + err.message);
        console.error(err);
    }
})();
