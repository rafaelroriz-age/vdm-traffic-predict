/**
 * Sidebar module - tab switching, search, and filter logic.
 */
function initSidebar() {
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
        });
    });

    // Search
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(handleSearch, 300));
    }
}

function debounce(fn, ms) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

function handleSearch() {
    const query = document.getElementById('search-input').value.trim().toUpperCase();
    const results = document.getElementById('search-results');
    results.innerHTML = '';

    if (!query || query.length < 2 || !window.segmentsData) return;

    const matches = window.segmentsData.features
        .filter(f => {
            const p = f.properties;
            return (p.sre && p.sre.toUpperCase().includes(query)) ||
                   (p.go && String(p.go).includes(query)) ||
                   (p.regional && String(p.regional) === query);
        })
        .slice(0, 20);

    matches.forEach(f => {
        const p = f.properties;
        const item = document.createElement('div');
        item.className = 'search-result-item';
        item.innerHTML = `
            <div class="sre-name">${p.sre}</div>
            <div class="sre-info">GO: ${p.go || '-'} | Regional: ${p.regional || '-'} | VMD: ${Math.round(p.vmd)} | ${p.vmd_source === 'observed' ? 'Observado' : 'Estimado'}</div>
        `;
        item.addEventListener('click', () => {
            if (window.zoomToFeature) window.zoomToFeature(f);
        });
        results.appendChild(item);
    });

    if (matches.length === 0) {
        results.innerHTML = '<div style="color:#64748b;font-size:12px;padding:8px;">Nenhum resultado encontrado</div>';
    }
}

function populateRegionalFilter(segments) {
    const select = document.getElementById('filter-regional');
    if (!select) return;

    const regionals = new Set();
    segments.features.forEach(f => {
        if (f.properties.regional) regionals.add(f.properties.regional);
    });

    [...regionals].sort((a, b) => a - b).forEach(r => {
        const opt = document.createElement('option');
        opt.value = r;
        opt.textContent = `Regional ${r}`;
        select.appendChild(opt);
    });
}

function getFilterState() {
    return {
        source: document.getElementById('filter-source')?.value || 'all',
        vmdMin: parseFloat(document.getElementById('filter-vmd-min')?.value) || 0,
        vmdMax: parseFloat(document.getElementById('filter-vmd-max')?.value) || 999999,
        regional: document.getElementById('filter-regional')?.value || 'all'
    };
}

function featureMatchesFilter(feature, filter) {
    const p = feature.properties;
    if (filter.source !== 'all' && p.vmd_source !== filter.source) return false;
    if (p.vmd < filter.vmdMin || p.vmd > filter.vmdMax) return false;
    if (filter.regional !== 'all' && String(p.regional) !== filter.regional) return false;
    return true;
}
