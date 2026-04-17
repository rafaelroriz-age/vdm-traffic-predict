/**
 * Charts module — Chart.js visualizations for all 7 tabs.
 */
var chartInstances = {};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';
Chart.defaults.font.family = 'Inter';

function destroyChart(id) {
    if (chartInstances[id]) { chartInstances[id].destroy(); delete chartInstances[id]; }
}

function _barOpts(indexAxis) {
    return {
        responsive: true, plugins: { legend: { display: false } },
        scales: {
            x: { grid: { color: indexAxis === 'y' ? '#1e293b' : false }, ticks: { font: { size: 10 } } },
            y: { grid: { color: indexAxis === 'y' ? false : '#1e293b' }, ticks: { font: { size: 10 } } }
        },
        indexAxis: indexAxis || 'x'
    };
}

/* === Tab 1: Rede === */
function renderClassKmChart(segments) {
    destroyChart('class-km');
    var ctx = document.getElementById('chart-class-km');
    if (!ctx) return;
    var data = {};
    segments.features.forEach(function(f) {
        var c = f.properties.classe || 'Outro';
        data[c] = (data[c] || 0) + (f.properties.extensao || 0);
    });
    var sorted = Object.entries(data).sort(function(a, b) { return b[1] - a[1]; });
    chartInstances['class-km'] = new Chart(ctx, {
        type: 'bar', data: {
            labels: sorted.map(function(d) { return d[0]; }),
            datasets: [{ data: sorted.map(function(d) { return Math.round(d[1]); }),
                backgroundColor: sorted.map(function(d) { return getClassColor(d[0]); }),
                borderRadius: 4, barThickness: 20 }]
        }, options: _barOpts('y')
    });
}

function renderSurfaceChart(segments) {
    destroyChart('surface');
    var ctx = document.getElementById('chart-surface');
    if (!ctx) return;
    var data = {};
    segments.features.forEach(function(f) {
        var r = f.properties.revest || 'N/D';
        data[r] = (data[r] || 0) + 1;
    });
    var keys = Object.keys(data).sort(function(a, b) { return data[b] - data[a]; });
    var colors = ['#3b82f6', '#f59e0b', '#94a3b8', '#22c55e', '#ef4444'];
    chartInstances['surface'] = new Chart(ctx, {
        type: 'doughnut', data: {
            labels: keys, datasets: [{ data: keys.map(function(k) { return data[k]; }),
                backgroundColor: colors.slice(0, keys.length), borderWidth: 0 }]
        }, options: { responsive: true, cutout: '55%', plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 10 } } } } }
    });
}

/* === Tab 2: Contagens === */
function renderCoverageChart(segments) {
    destroyChart('coverage');
    var ctx = document.getElementById('chart-coverage');
    if (!ctx) return;
    var obs = 0, est = 0;
    segments.features.forEach(function(f) {
        if (f.properties.vmd_source === 'observed') obs++; else est++;
    });
    chartInstances['coverage'] = new Chart(ctx, {
        type: 'doughnut', data: {
            labels: ['Observado (' + obs + ')', 'A estimar (' + est + ')'],
            datasets: [{ data: [obs, est], backgroundColor: ['#22c55e', '#334155'], borderWidth: 0 }]
        }, options: { responsive: true, cutout: '60%', plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 11 } } } } }
    });
}

function renderVMDDistribution(segments, canvasId) {
    var id = canvasId || 'vmd-dist';
    destroyChart(id);
    var ctx = document.getElementById('chart-' + id);
    if (!ctx) return;
    var bins = [0, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000];
    var counts = new Array(bins.length).fill(0);
    segments.features.forEach(function(f) {
        var vmd = f.properties.vmd || 0;
        for (var i = bins.length - 1; i >= 0; i--) { if (vmd >= bins[i]) { counts[i]++; break; } }
    });
    var labels = bins.map(function(b, i) { return i < bins.length - 1 ? b + '-' + bins[i + 1] : b + '+'; });
    chartInstances[id] = new Chart(ctx, {
        type: 'bar', data: {
            labels: labels, datasets: [{ data: counts,
                backgroundColor: bins.map(function(b) { return getVMDColor(b); }),
                borderRadius: 3, barThickness: 16 }]
        }, options: _barOpts()
    });
}

function renderVehicleChart(segments) {
    destroyChart('vehicle');
    var ctx = document.getElementById('chart-vehicle');
    if (!ctx) return;
    var tl = 0, th = 0, tm = 0, n = 0;
    segments.features.forEach(function(f) {
        var p = f.properties;
        if (p.pct_light !== undefined && p.pct_light !== null) {
            tl += p.pct_light; th += (p.pct_heavy || 0); tm += (p.pct_moto || 0); n++;
        }
    });
    if (n === 0) return;
    chartInstances['vehicle'] = new Chart(ctx, {
        type: 'doughnut', data: {
            labels: ['Leves', 'Pesados', 'Motos'],
            datasets: [{ data: [(tl / n * 100).toFixed(1), (th / n * 100).toFixed(1), (tm / n * 100).toFixed(1)],
                backgroundColor: ['#3b82f6', '#ef4444', '#f59e0b'], borderWidth: 0 }]
        }, options: { responsive: true, cutout: '55%', plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 11 } } } } }
    });
}

/* === Tab 3: Propagação === */
function renderPropagationChart(frames) {
    destroyChart('propagation');
    var ctx = document.getElementById('chart-propagation');
    if (!ctx) return;
    chartInstances['propagation'] = new Chart(ctx, {
        type: 'line', data: {
            labels: frames.map(function(f) { return f.iteration; }),
            datasets: [{
                label: 'Cobertura %',
                data: frames.map(function(f) { return (f.coverage * 100).toFixed(1); }),
                borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)',
                fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: '#3b82f6'
            }]
        }, options: {
            responsive: true, plugins: { legend: { display: false } },
            scales: {
                x: { title: { display: true, text: 'Iteração', font: { size: 10 } }, grid: { color: '#1e293b' } },
                y: { title: { display: true, text: 'Cobertura %', font: { size: 10 } }, grid: { color: '#1e293b' }, min: 0, max: 100 }
            }
        }
    });
}

/* === Tab 4: Gravitacional === */
function renderZoneTypeChart(zones) {
    destroyChart('zone-type');
    var ctx = document.getElementById('chart-zone-type');
    if (!ctx) return;
    var urban = 0, federal = 0, other = 0;
    zones.forEach(function(z) {
        if (z.is_urban) urban++;
        else if (z.is_federal) federal++;
        else other++;
    });
    chartInstances['zone-type'] = new Chart(ctx, {
        type: 'doughnut', data: {
            labels: ['Urbana (' + urban + ')', 'Federal (' + federal + ')', 'Rural (' + other + ')'],
            datasets: [{ data: [urban, federal, other], backgroundColor: ['#f59e0b', '#ef4444', '#3b82f6'], borderWidth: 0 }]
        }, options: { responsive: true, cutout: '55%', plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 11 } } } } }
    });
}

/* === Tab 5: Alocação === */
function renderVCDistChart(segments) {
    destroyChart('vc-dist');
    var ctx = document.getElementById('chart-vc-dist');
    if (!ctx) return;
    var bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.5, 3.0];
    var counts = new Array(bins.length).fill(0);
    segments.features.forEach(function(f) {
        var vc = f.properties.vc_ratio || 0;
        for (var i = bins.length - 1; i >= 0; i--) { if (vc >= bins[i]) { counts[i]++; break; } }
    });
    var labels = bins.map(function(b, i) { return i < bins.length - 1 ? b.toFixed(1) + '-' + bins[i + 1].toFixed(1) : b.toFixed(1) + '+'; });
    chartInstances['vc-dist'] = new Chart(ctx, {
        type: 'bar', data: {
            labels: labels, datasets: [{ data: counts,
                backgroundColor: bins.map(function(b) { return getVCColor(b); }),
                borderRadius: 3, barThickness: 18 }]
        }, options: _barOpts()
    });
}

function renderSourcePieChart(segments) {
    destroyChart('source-pie');
    var ctx = document.getElementById('chart-source-pie');
    if (!ctx) return;
    var data = {};
    segments.features.forEach(function(f) {
        var s = f.properties.vmd_source || 'estimated';
        data[s] = (data[s] || 0) + 1;
    });
    var keys = ['observed', 'propagated', 'assigned', 'estimated'].filter(function(k) { return data[k]; });
    chartInstances['source-pie'] = new Chart(ctx, {
        type: 'doughnut', data: {
            labels: keys.map(function(k) { return SOURCE_LABELS[k] + ' (' + data[k] + ')'; }),
            datasets: [{ data: keys.map(function(k) { return data[k]; }),
                backgroundColor: keys.map(function(k) { return SOURCE_COLORS[k]; }), borderWidth: 0 }]
        }, options: { responsive: true, cutout: '55%', plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 10 } } } } }
    });
}

/* === Tab 6: Calibração === */
function renderScatterChart(scatterData) {
    destroyChart('scatter');
    var ctx = document.getElementById('chart-scatter');
    if (!ctx || !scatterData || scatterData.length === 0) return;
    var maxVal = Math.max.apply(null, scatterData.map(function(d) { return Math.max(d.observed, d.estimated); }));
    chartInstances['scatter'] = new Chart(ctx, {
        type: 'scatter', data: {
            datasets: [{
                label: 'Obs vs Est',
                data: scatterData.map(function(d) { return { x: d.observed, y: d.estimated }; }),
                backgroundColor: scatterData.map(function(d) { return getGEHColor(d.geh); }),
                pointRadius: 3
            }, {
                label: 'y = x',
                data: [{ x: 0, y: 0 }, { x: maxVal, y: maxVal }],
                type: 'line', borderColor: 'rgba(255,255,255,0.3)', borderDash: [5, 5],
                pointRadius: 0, borderWidth: 1
            }]
        }, options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { title: { display: true, text: 'Observado', font: { size: 10 } }, grid: { color: '#1e293b' } },
                y: { title: { display: true, text: 'Estimado', font: { size: 10 } }, grid: { color: '#1e293b' } }
            }
        }
    });
}

function renderGEHChart(scatterData) {
    destroyChart('geh');
    var ctx = document.getElementById('chart-geh');
    if (!ctx || !scatterData) return;
    var bins = [0, 1, 2, 3, 5, 7, 10, 15, 20];
    var counts = new Array(bins.length).fill(0);
    scatterData.forEach(function(d) {
        for (var i = bins.length - 1; i >= 0; i--) { if (d.geh >= bins[i]) { counts[i]++; break; } }
    });
    var labels = bins.map(function(b, i) { return i < bins.length - 1 ? b + '-' + bins[i + 1] : b + '+'; });
    chartInstances['geh'] = new Chart(ctx, {
        type: 'bar', data: {
            labels: labels, datasets: [{ data: counts,
                backgroundColor: bins.map(function(b) { return getGEHColor(b); }),
                borderRadius: 3, barThickness: 18 }]
        }, options: _barOpts()
    });
}

/* === Tab 7: Resultado === */
function renderRegionalChart(segments) {
    destroyChart('regional');
    var ctx = document.getElementById('chart-regional');
    if (!ctx) return;
    var regData = {};
    segments.features.forEach(function(f) {
        var reg = f.properties.regional;
        if (!reg) return;
        if (!regData[reg]) regData[reg] = [];
        regData[reg].push(f.properties.vmd || 0);
    });
    var sorted = Object.entries(regData)
        .map(function(e) { var vmds = e[1]; return { reg: e[0], mean: vmds.reduce(function(a, b) { return a + b; }, 0) / vmds.length }; })
        .sort(function(a, b) { return b.mean - a.mean; });
    chartInstances['regional'] = new Chart(ctx, {
        type: 'bar', data: {
            labels: sorted.map(function(d) { return 'R' + d.reg; }),
            datasets: [{ data: sorted.map(function(d) { return Math.round(d.mean); }),
                backgroundColor: sorted.map(function(d) { return getVMDColor(d.mean); }),
                borderRadius: 3, barThickness: 12 }]
        }, options: _barOpts('y')
    });
}
