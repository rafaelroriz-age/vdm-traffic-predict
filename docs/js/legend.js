/**
 * Legend module — color scales for each tab view.
 */
var VMD_BREAKS = [0, 200, 500, 1000, 3000, 10000, 40000];
var VMD_COLORS = ['#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c', '#800000'];

var CLASS_COLORS = {
    'Radiais': '#e74c3c',
    'Longitudinais': '#3498db',
    'Transversais': '#2ecc71',
    'Diagonais': '#f39c12',
    'Ligações': '#9b59b6'
};

var SOURCE_COLORS = {
    'observed': '#22c55e',
    'propagated': '#3b82f6',
    'assigned': '#f59e0b',
    'estimated': '#94a3b8'
};

var SOURCE_LABELS = {
    'observed': 'Observado',
    'propagated': 'Propagado',
    'assigned': 'Alocado',
    'estimated': 'Estimado'
};

var VC_BREAKS = [0, 0.3, 0.6, 0.8, 1.0, 1.5];
var VC_COLORS = ['#22c55e', '#84cc16', '#f59e0b', '#ef4444', '#7f1d1d'];
var VC_LABELS = ['0 – 0.3', '0.3 – 0.6', '0.6 – 0.8', '0.8 – 1.0', '> 1.0'];

var GEH_BREAKS = [0, 5, 10, 20];
var GEH_COLORS = ['#22c55e', '#f59e0b', '#ef4444'];

function getVMDColor(vmd) {
    for (var i = VMD_BREAKS.length - 2; i >= 0; i--) {
        if (vmd >= VMD_BREAKS[i]) return VMD_COLORS[i];
    }
    return VMD_COLORS[0];
}

function getClassColor(classe) {
    return CLASS_COLORS[classe] || '#64748b';
}

function getSourceColor(source) {
    return SOURCE_COLORS[source] || '#64748b';
}

function getVCColor(vc) {
    for (var i = VC_BREAKS.length - 2; i >= 0; i--) {
        if (vc >= VC_BREAKS[i]) return VC_COLORS[i];
    }
    return VC_COLORS[0];
}

function getGEHColor(geh) {
    if (geh < 5) return GEH_COLORS[0];
    if (geh < 10) return GEH_COLORS[1];
    return GEH_COLORS[2];
}

function renderLegend(type) {
    var container = document.getElementById('legend-items');
    var title = document.getElementById('legend-title');
    container.innerHTML = '';

    if (type === 'classe') {
        title.textContent = 'Classe da Rodovia';
        Object.entries(CLASS_COLORS).forEach(function(e) {
            _addLegendLine(container, e[1], e[0]);
        });
    } else if (type === 'vmd') {
        title.textContent = 'VMD (veíc/dia)';
        ['0 – 200','200 – 500','500 – 1.000','1.000 – 3.000','3.000 – 10.000','10.000+'].forEach(function(label, i) {
            _addLegendLine(container, VMD_COLORS[i], label);
        });
    } else if (type === 'source') {
        title.textContent = 'Fonte do VMD';
        Object.entries(SOURCE_COLORS).forEach(function(e) {
            _addLegendLine(container, e[1], SOURCE_LABELS[e[0]]);
        });
    } else if (type === 'vc') {
        title.textContent = 'V/C Ratio';
        VC_LABELS.forEach(function(label, i) {
            _addLegendLine(container, VC_COLORS[i], label);
        });
    } else if (type === 'geh') {
        title.textContent = 'GEH Statistic';
        [['< 5 (Bom)', '#22c55e'], ['5 – 10 (Aceitável)', '#f59e0b'], ['> 10 (Ruim)', '#ef4444']].forEach(function(e) {
            _addLegendLine(container, e[1], e[0]);
        });
    } else if (type === 'gravity') {
        title.textContent = 'Modelo Gravitacional';
        _addLegendCircle(container, '#f59e0b', 'Zona (TAZ)');
        _addLegendLine(container, 'rgba(239,68,68,0.5)', 'Linha de desejo');
    } else if (type === 'count') {
        title.textContent = 'Contagens';
        _addLegendCircle(container, '#22c55e', 'Posto de contagem');
        _addLegendLine(container, 'rgba(34,197,94,0.6)', 'Segmento observado');
        _addLegendLine(container, 'rgba(100,116,139,0.3)', 'Sem contagem');
    }
}

function _addLegendLine(container, color, label) {
    var item = document.createElement('div');
    item.className = 'legend-item';
    item.innerHTML = '<div class="legend-color" style="background:' + color + '"></div><span>' + label + '</span>';
    container.appendChild(item);
}

function _addLegendCircle(container, color, label) {
    var item = document.createElement('div');
    item.className = 'legend-item';
    item.innerHTML = '<div class="legend-circle" style="background:' + color + '"></div><span>' + label + '</span>';
    container.appendChild(item);
}
