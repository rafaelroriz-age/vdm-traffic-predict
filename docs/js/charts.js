/**
 * Charts module - Chart.js visualizations for sidebar panels.
 */
let chartInstances = {};

function destroyChart(id) {
    if (chartInstances[id]) {
        chartInstances[id].destroy();
        delete chartInstances[id];
    }
}

const CHART_DEFAULTS = {
    color: '#94a3b8',
    borderColor: '#334155',
    font: { family: 'Inter' }
};

Chart.defaults.color = CHART_DEFAULTS.color;
Chart.defaults.borderColor = CHART_DEFAULTS.borderColor;
Chart.defaults.font.family = CHART_DEFAULTS.font.family;

function renderVMDDistribution(segments) {
    destroyChart('vmd-dist');
    const ctx = document.getElementById('chart-vmd-dist');
    if (!ctx) return;

    const bins = [0, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000];
    const counts = new Array(bins.length).fill(0);

    segments.features.forEach(f => {
        const vmd = f.properties.vmd || 0;
        for (let i = bins.length - 1; i >= 0; i--) {
            if (vmd >= bins[i]) { counts[i]++; break; }
        }
    });

    const labels = bins.map((b, i) => i < bins.length - 1 ? `${b}-${bins[i+1]}` : `${b}+`);

    chartInstances['vmd-dist'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: bins.map(b => getVMDColor(b)),
                borderRadius: 4,
                barThickness: 20
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 9 }, maxRotation: 45 } },
                y: { grid: { color: '#1e293b' }, ticks: { font: { size: 10 } } }
            }
        }
    });
}

function renderRegionalChart(segments) {
    destroyChart('regional');
    const ctx = document.getElementById('chart-regional');
    if (!ctx) return;

    const regData = {};
    segments.features.forEach(f => {
        const reg = f.properties.regional;
        if (!reg) return;
        if (!regData[reg]) regData[reg] = [];
        regData[reg].push(f.properties.vmd || 0);
    });

    const sorted = Object.entries(regData)
        .map(([reg, vmds]) => ({ reg, mean: vmds.reduce((a, b) => a + b, 0) / vmds.length }))
        .sort((a, b) => b.mean - a.mean);

    chartInstances['regional'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sorted.map(d => `R${d.reg}`),
            datasets: [{
                data: sorted.map(d => Math.round(d.mean)),
                backgroundColor: sorted.map(d => getVMDColor(d.mean)),
                borderRadius: 4,
                barThickness: 14
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: '#1e293b' }, ticks: { font: { size: 10 } } },
                y: { grid: { display: false }, ticks: { font: { size: 10 } } }
            }
        }
    });
}

function renderVehicleChart(segments) {
    destroyChart('vehicle');
    const ctx = document.getElementById('chart-vehicle');
    if (!ctx) return;

    let totalLight = 0, totalHeavy = 0, totalMoto = 0, count = 0;
    segments.features.forEach(f => {
        const p = f.properties;
        if (p.pct_light !== undefined) {
            totalLight += p.pct_light;
            totalHeavy += p.pct_heavy || 0;
            totalMoto += p.pct_moto || 0;
            count++;
        }
    });

    if (count === 0) return;

    chartInstances['vehicle'] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Leves', 'Pesados', 'Motos'],
            datasets: [{
                data: [
                    (totalLight / count * 100).toFixed(1),
                    (totalHeavy / count * 100).toFixed(1),
                    (totalMoto / count * 100).toFixed(1)
                ],
                backgroundColor: ['#3b82f6', '#ef4444', '#f59e0b'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            cutout: '60%',
            plugins: {
                legend: { position: 'bottom', labels: { padding: 16, font: { size: 12 } } }
            }
        }
    });
}

function renderModelR2Chart(metrics) {
    destroyChart('models-r2');
    const ctx = document.getElementById('chart-models-r2');
    if (!ctx) return;

    const models = Object.entries(metrics)
        .filter(([k, v]) => k !== 'feature_importance' && k !== 'Ensemble' && v.r2)
        .map(([name, m]) => ({ name, r2: m.r2.mean }))
        .sort((a, b) => b.r2 - a.r2);

    chartInstances['models-r2'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: models.map(m => m.name),
            datasets: [{
                label: 'R2',
                data: models.map(m => m.r2),
                backgroundColor: models.map(m => m.r2 > 0 ? '#3b82f6' : '#ef4444'),
                borderRadius: 4,
                barThickness: 30
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false } },
                y: { grid: { color: '#1e293b' }, title: { display: true, text: 'R2', font: { size: 11 } } }
            }
        }
    });
}

function renderModelRMSEChart(metrics) {
    destroyChart('models-rmse');
    const ctx = document.getElementById('chart-models-rmse');
    if (!ctx) return;

    const models = Object.entries(metrics)
        .filter(([k, v]) => k !== 'feature_importance' && k !== 'Ensemble' && v.rmse)
        .map(([name, m]) => ({ name, rmse: m.rmse.mean }))
        .sort((a, b) => a.rmse - b.rmse);

    chartInstances['models-rmse'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: models.map(m => m.name),
            datasets: [{
                label: 'RMSE',
                data: models.map(m => Math.round(m.rmse)),
                backgroundColor: '#f59e0b',
                borderRadius: 4,
                barThickness: 30
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false } },
                y: { grid: { color: '#1e293b' }, title: { display: true, text: 'RMSE', font: { size: 11 } } }
            }
        }
    });
}

function renderFeatureImportance(metrics) {
    destroyChart('features');
    const ctx = document.getElementById('chart-features');
    if (!ctx || !metrics.feature_importance) return;

    const features = Object.entries(metrics.feature_importance)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 12);

    chartInstances['features'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: features.map(f => f[0].replace(/_/g, ' ')),
            datasets: [{
                data: features.map(f => f[1]),
                backgroundColor: '#22c55e',
                borderRadius: 4,
                barThickness: 14
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: '#1e293b' }, ticks: { font: { size: 10 } } },
                y: { grid: { display: false }, ticks: { font: { size: 10 } } }
            }
        }
    });
}

function updateModelDetails(metrics) {
    const models = Object.entries(metrics)
        .filter(([k, v]) => k !== 'feature_importance' && k !== 'Ensemble' && v.r2 && v.r2.mean !== undefined)
        .sort((a, b) => b[1].r2.mean - a[1].r2.mean);

    if (models.length === 0) return;

    const [name, m] = models[0];
    document.getElementById('best-model-name').textContent = name;
    document.getElementById('best-r2').textContent = m.r2.mean.toFixed(3);
    document.getElementById('best-rmse').textContent = Math.round(m.rmse.mean);
    document.getElementById('best-mae').textContent = Math.round(m.mae.mean);
    document.getElementById('best-mape').textContent = m.mape.mean.toFixed(1);
}
