/**
 * Legend module - VMD color scale configuration.
 */
const VMD_BREAKS = [0, 200, 500, 1000, 3000, 10000, 40000];
const VMD_COLORS = ['#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c', '#800000'];
const VMD_LABELS = ['0 – 200', '200 – 500', '500 – 1.000', '1.000 – 3.000', '3.000 – 10.000', '10.000+'];

const CONFIDENCE_COLORS = {
    'observed': '#94a3b8',
    'high': '#22c55e',
    'medium': '#f59e0b',
    'low': '#ef4444'
};

function getVMDColor(vmd) {
    for (let i = VMD_BREAKS.length - 2; i >= 0; i--) {
        if (vmd >= VMD_BREAKS[i]) return VMD_COLORS[i];
    }
    return VMD_COLORS[0];
}

function getConfidenceColor(conf) {
    return CONFIDENCE_COLORS[conf] || '#64748b';
}

function renderLegend() {
    const container = document.getElementById('legend-items');
    container.innerHTML = '';
    VMD_LABELS.forEach((label, i) => {
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `<div class="legend-color" style="background:${VMD_COLORS[i]}"></div><span>${label}</span>`;
        container.appendChild(item);
    });
}
