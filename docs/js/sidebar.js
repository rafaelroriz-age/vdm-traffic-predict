/**
 * Sidebar module — tab switching, search, filters, animation controls, stats rendering.
 */
var animTimer = null;
var animStep = 0;

function initSidebar(data) {
    // Tab switching
    document.querySelectorAll('.step-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var tab = btn.dataset.tab;
            activateTab(tab, data);
        });
    });

    // Search
    var searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(handleSearch, 300));
    }

    // Filter
    var filterBtn = document.getElementById('btn-apply-filter');
    if (filterBtn) {
        filterBtn.addEventListener('click', function() {
            var filter = getFilterState();
            showResultadoView(data.segments, filter);
        });
    }

    // Animation controls
    document.getElementById('btn-play').addEventListener('click', function() { startAnimation(data); });
    document.getElementById('btn-pause').addEventListener('click', stopAnimation);
    document.getElementById('btn-reset').addEventListener('click', function() { resetAnimation(data); });
    document.getElementById('anim-slider').addEventListener('input', function() {
        animStep = parseInt(this.value);
        updateAnimFrame(data);
    });
}

function activateTab(tab, data) {
    // Update step buttons
    document.querySelectorAll('.step-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelector('[data-tab="' + tab + '"]').classList.add('active');

    // Update panels
    document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
    document.getElementById('panel-' + tab).classList.add('active');

    // Update map view
    stopAnimation();
    switch (tab) {
        case 'rede':
            showRedeView(data.segments);
            break;
        case 'contagens':
            showContagensView(data.segments, data.points);
            break;
        case 'propagacao':
            resetAnimation(data);
            break;
        case 'gravitacional':
            showGravitacionalView(data.gravity);
            break;
        case 'alocacao':
            showAlocacaoView(data.segments);
            break;
        case 'calibracao':
            showCalibracaoView(data.segments, data.calibration.scatter_data);
            break;
        case 'resultado':
            showResultadoView(data.segments);
            break;
    }
}

/* === Animation === */
function startAnimation(data) {
    stopAnimation();
    var frames = data.frames;
    var maxStep = frames.length - 1;
    animTimer = setInterval(function() {
        if (animStep >= maxStep) { stopAnimation(); return; }
        animStep++;
        document.getElementById('anim-slider').value = animStep;
        updateAnimFrame(data);
    }, 400);
}

function stopAnimation() {
    if (animTimer) { clearInterval(animTimer); animTimer = null; }
}

function resetAnimation(data) {
    stopAnimation();
    animStep = 0;
    document.getElementById('anim-slider').value = 0;
    updateAnimFrame(data);
}

function updateAnimFrame(data) {
    var frames = data.frames;
    if (!frames || frames.length === 0) return;
    var frame = frames[Math.min(animStep, frames.length - 1)];
    var cov = (frame.coverage * 100).toFixed(1);
    document.getElementById('anim-status').textContent = 'Iteração ' + frame.iteration + ' — Cobertura: ' + cov + '%';
    document.getElementById('anim-progress').style.width = cov + '%';

    // Map: show segments based on coverage threshold
    // coverage < 0.5 → only observed, < 0.95 → observed+propagated, else all
    var step = frame.coverage < 0.5 ? 0 : (frame.coverage < 0.95 ? 1 : 2);
    showPropagacaoView(data.segments, step);
}

/* === Stats Rendering === */
function renderStats(data) {
    var segs = data.segments;
    var nw = data.network;
    var frames = data.frames;
    var grav = data.gravity;
    var cal = data.calibration;

    var totalKm = 0, observed = 0, propagated = 0, assigned = 0, estimated = 0;
    segs.features.forEach(function(f) {
        totalKm += f.properties.extensao || 0;
        var s = f.properties.vmd_source;
        if (s === 'observed') observed++;
        else if (s === 'propagated') propagated++;
        else if (s === 'assigned') assigned++;
        else estimated++;
    });
    var total = segs.features.length;

    // Header stats
    document.getElementById('stat-total-km').textContent = Math.round(totalKm).toLocaleString('pt-BR');
    document.getElementById('stat-observed').textContent = observed.toLocaleString('pt-BR');
    document.getElementById('stat-estimated').textContent = (total - observed).toLocaleString('pt-BR');

    // Tab 1: Rede
    _fillStats('stats-rede', [
        { v: total.toLocaleString('pt-BR'), l: 'Segmentos' },
        { v: Math.round(totalKm).toLocaleString('pt-BR') + ' km', l: 'Extensão' },
        { v: nw.nodes.length.toLocaleString('pt-BR'), l: 'Nós' },
        { v: nw.edges.length.toLocaleString('pt-BR'), l: 'Arestas' }
    ]);

    // Tab 2: Contagens
    _fillStats('stats-contagens', [
        { v: observed.toLocaleString('pt-BR'), l: 'Contagens', c: 'success' },
        { v: (observed / total * 100).toFixed(1) + '%', l: 'Cobertura' },
        { v: Math.round(cal.metrics.mean_observed || 0).toLocaleString('pt-BR'), l: 'VMD Médio Obs' },
        { v: total.toLocaleString('pt-BR'), l: 'Total Segmentos' }
    ]);

    // Tab 3: Propagação
    var lastFrame = frames[frames.length - 1];
    _fillStats('stats-propagacao', [
        { v: '28.5%', l: 'Cobertura Inicial' },
        { v: (lastFrame.coverage * 100).toFixed(1) + '%', l: 'Cobertura Final', c: 'success' },
        { v: frames.length, l: 'Iterações' },
        { v: propagated.toLocaleString('pt-BR'), l: 'Seg. Propagados', c: 'accent' }
    ]);

    // Tab 4: Gravitacional
    _fillStats('stats-gravitacional', [
        { v: grav.zones.length, l: 'Zonas (TAZ)' },
        { v: grav.total_od_pairs.toLocaleString('pt-BR'), l: 'Pares OD' },
        { v: grav.desire_lines.length, l: 'Linhas de Desejo' },
        { v: Math.round(grav.desire_lines.reduce(function(a, d) { return a + d.flow; }, 0)).toLocaleString('pt-BR'), l: 'Viagens Top 200' }
    ]);

    // Tab 5: Alocação
    _fillStats('stats-alocacao', [
        { v: observed.toLocaleString('pt-BR'), l: 'Observado', c: 'success' },
        { v: propagated.toLocaleString('pt-BR'), l: 'Propagado', c: 'accent' },
        { v: assigned.toLocaleString('pt-BR'), l: 'Alocado', c: 'warning' },
        { v: estimated.toLocaleString('pt-BR'), l: 'Estimado' }
    ]);

    // Tab 6: Calibração
    var m = cal.metrics;
    _fillStats('stats-calibracao', [
        { v: (m.r2 || 0).toFixed(3), l: 'R²', c: m.r2 >= 0.8 ? 'success' : (m.r2 >= 0.5 ? 'warning' : 'danger') },
        { v: Math.round(m.rmse || 0).toLocaleString('pt-BR'), l: 'RMSE' },
        { v: Math.round(m.mae || 0).toLocaleString('pt-BR'), l: 'MAE' },
        { v: (m.mape || 0).toFixed(1) + '%', l: 'MAPE' },
        { v: (m.geh_pct_under_5 || 0).toFixed(1) + '%', l: 'GEH < 5', c: m.geh_pct_under_5 >= 85 ? 'success' : 'warning' },
        { v: (m.n_observations || 0).toLocaleString('pt-BR'), l: 'Observações' }
    ]);

    // Slider max
    document.getElementById('anim-slider').max = frames.length - 1;
}

function _fillStats(containerId, items) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    items.forEach(function(item) {
        var card = document.createElement('div');
        card.className = 'stat-card';
        card.innerHTML = '<span class="stat-value ' + (item.c || '') + '">' + item.v + '</span><span class="stat-label">' + item.l + '</span>';
        container.appendChild(card);
    });
}

/* === Desire Lines Table === */
function renderDesireLinesTable(desireLines) {
    var container = document.getElementById('desire-lines-table');
    if (!container) return;
    var html = '<table><thead><tr><th>Origem</th><th>Destino</th><th>Fluxo</th></tr></thead><tbody>';
    desireLines.slice(0, 15).forEach(function(dl) {
        html += '<tr><td>#' + dl.origin + '</td><td>#' + dl.dest + '</td><td>' + Math.round(dl.flow).toLocaleString('pt-BR') + '</td></tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

/* === Populate Filters === */
function populateFilters(segments) {
    var regionals = new Set();
    var classes = new Set();
    segments.features.forEach(function(f) {
        if (f.properties.regional) regionals.add(f.properties.regional);
        if (f.properties.classe) classes.add(f.properties.classe);
    });

    var regSelect = document.getElementById('filter-regional');
    Array.from(regionals).sort(function(a, b) { return a - b; }).forEach(function(r) {
        var opt = document.createElement('option');
        opt.value = r; opt.textContent = 'Regional ' + r;
        regSelect.appendChild(opt);
    });

    var clsSelect = document.getElementById('filter-classe');
    Array.from(classes).sort().forEach(function(c) {
        var opt = document.createElement('option');
        opt.value = c; opt.textContent = c;
        clsSelect.appendChild(opt);
    });
}

function getFilterState() {
    return {
        source: (document.getElementById('filter-source') || {}).value || 'all',
        vmdMin: parseFloat((document.getElementById('filter-vmd-min') || {}).value) || 0,
        vmdMax: parseFloat((document.getElementById('filter-vmd-max') || {}).value) || 999999,
        regional: (document.getElementById('filter-regional') || {}).value || 'all',
        classe: (document.getElementById('filter-classe') || {}).value || 'all'
    };
}

/* === Search === */
function debounce(fn, ms) {
    var timer;
    return function() {
        var args = arguments;
        clearTimeout(timer);
        timer = setTimeout(function() { fn.apply(null, args); }, ms);
    };
}

function handleSearch() {
    var query = document.getElementById('search-input').value.trim().toUpperCase();
    var results = document.getElementById('search-results');
    results.innerHTML = '';
    if (!query || query.length < 2 || !window.segmentsData) return;
    var matches = window.segmentsData.features.filter(function(f) {
        var p = f.properties;
        return (p.sre && p.sre.toUpperCase().indexOf(query) >= 0) ||
               (p.go && String(p.go).indexOf(query) >= 0) ||
               (p.regional && String(p.regional) === query);
    }).slice(0, 20);
    matches.forEach(function(f) {
        var p = f.properties;
        var item = document.createElement('div');
        item.className = 'search-result-item';
        item.innerHTML = '<div class="sre-name">' + p.sre + '</div>' +
            '<div class="sre-info">GO: ' + (p.go || '-') + ' | Reg: ' + (p.regional || '-') +
            ' | VMD: ' + Math.round(p.vmd) + ' | ' + (SOURCE_LABELS[p.vmd_source] || p.vmd_source) + '</div>';
        item.addEventListener('click', function() { if (window.zoomToFeature) window.zoomToFeature(f); });
        results.appendChild(item);
    });
    if (matches.length === 0) {
        results.innerHTML = '<div style="color:#64748b;font-size:11px;padding:6px;">Nenhum resultado</div>';
    }
}
