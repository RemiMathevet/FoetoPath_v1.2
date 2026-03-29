async function renderMacroscopiePanel(c) {
    const el = document.getElementById('panel-macroscopie');
    el.innerHTML = '<div class="loading-inline"><div class="spinner"></div> Chargement macroscopie...</div>';

    const modules = c.modules || {};
    const mFrais = modules.macro_frais?.data || null;
    const mAutopsie = modules.macro_autopsie?.data || null;
    const mFixe = modules.macro_fixe?.data || null;
    const mNeuro = modules.neuropath?.data || null;

    // Load pairing data in parallel
    let pairingData = null;
    try {
        pairingData = await api('/api/cases/' + c.id + '/pairing');
    } catch(e) {}

    // Load photos list
    let photosData = null;
    try {
        photosData = await fetch('/admin/api/photos/list', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ case_id: c.id })
        }).then(r => r.json());
    } catch(e) {}

    const categories = photosData?.categories || {};
    const folders = c.macro_folders || [];

    // ── Summary bar ──
    // Mapping des catégories API photos → types d'affichage
    // L'API photos/list retourne des catégories : externe, extra_externe, autopsie, fixe, fixe_lesion, neuropath, anomalie, autre
    // On fusionne pour l'affichage en 5 cartes
    const types = ['photos', 'frais', 'autopsie', 'fixe', 'neuropath'];
    const typeIcons = { photos: '&#128247;', frais: '&#129516;', autopsie: '&#128300;', fixe: '&#129514;', neuropath: '&#129504;' };
    const typeLabels = { photos: 'Photos', frais: 'Frais', autopsie: 'Autopsie', fixe: 'Fixé', neuropath: 'Neuropath' };

    // Calculer les comptes depuis les catégories de l'API photos (source fiable)
    // plutôt que depuis les sous-dossiers physiques (souvent inexistants)
    function countCatPhotos(catKeys) {
        return catKeys.reduce((sum, k) => sum + (categories[k]?.photos?.length || 0), 0);
    }
    const catCounts = {
        photos: Object.values(categories).reduce((sum, cat) => sum + (cat.photos?.length || 0), 0),
        frais: countCatPhotos(['externe', 'extra_externe', 'anomalie']),
        autopsie: countCatPhotos(['autopsie', 'extra_autopsie']),
        fixe: countCatPhotos(['fixe', 'fixe_lesion', 'extra_fixe']),
        neuropath: countCatPhotos(['neuropath', 'extra_neuropath']),
    };

    let html = `
    <div class="card" style="padding:14px 18px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap">
            <span style="font-size:13px;font-weight:600">Dossiers</span>
            <code style="color:var(--accent);font-family:var(--mono);font-size:11px">${c.dossier_macro_path || 'Non défini'}</code>
            <div style="margin-left:auto;display:flex;gap:8px">
                <button class="btn btn-sm" onclick="scanMacro(${c.id})">Re-scanner</button>
                ${c.dossier_macro_path ? '<button class="btn btn-sm" onclick="openViewerPhotos('+c.id+')">Viewer photos</button>' : ''}
                ${c.dossier_lames_path ? '<button class="btn btn-sm" onclick="openViewerLames(state.currentCase.dossier_lames_path)">Viewer lames</button>' : ''}
            </div>
        </div>
        <div class="macro-grid">
            ${types.map(t => {
                // Priorité : données catégorisées de l'API, fallback sur les dossiers physiques
                const apiCount = catCounts[t] || 0;
                const f = folders.find(x => x.folder_type === t);
                const folderCount = f ? f.photo_count : 0;
                const count = apiCount || folderCount;
                const exists = count > 0 || (f && f.folder_path);
                return '<div class="macro-card ' + (exists ? 'exists' : 'missing') + '"><div class="macro-card-icon">' + typeIcons[t] + '</div><div class="macro-card-label">' + typeLabels[t] + '</div><div class="macro-card-count">' + (count > 0 ? count + ' photo(s)' : exists ? '0 photo(s)' : 'Absent') + '</div></div>';
            }).join('')}
        </div>
    </div>`;

    // ── Pairing summary ──
    if (pairingData && pairingData.stats) {
        const s = pairingData.stats;
        const match = s.cassettes_vs_lames_ok;
        const matchCls = match === true ? 'pairing-stat-ok' : match === false ? 'pairing-stat-err' : 'pairing-stat-warn';
        html += `
        <div class="pairing-stats" style="margin-bottom:16px">
            <div class="pairing-stat"><div class="pairing-stat-value">${s.photos_frais}</div><div class="pairing-stat-label">Frais</div></div>
            <div class="pairing-stat"><div class="pairing-stat-value">${s.photos_autopsie}</div><div class="pairing-stat-label">Autopsie</div></div>
            <div class="pairing-stat"><div class="pairing-stat-value">${s.photos_fixe}</div><div class="pairing-stat-label">Fixé</div></div>
            <div class="pairing-stat"><div class="pairing-stat-value">${s.photos_neuropath}</div><div class="pairing-stat-label">Neuropath</div></div>
            <div class="pairing-stat"><div class="pairing-stat-value">${s.slides}</div><div class="pairing-stat-label">Lames</div></div>
            <div class="pairing-stat ${matchCls}"><div class="pairing-stat-value">${match === true ? '&#10003;' : match === false ? '&#10007;' : '?'}</div><div class="pairing-stat-label">K7 = Lames</div></div>
        </div>`;
    }

    // Helper: merge photos from main + extra + anomalies for a context
    function mergePhotos(cat) {
        const main = cat ? (cat.photos || []) : [];
        return main;
    }
    function mergeCatPhotos(mainKey, extraKey) {
        const main = categories[mainKey]?.photos || [];
        const extra = categories[extraKey]?.photos || [];
        const anomalies = (mainKey === 'externe') ? (categories.anomalie?.photos || []) : [];
        return [...main, ...extra, ...anomalies];
    }

    // ── Section: Examen externe (macro_frais) ──
    const externePhotos = mergeCatPhotos('externe', 'extra_externe');
    html += buildMacroSection('externe', '&#129516;', 'Examen externe (frais)', mFrais, {photos: externePhotos}, function() {
        if (!mFrais) return '';
        let s = '';
        // Biométries
        const bio = mFrais.biometries || mFrais.biometrie || {};
        if (Object.keys(bio).length) {
            s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:8px 0 4px">Biométries</div>';
            s += '<div class="macro-data-grid">';
            for (const [k, v] of Object.entries(bio)) {
                if (v !== null && v !== undefined && v !== '') s += '<div class="data-item"><span class="data-label">' + (BIO_LABELS[k] || k) + '</span><span class="data-value">' + v + '</span></div>';
            }
            s += '</div>';
        }
        // Macération + Sexe + État
        const meta = [];
        if (mFrais.maceration !== undefined) meta.push(['Macération', mFrais.maceration]);
        if (mFrais.sexe) meta.push(['Sexe', mFrais.sexe === 'M' ? 'Masculin' : mFrais.sexe === 'F' ? 'Féminin' : mFrais.sexe]);
        if (mFrais.etat) meta.push(['État', mFrais.etat]);
        if (mFrais.aspect_general) meta.push(['Aspect général', mFrais.aspect_general]);
        if (meta.length) {
            s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">Informations générales</div>';
            s += '<div class="macro-data-grid">';
            meta.forEach(([lab, val]) => { s += '<div class="data-item"><span class="data-label">' + lab + '</span><span class="data-value">' + val + '</span></div>'; });
            s += '</div>';
        }
        // Morphologie
        const morpho = mFrais.morphologie || mFrais.examen_externe || {};
        if (Object.keys(morpho).length) {
            s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">Morphologie externe</div>';
            s += '<div class="macro-data-grid">';
            for (const [k, v] of Object.entries(morpho)) {
                if (v !== null && v !== undefined) {
                    const val = typeof v === 'object' ? JSON.stringify(v) : v;
                    s += '<div class="data-item"><span class="data-label">' + k + '</span><span class="data-value">' + val + '</span></div>';
                }
            }
            s += '</div>';
        }
        return s;
    });

    // ── Section: Autopsie ──
    const autopsiePhotos = mergeCatPhotos('autopsie', 'extra_autopsie');
    html += buildMacroSection('autopsie', '&#128300;', 'Autopsie', mAutopsie, {photos: autopsiePhotos}, function() {
        if (!mAutopsie) return '';
        let s = '';
        for (const [key, val] of Object.entries(mAutopsie)) {
            if (val === null || val === undefined) continue;
            if (key === 'coeur' && typeof val === 'object') {
                s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">&#10084; Cœur</div>';
                s += '<div class="macro-data-grid">';
                for (const [sk, sv] of Object.entries(val)) {
                    if (typeof sv === 'object' && sv !== null) {
                        for (const [ssk, ssv] of Object.entries(sv)) {
                            s += '<div class="data-item"><span class="data-label">' + (CARDIAC_LABELS[sk]||sk) + ' › ' + ssk + '</span><span class="data-value">' + ssv + '</span></div>';
                        }
                    } else {
                        s += '<div class="data-item"><span class="data-label">' + (CARDIAC_LABELS[sk]||sk) + '</span><span class="data-value">' + sv + (sk === 'masse' ? ' g' : '') + '</span></div>';
                    }
                }
                s += '</div>';
            } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
                const label = ORGAN_LABELS[key] || key;
                s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">' + label + '</div>';
                s += '<div class="macro-data-grid">';
                for (const [sk, sv] of Object.entries(val)) {
                    if (sv !== null && sv !== undefined) {
                        const d = typeof sv === 'object' ? JSON.stringify(sv) : sv;
                        s += '<div class="data-item"><span class="data-label">' + sk + '</span><span class="data-value">' + d + (sk === 'masse' || sk === 'poids' ? ' g' : '') + '</span></div>';
                    }
                }
                s += '</div>';
            } else if (!Array.isArray(val)) {
                s += '<div class="macro-data-grid"><div class="data-item"><span class="data-label">' + (ORGAN_LABELS[key]||key) + '</span><span class="data-value">' + val + '</span></div></div>';
            }
        }
        return s;
    });

    // ── Section: Fixé ──
    const fixePhotos = [...(categories.fixe?.photos || []), ...(categories.fixe_lesion?.photos || []), ...(categories.extra_fixe?.photos || [])];
    html += buildMacroSection('fixe', '&#129514;', 'Macro fixé (tranches de section)', mFixe, {photos: fixePhotos}, function() {
        if (!mFixe) return '';
        let s = '';
        const organes = mFixe.organes || {};
        for (const [orgId, od] of Object.entries(organes)) {
            const items = [];
            if (od.masse_fixee) items.push(['Masse fixée', od.masse_fixee + ' g']);
            if (od.cassettes) items.push(['Cassettes', od.cassettes]);
            if (od.lesion_desc) items.push(['Lésion', od.lesion_desc]);
            if (od.lesion_k7) items.push(['K7 lésion', od.lesion_k7]);
            if (items.length) {
                s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">' + (ORGAN_LABELS[orgId] || orgId) + '</div>';
                s += '<div class="macro-data-grid">';
                items.forEach(([lab, val]) => { s += '<div class="data-item"><span class="data-label">' + lab + '</span><span class="data-value">' + val + '</span></div>'; });
                s += '</div>';
            }
        }
        // Toggles
        const toggles = mFixe.toggles || {};
        const activeToggles = Object.entries(toggles).filter(([k, v]) => v !== null);
        if (activeToggles.length) {
            s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">Toggles</div>';
            s += '<div class="macro-data-grid">';
            activeToggles.forEach(([k, v]) => {
                s += '<div class="data-item"><span class="data-label">' + k + '</span><span class="data-value">' + (v ? 'Oui' : 'Non') + '</span></div>';
            });
            s += '</div>';
        }
        if (mFixe.commentaire) {
            s += '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">Commentaire</div>';
            s += '<div style="font-size:12px;color:var(--text);padding:8px;background:var(--bg3);border-radius:var(--radius)">' + escHtml(mFixe.commentaire) + '</div>';
        }
        return s;
    });

    // ── Section: Neuropath ──
    const neuroPhotos = mergeCatPhotos('neuropath', 'extra_neuropath');
    html += buildMacroSection('neuropath', '&#129504;', 'Neuropathologie', mNeuro, {photos: neuroPhotos}, function() {
        if (!mNeuro) return '';
        return renderGenericModule(mNeuro);
    });

    // ── Section: Appairage détaillé ──
    if (pairingData && pairingData.pairing && pairingData.pairing.length) {
        html += `
        <div class="macro-section" id="msec-pairing">
            <div class="macro-section-header" onclick="toggleMacroSection('msec-pairing')">
                <span class="macro-section-icon">&#128279;</span>
                <span class="macro-section-title">Appairage organes / photos / lames</span>
                <span class="macro-section-badge has-data">${pairingData.pairing.length} organes</span>
                <span class="macro-section-chevron">&#9660;</span>
            </div>
            <div class="macro-section-body">
                ${renderPairingTable(pairingData)}
            </div>
        </div>`;
    }

    el.innerHTML = html;
}

// Store photo arrays for lightbox access
const _sectionPhotos = {};

function buildMacroSection(id, icon, title, moduleData, photosCat, dataRendererFn) {
    const hasData = !!moduleData;
    const photos = photosCat?.photos || [];
    const badgeTxt = hasData ? (photos.length ? photos.length + ' photo(s)' : 'Données') : 'Vide';
    const badgeCls = hasData ? 'has-data' : 'no-data';

    // Store photos for lightbox
    _sectionPhotos[id] = photos.map(p => ({
        thumb: '/admin/api/photo/thumbnail?path=' + encodeURIComponent(p.path) + '&w=280&h=280',
        full: '/admin/api/photo/serve?path=' + encodeURIComponent(p.path),
        label: p.label || p.filename,
    }));

    let body = '';

    // Photos grid — click opens lightbox
    if (photos.length) {
        body += '<div class="macro-photo-grid">';
        photos.forEach((p, i) => {
            const thumbUrl = '/admin/api/photo/thumbnail?path=' + encodeURIComponent(p.path) + '&w=280&h=280';
            body += '<div class="macro-photo-item" onclick="openLightbox(_sectionPhotos[\'' + id + '\'],' + i + ')" title="' + escHtml(p.label || p.filename) + '"><img src="' + thumbUrl + '" loading="lazy"><div class="photo-label">' + escHtml(p.label || p.filename) + '</div></div>';
        });
        body += '</div>';
    }

    // Data — collapsible
    if (hasData && typeof dataRendererFn === 'function') {
        const dataHtml = dataRendererFn();
        if (dataHtml) {
            const dtId = 'dt-' + id;
            body += '<div class="data-toggle" onclick="toggleDataBlock(\'' + dtId + '\', this)"><span class="dt-chevron">&#9660;</span> Données du module</div>';
            body += '<div class="data-collapsible" id="' + dtId + '">' + dataHtml + '</div>';
        }
    }

    if (!body) {
        body = '<div style="color:var(--text3);font-size:13px;padding:8px 0">Aucune donnée pour cette section.</div>';
    }

    return `
    <div class="macro-section${hasData ? ' open' : ''}" id="msec-${id}">
        <div class="macro-section-header" onclick="toggleMacroSection('msec-${id}')">
            <span class="macro-section-icon">${icon}</span>
            <span class="macro-section-title">${title}</span>
            <span class="macro-section-badge ${badgeCls}">${badgeTxt}</span>
            <span class="macro-section-chevron">&#9660;</span>
        </div>
        <div class="macro-section-body">${body}</div>
    </div>`;
}

function toggleDataBlock(id, btn) {
    const el = document.getElementById(id);
    if (el) { el.classList.toggle('open'); btn.classList.toggle('open'); }
}

function toggleMacroSection(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('open');
}

function renderPairingTable(data) {
    let html = `
        <table class="pairing-table">
            <thead><tr>
                <th style="width:90px">Organe</th>
                <th>Photos frais</th>
                <th>Photos fixé</th>
                <th>Lames</th>
                <th style="width:80px">Actions</th>
            </tr></thead><tbody>`;

    for (const row of data.pairing) {
        html += '<tr>';
        html += '<td><span class="organ-badge">' + row.organ_id + '</span></td>';
        html += '<td><div class="pairing-thumb-group">' + (row.photos_frais.map(p => '<img class="pairing-thumb" src="/admin/api/photo/thumbnail?path=' + encodeURIComponent(p.path) + '&w=120&h=120" title="' + p.filename + '" onclick="window.open(\'/admin/api/photo/serve?path=' + encodeURIComponent(p.path) + '\',\'_blank\')">').join('') || '<span style="color:var(--text3);font-size:12px">—</span>') + '</div></td>';
        html += '<td><div class="pairing-thumb-group">' + (row.photos_fixe.map(p => '<img class="pairing-thumb" src="/admin/api/photo/thumbnail?path=' + encodeURIComponent(p.path) + '&w=120&h=120" title="' + p.filename + '" onclick="window.open(\'/admin/api/photo/serve?path=' + encodeURIComponent(p.path) + '\',\'_blank\')">').join('') || '<span style="color:var(--text3);font-size:12px">—</span>') + '</div></td>';
        html += '<td>' + (row.slides.map(sl => '<div class="slide-badge" title="' + sl.path + '"><img src="/api/slide/thumbnail?path=' + encodeURIComponent(sl.path) + '&w=50&h=50" style="width:40px;height:40px;border-radius:3px;object-fit:cover" onerror="this.style.display=\'none\'">' + sl.name + '</div>').join('') || '<span style="color:var(--text3);font-size:12px">—</span>') + '</td>';
        html += '<td>' + (row.slides.length ? '<button class="btn btn-sm" onclick="openViewerLames(\'' + escPath(data.paths.lames||'') + '\',\'' + escPath(row.slides[0].path) + '\')">Voir</button>' : '') + '</td>';
        html += '</tr>';
    }

    html += '</tbody></table>';
    return html;
}

// ── Microscopie Panel ─────────────────────────

async function renderMicroscopiePanel(c) {
    const el = document.getElementById('panel-microscopie');

    // Load available micro templates
    let templates = [];
    try {
        const res = await api('/api/micro/templates');
        templates = res.templates || [];
    } catch(e) {}

    // Load pairing for slides info (includes photos fixé + lames)
    let pairingData = null;
    try {
        pairingData = await api('/api/cases/' + c.id + '/pairing');
    } catch(e) {}

    const slideCount = pairingData?.stats?.slides || 0;
    const lamePath = pairingData?.paths?.lames || c.dossier_lames_path || '';
    const pairingRows = pairingData?.pairing || [];

    // Collecter toutes les lames individuelles avec leur mapping cassette
    const allSlides = [];
    pairingRows.forEach(row => {
        (row.slides || []).forEach(sl => {
            // Convention de nommage : numero_dossier_cassette_coupe
            // Extraire le numéro de cassette depuis le nom de fichier
            const parts = sl.name.split('_');
            const cassette = parts.length >= 2 ? parts[parts.length - 2] : '';
            const coupe = parts.length >= 3 ? parts[parts.length - 1] : '';
            allSlides.push({
                ...sl,
                organ_id: row.organ_id,
                cassette: cassette,
                coupe: coupe,
                photos_fixe: row.photos_fixe || [],
            });
        });
    });

    let html = `
    <div class="card">
        <div class="card-title"><span class="icon">&#128300;</span> Microscopie — Lames & Grilles</div>
        <div style="font-size:12px;color:var(--text2);margin-bottom:16px">
            ${slideCount} lame(s) détectée(s)
            ${lamePath ? '— <code style="font-family:var(--mono);color:var(--accent);font-size:11px">' + escHtml(lamePath) + '</code>' : '— <span style="color:var(--warning)">Aucun chemin de lames configuré</span>'}
        </div>`;

    // ── Galerie de lames avec previews ──
    if (allSlides.length) {
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-bottom:20px">';
        allSlides.forEach(sl => {
            const thumbUrl = '/api/slide/thumbnail?path=' + encodeURIComponent(sl.path) + '&w=300&h=200';
            const hasFixePhoto = sl.photos_fixe.length > 0;
            const fixeThumbUrl = hasFixePhoto
                ? '/api/photo/thumbnail?path=' + encodeURIComponent(sl.photos_fixe[0].path) + '&w=120&h=120'
                : '';

            html += `
            <div class="micro-slide-card" style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;cursor:pointer;transition:all 0.2s"
                 onmouseenter="this.style.borderColor='var(--accent)';this.style.transform='translateY(-2px)'"
                 onmouseleave="this.style.borderColor='var(--border)';this.style.transform='none'">
                <div style="position:relative;width:100%;height:160px;background:#111;display:flex;align-items:center;justify-content:center"
                     onclick="openViewerLames('${escPath(lamePath)}','${escPath(sl.path)}')">
                    <img src="${thumbUrl}" alt="${escHtml(sl.name)}"
                         style="max-width:100%;max-height:100%;object-fit:contain"
                         onerror="this.style.display='none';this.parentElement.innerHTML+='<div style=\\'color:var(--text2);font-size:12px\\'>Aperçu non disponible</div>'">
                    <div style="position:absolute;top:8px;right:8px;background:rgba(0,0,0,0.7);border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;cursor:pointer"
                         title="Ouvrir dans le viewer"
                         onclick="event.stopPropagation();openViewerLames('${escPath(lamePath)}','${escPath(sl.path)}')">
                        <svg viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2" width="16" height="16">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                        </svg>
                    </div>
                    ${hasFixePhoto ? `
                    <div style="position:absolute;bottom:8px;left:8px;width:56px;height:56px;border-radius:8px;overflow:hidden;border:2px solid var(--accent);background:#111"
                         title="Photo macro fixé correspondante">
                        <img src="${fixeThumbUrl}" style="width:100%;height:100%;object-fit:cover"
                             onerror="this.parentElement.style.display='none'">
                    </div>` : ''}
                </div>
                <div style="padding:10px 12px">
                    <div style="font-size:13px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
                         title="${escHtml(sl.filename)}">${escHtml(sl.name)}</div>
                    <div style="font-size:11px;color:var(--text2);margin-top:2px">
                        ${sl.organ_id ? '<span style="background:var(--accent-dim);color:var(--accent);padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600">' + escHtml(sl.organ_id) + '</span>' : ''}
                        ${sl.extension ? '<span style="margin-left:4px;color:var(--muted)">' + sl.extension.toUpperCase() + '</span>' : ''}
                        ${hasFixePhoto ? '<span style="margin-left:4px;color:var(--success)" title="Photo fixé appairée">&#10003;</span>' : ''}
                    </div>
                </div>
            </div>`;
        });
        html += '</div>';
    } else if (lamePath) {
        html += `
        <div class="empty-state" style="padding:24px">
            <h3>Aucune lame trouvée</h3>
            <p style="color:var(--text2);font-size:13px">Le dossier <code style="font-family:var(--mono);color:var(--accent);font-size:12px">${escHtml(lamePath)}</code> ne contient aucun fichier de lame supporté.</p>
        </div>`;
    } else {
        html += `
        <div class="empty-state" style="padding:24px">
            <h3>Chemin des lames non configuré</h3>
            <p style="color:var(--text2);font-size:13px">Renseignez le chemin dans l'onglet Informations (<code>dossier_lames_path</code>) ou configurez <code>slides_root</code> dans les paramètres.</p>
        </div>`;
    }

    // ── Bouton global viewer ──
    if (lamePath && slideCount > 0) {
        html += `
        <div style="display:flex;gap:8px;margin-bottom:20px">
            <button class="btn" onclick="openViewerLames('${escPath(lamePath)}')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="3"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2"/></svg>
                Ouvrir toutes les lames dans le viewer
            </button>
        </div>`;
    }

    // ── Grilles de lecture (templates) ──
    if (templates.length) {
        html += '<div class="card-title" style="margin-top:8px"><span class="icon">&#128203;</span> Grilles de lecture</div>';
        html += '<div class="micro-templates-grid">';
        templates.forEach(t => {
            html += `
            <div class="micro-template-card" onclick="openMicroTemplate(${c.id}, '${t.id}')">
                <div class="micro-template-icon">${t.icon || '&#128203;'}</div>
                <div class="micro-template-name">${escHtml(t.name)}</div>
                <div class="micro-template-desc">${escHtml(t.description || '')}</div>
            </div>`;
        });
        html += '</div>';
    }

    html += '</div>';
    el.innerHTML = html;
}

function openMicroTemplate(caseId, templateId) {
    // Future: open micro reading grid for specific template
    toast('Grille de lecture : ' + templateId + ' (à venir)', 'info');
}

// ══════════════════════════════════════════════════════════════
// RADIO PANEL — Full interactive radiology module
// ══════════════════════════════════════════════════════════════

function renderModulesPanel(c) {
    const el = document.getElementById('panel-modules');
    const modules = c.modules || {};
    const moduleNames = Object.keys(modules);

    if (!moduleNames.length) {
        el.innerHTML = '<div class="empty-state"><h3>Aucune donnée de module</h3><p>Les modules seront remplis depuis l\'app ou par import JSON.</p></div>';
        return;
    }

    // Pretty module names
    const prettyNames = {
        macro_frais: 'Examen macro frais',
        macro_autopsie: 'Examen macro autopsie',
        macro_fixe: 'Macro fixé',
        tranches_section: 'Tranches de section',
        neuropath: 'Neuropathologie',
        radio: 'Imagerie Radio',
        index: 'Index',
        atcd_maternels: 'ATCD Maternels',
        atcd_obstetricaux: 'ATCD Obstétricaux',
        grossesse_en_cours: 'Grossesse en cours',
        examens_prenataux: 'Examens prénataux',
    };
    const icons = {
        macro_frais: '&#129516;', macro_autopsie: '&#128300;',
        macro_fixe: '&#129514;', tranches_section: '&#129514;',
        neuropath: '&#129504;', radio: '&#128225;', index: '&#128203;',
    };

    // Compute toolbar
    const hasMacroData = moduleNames.some(n => n === 'macro_frais' || n === 'macro_autopsie');
    const hasComputed = moduleNames.includes('computed_biometrics');
    const computedMod = modules.computed_biometrics?.data || {};

    let toolbar = '';
    if (hasMacroData) {
        toolbar = `
        <div class="card" style="background:var(--bg3);border-color:var(--accent);margin-bottom:20px">
            <div class="card-title" style="margin-bottom:8px"><span class="icon">&#9881;</span> Calculs biométriques</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <button class="btn btn-primary btn-sm" onclick="computeBiometrics(${c.id})">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>
                    Calculer DS &amp; Ratios
                </button>
                <span id="computeStatus" style="font-size:11px;color:var(--text3)"></span>
            </div>
            ${hasComputed && computedMod.report_text ? `
                <div style="margin-top:12px">
                    <div style="font-size:12px;font-weight:600;color:var(--success);margin-bottom:6px">Rapport calculé</div>
                    <pre style="background:var(--bg);padding:12px;border-radius:var(--radius);font-family:var(--mono);font-size:11px;max-height:300px;overflow:auto;color:var(--text);white-space:pre-wrap;border:1px solid var(--border)">${escHtml(computedMod.report_text)}</pre>
                </div>` : ''}
        </div>`;
    }

    el.innerHTML = toolbar + moduleNames.filter(n => n !== 'computed_biometrics').map(name => {
        const mod = modules[name];
        const label = prettyNames[name] || name;
        const icon = icons[name] || '&#128203;';
        let body;

        // Route to the right renderer
        if (name === 'macro_frais') body = renderMacroFrais(mod.data);
        else if (name === 'macro_autopsie') body = renderMacroAutopsie(mod.data);
        else if (name === 'tranches_section') body = renderTranchesSection(mod.data);
        else if (name === 'neuropath') body = renderNeuropath(mod.data);
        else if (name === 'radio') body = renderRadio(mod.data);
        else body = renderGenericModule(mod.data);

        return `
        <div class="card">
            <div class="card-title" style="cursor:pointer" onclick="this.nextElementSibling.classList.toggle('collapsed')">
                <span class="icon">${icon}</span> ${label}
                <span style="font-size:11px;color:var(--text3);font-weight:400;margin-left:auto">
                    ${new Date(mod.updated_at).toLocaleString('fr-FR')} · <span style="color:var(--accent);cursor:pointer" onclick="event.stopPropagation();toggleRawJson(this)">JSON</span>
                </span>
            </div>
            <div class="mod-body">${body}</div>
        </div>`;
    }).join('');
}

function toggleRawJson(el) {
    const card = el.closest('.card');
    const body = card.querySelector('.mod-body');
    const rawEl = body.querySelector('[data-raw-json]');
    if (body.dataset.showRaw === '1') {
        body.innerHTML = body.dataset.rendered;
        body.dataset.showRaw = '0';
        el.textContent = 'JSON';
    } else {
        body.dataset.rendered = body.innerHTML;
        const rawJson = rawEl ? rawEl.dataset.rawJson : JSON.stringify({}, null, 2);
        body.innerHTML = `<pre style="background:var(--bg3);padding:12px;border-radius:var(--radius);font-family:var(--mono);font-size:11px;max-height:400px;overflow:auto;color:var(--text2)">${escHtml(rawJson)}</pre>`;
        body.dataset.showRaw = '1';
        el.textContent = 'Rendu';
    }
}

// ── Biométries labels ────────────────────────
const BIO_LABELS = {
    masse:'Masse (g)', vt:'VT (mm)', vc:'VC (mm)', pc:'PC (mm)', pt:'PT (mm)', pa:'PA (mm)',
    bip:'BIP (mm)', fo:'FO (mm)', dici:'DICI (mm)', dice:'DICE (mm)', dim:'DIM (mm)',
    fpd:'Fémur D (mm)', fpg:'Fémur G (mm)', main:'Main (mm)', pied:'Pied (mm)',
    lcc:'LCC (mm)',
};

// ── Organ labels ─────────────────────────────
const ORGAN_LABELS = {
    coeur:'Cœur', poumons:'Poumons', poumon_d:'Poumon droit', poumon_g:'Poumon gauche',
    foie:'Foie', rate:'Rate', reins:'Reins', rein_d:'Rein droit', rein_g:'Rein gauche',
    thymus:'Thymus', pancreas:'Pancréas', surrenales:'Surrénales',
    surrenale_d:'Surrénale D', surrenale_g:'Surrénale G',
    cerveau:'Cerveau', thyroide:'Thyroïde', diaphragme:'Diaphragme',
    tube_digestif:'Tube digestif', vessie:'Vessie', gonades:'Gonades',
};

// ── Cardiac sub-fields ───────────────────────
const CARDIAC_LABELS = {
    masse:'Masse', crosse:'Crosse', foramen_ovale:'Foramen ovale',
    gros_vx:'Gros vaisseaux', isthme:'Isthme', quatre_cav:'4 cavités',
    sinus_cor:'Sinus coronaire', vd_av:'VD (av)', vd_ej:'VD (éj)',
    vg_av:'VG (av)', vg_ej:'VG (éj)', og_retours:'OG/Retours',
    septum:'Septum', tsa:'TSA', tvi:'TVI', ductus:'Ductus',
    ap:'AP', aorte:'Aorte', vci:'VCI',
};

// ── Render helpers ───────────────────────────
function kvRow(label, val, unit) {
    if (val === null || val === undefined || val === '') return '';
    const cls = typeof val === 'number' ? 'font-family:var(--mono)' : '';
    return `<tr><td style="color:var(--text2);font-size:12px;padding:3px 8px">${label}</td><td style="font-size:13px;padding:3px 8px;${cls}">${val}${unit ? ' <span style="color:var(--text3);font-size:11px">'+unit+'</span>' : ''}</td></tr>`;
}

function kvTable(rows, title) {
    const filtered = rows.filter(Boolean);
    if (!filtered.length) return '';
    return `${title ? '<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">'+title+'</div>':''}
    <table style="width:100%;border-collapse:collapse">${filtered.join('')}</table>`;
}

// ── Universal HPO findings renderer for données modules ──
// Handles both formats: data.hpo.findings[] (macro_frais) and data.hpo_codes[] (radio, neuropath)
function renderHPOFindings(data) {
    // Collect findings from either format
    let findings = [];
    if (data.hpo && data.hpo.findings && data.hpo.findings.length) {
        findings = data.hpo.findings;
    }
    if (data.hpo_codes && data.hpo_codes.length) {
        findings = findings.concat(data.hpo_codes);
    }
    if (!findings.length) return '';

    // Deduplicate by code + source_field
    const seen = {};
    const unique = findings.filter(h => {
        const key = (h.code || '') + '_' + (h.source_field || '');
        if (seen[key]) return false;
        seen[key] = true;
        return true;
    });

    let html = `<div style="font-size:12px;font-weight:600;color:var(--purple,#7c3aed);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">Codes HPO (${unique.length})</div>`;
    unique.forEach(h => {
        const typeBg = h.type === 'chip' ? 'var(--accent,#5b4fd6)' : h.type === 'zscore' ? 'var(--warning,#f59e0b)' : h.type === 'toggle' ? 'var(--success,#22c55e)' : 'var(--purple,#7c3aed)';
        const typeLabel = h.type === 'chip' ? 'chip' : h.type === 'zscore' ? 'Z-score' : h.type === 'toggle' ? 'toggle' : h.type === 'textarea_autocomplete' ? 'texte' : h.type === 'textarea_keyword' ? 'auto' : h.type || '';
        const termDisplay = h.term_fr || h.term || '';
        const sourceDisplay = h.source_value || h.source_field || h.source || '';
        html += `<div style="display:flex;align-items:center;gap:6px;padding:3px 8px;font-size:11px">
            <span style="font-family:var(--mono,monospace);color:var(--purple,#7c3aed);font-weight:600;white-space:nowrap;min-width:90px">${escHtml(h.code || '')}</span>
            <span style="color:var(--text,#ccc);flex:1">${escHtml(termDisplay)}</span>
            <span style="font-size:9px;padding:1px 5px;border-radius:8px;background:${typeBg};color:#fff;white-space:nowrap">${typeLabel}</span>
            <span style="color:var(--text3,#666);font-size:10px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(sourceDisplay)}</span>
        </div>`;
    });
    return html;
}

function renderMacroFrais(data) {
    if (!data) return '<span style="color:var(--text3)">Pas de données</span>';
    let html = '';

    // Biométries
    const bio = data.biometries || data.biometrie || {};
    if (Object.keys(bio).length) {
        const rows = Object.entries(bio).map(([k, v]) => kvRow(BIO_LABELS[k] || k, v, ''));
        html += kvTable(rows, 'Biométries corporelles');
    }

    // Macération
    if (data.maceration !== undefined) {
        html += kvTable([kvRow('Score macération', data.maceration, '')], 'Macération');
    }

    // Sexe, état
    const metaRows = [];
    if (data.sexe) metaRows.push(kvRow('Sexe', data.sexe === 'M' ? 'Masculin' : data.sexe === 'F' ? 'Féminin' : data.sexe, ''));
    if (data.etat) metaRows.push(kvRow('État', data.etat, ''));
    if (data.aspect_general) metaRows.push(kvRow('Aspect général', data.aspect_general, ''));
    if (metaRows.length) html += kvTable(metaRows, 'Informations générales');

    // Morphologie externe
    const morpho = data.morphologie || data.examen_externe || {};
    if (Object.keys(morpho).length) {
        const rows = Object.entries(morpho).map(([k, v]) => {
            if (typeof v === 'object' && v !== null) return kvRow(k, JSON.stringify(v), '');
            return kvRow(k, v, '');
        });
        html += kvTable(rows, 'Morphologie externe');
    }

    // Anomalies
    const anomalies = data.anomalies || [];
    if (anomalies.length) {
        html += `<div style="font-size:12px;font-weight:600;color:var(--danger);margin:12px 0 4px">Anomalies signalées</div>`;
        html += anomalies.map(a => `<div style="padding:2px 8px;font-size:12px;color:var(--text)">• ${typeof a === 'string' ? a : (a.description || a.type || JSON.stringify(a))}</div>`).join('');
    }

    // Tout le reste non traité
    const handled = new Set(['biometries','biometrie','maceration','sexe','etat','aspect_general','morphologie','examen_externe','anomalies','hpo','hpo_codes','hpo_meta','photos','dossier','timestamp','type','terme','commentaire']);
    const rest = Object.entries(data).filter(([k]) => !handled.has(k));
    if (rest.length) {
        const rows = rest.map(([k, v]) => {
            if (typeof v === 'object' && v !== null) return '';
            return kvRow(k, v, '');
        });
        const filtered = rows.filter(Boolean);
        if (filtered.length) html += kvTable(filtered, 'Autres données');
    }

    // HPO findings
    html += renderHPOFindings(data);

    // Store raw JSON for toggle
    html = `<div data-raw-json='${escHtml(JSON.stringify(data,null,2))}'>${html}</div>`;
    return html;
}

function renderMacroAutopsie(data) {
    if (!data) return '<span style="color:var(--text3)">Pas de données</span>';
    let html = '';

    // Group known organs
    const organKeys = Object.keys(ORGAN_LABELS);
    const cardiacKeys = Object.keys(CARDIAC_LABELS);

    const skipKeys = new Set(['hpo','hpo_codes','hpo_meta','photos','dossier','timestamp','type']);
    for (const [key, val] of Object.entries(data)) {
        if (val === null || val === undefined || skipKeys.has(key)) continue;

        if (key === 'coeur' && typeof val === 'object') {
            // Special cardiac rendering
            html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">&#10084; Cœur</div>`;
            const rows = Object.entries(val).map(([sk, sv]) => {
                if (typeof sv === 'object' && sv !== null) {
                    // Nested (vd_av, vg_av etc with sub-fields)
                    const subRows = Object.entries(sv).map(([ssk, ssv]) => kvRow('&nbsp;&nbsp;' + ssk, ssv, ''));
                    return kvRow(CARDIAC_LABELS[sk] || sk, '', '') + subRows.join('');
                }
                return kvRow(CARDIAC_LABELS[sk] || sk, sv, sk === 'masse' ? 'g' : '');
            });
            html += `<table style="width:100%;border-collapse:collapse">${rows.join('')}</table>`;
        } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
            // Generic organ object
            const label = ORGAN_LABELS[key] || key;
            const rows = Object.entries(val).map(([sk, sv]) => {
                if (typeof sv === 'object' && sv !== null) return kvRow(sk, JSON.stringify(sv), '');
                return kvRow(sk, sv, sk === 'masse' || sk === 'poids' ? 'g' : '');
            });
            html += kvTable(rows, label);
        } else {
            // Simple value
            html += kvTable([kvRow(ORGAN_LABELS[key] || key, val, '')], '');
        }
    }

    // HPO findings
    html += renderHPOFindings(data);

    html = `<div data-raw-json='${escHtml(JSON.stringify(data,null,2))}'>${html}</div>`;
    return html;
}

function renderTranchesSection(data) {
    if (!data) return '<span style="color:var(--text3)">Pas de données</span>';
    let html = '';

    if (Array.isArray(data)) {
        html += data.map((tranche, i) => {
            const rows = Object.entries(tranche).map(([k, v]) => {
                if (typeof v === 'object') return kvRow(k, JSON.stringify(v), '');
                return kvRow(k, v, '');
            });
            return kvTable(rows, `Tranche ${i + 1}`);
        }).join('');
    } else if (typeof data === 'object') {
        const rows = Object.entries(data).map(([k, v]) => {
            if (typeof v === 'object') return kvRow(k, JSON.stringify(v), '');
            return kvRow(k, v, '');
        });
        html += kvTable(rows, 'Tranches de section');
    }

    html = `<div data-raw-json='${escHtml(JSON.stringify(data,null,2))}'>${html}</div>`;
    return html;
}

function renderNeuropath(data) {
    if (!data) return '<span style="color:var(--text3)">Pas de données</span>';
    let html = '';

    // SA
    if (data.sa) {
        html += kvTable([kvRow('Terme SA', data.sa, 'SA')], 'Terme');
    }

    // Descriptions macroscopiques
    const descs = data.descriptions || {};
    if (Object.keys(descs).length) {
        const descLabels = {meninges:'Méninges', gyration:'Gyration', willis:'Polygone de Willis', mamillaires:'Corps mamillaires', colliculi:'Colliculi'};
        const rows = Object.entries(descs).map(([k, v]) => {
            const label = descLabels[k] || k;
            const status = v && v.status ? v.status : '—';
            const signes = v && v.signes && v.signes.length ? ' (' + v.signes.map(s => s.label).join(', ') + ')' : '';
            const detail = v && v.detail ? ' — ' + v.detail : '';
            const cls = status === 'Normal' ? 'color:var(--success)' : status === 'Anormal' ? 'color:var(--danger)' : '';
            return `<tr><td style="color:var(--text2);font-size:12px;padding:3px 8px">${label}</td><td style="font-size:13px;padding:3px 8px;${cls}">${status}${signes}${detail}</td></tr>`;
        });
        html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">Description macroscopique</div><table style="width:100%;border-collapse:collapse">${rows.join('')}</table>`;
    }

    // Biométries
    const bio = data.biometries || {};
    if (Object.keys(bio).length) {
        const bioLabels = {masse_encephale:'Masse encéphale (g)', masse_cervelet:'Masse cervelet (g)', DOFD:'DOF droit (mm)', DOFG:'DOF gauche (mm)', DT:'DT / BIP cérébral (mm)', DTC:'DTC (mm)', HautVermis:'Hauteur vermis (mm)', CC:'Longueur CC (mm)'};
        const rows = Object.entries(bio).filter(([k,v]) => v !== null).map(([k, v]) => kvRow(bioLabels[k] || k, v, ''));
        html += kvTable(rows, 'Biométries cérébrales');
    }

    // Z-scores
    const zs = data.zscores || {};
    if (Object.keys(zs).length) {
        const rows = Object.entries(zs).map(([k, v]) => {
            const z = parseFloat(String(v).replace(/[^0-9.\-+]/g, ''));
            const cls = !isNaN(z) && Math.abs(z) > 2 ? 'color:var(--danger);font-weight:600' : !isNaN(z) && Math.abs(z) > 1 ? 'color:var(--warning)' : 'color:var(--success)';
            return `<tr><td style="color:var(--text2);font-size:12px;padding:3px 8px">${k}</td><td style="font-size:13px;padding:3px 8px;font-family:var(--mono);${cls}">${v}</td></tr>`;
        });
        html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">Z-scores</div><table style="width:100%;border-collapse:collapse">${rows.join('')}</table>`;
    }

    // Oculaire
    const ocu = data.oculaire || {};
    if (ocu.oeil1 || ocu.oeil2) {
        const rows = [];
        if (ocu.oeil1) {
            if (ocu.oeil1.dt) rows.push(kvRow('Œil 1 DT', ocu.oeil1.dt, 'mm'));
            if (ocu.oeil1.dap) rows.push(kvRow('Œil 1 DAP', ocu.oeil1.dap, 'mm'));
            if (ocu.oeil1.dc) rows.push(kvRow('Œil 1 DC', ocu.oeil1.dc, 'mm'));
        }
        if (ocu.oeil2) {
            if (ocu.oeil2.dt) rows.push(kvRow('Œil 2 DT', ocu.oeil2.dt, 'mm'));
            if (ocu.oeil2.dap) rows.push(kvRow('Œil 2 DAP', ocu.oeil2.dap, 'mm'));
            if (ocu.oeil2.dc) rows.push(kvRow('Œil 2 DC', ocu.oeil2.dc, 'mm'));
        }
        html += kvTable(rows, 'Biométries oculaires');
    }

    // Cervelet / Ratio
    const cerv = data.cervelet || {};
    if (cerv.ratio_ce || cerv.masse) {
        const rows = [];
        if (cerv.masse) rows.push(kvRow('Masse cervelet', cerv.masse, 'g'));
        if (cerv.ratio_ce) rows.push(kvRow('Ratio C/E', cerv.ratio_ce, '%'));
        html += kvTable(rows, 'Cervelet');
    }

    // Aqueduc
    const aq = data.aqueduc || {};
    if (aq.status && aq.status.length) {
        html += kvTable([kvRow('Aqueduc de Sylvius', aq.status.join(', '), ''), aq.detail ? kvRow('Détails', aq.detail, '') : ''], 'Aqueduc');
    }

    // Corps calleux
    const cc = data.corps_calleux || {};
    if (cc.status && cc.status.length) {
        const rows = [kvRow('Corps calleux', cc.status.join(', '), '')];
        if (cc.longueur) rows.push(kvRow('Longueur CC', cc.longueur, 'mm'));
        if (cc.detail) rows.push(kvRow('Détails', cc.detail, ''));
        html += kvTable(rows, 'Corps calleux');
    }

    // Tranches HD
    const thd = data.tranches_hd || [];
    if (thd.length) {
        html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">Tranches HD (${thd.length})</div>`;
        thd.forEach((t, i) => {
            const chips = (t.constatations || []).join(', ') || '—';
            const cls = chips.includes('Normal') ? 'color:var(--success)' : 'color:var(--text)';
            html += `<div style="font-size:12px;padding:2px 8px;${cls}"><strong>#${t.numero || i+1}</strong> ${chips}${t.note ? ' — <em style="color:var(--text3)">'+escHtml(t.note)+'</em>' : ''}</div>`;
        });
    }

    // Tranches HG
    const thg = data.tranches_hg || [];
    if (thg.length) {
        html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">Tranches HG (${thg.length})</div>`;
        thg.forEach((t, i) => {
            const chips = (t.constatations || []).join(', ') || '—';
            const cls = chips.includes('Normal') ? 'color:var(--success)' : 'color:var(--text)';
            html += `<div style="font-size:12px;padding:2px 8px;${cls}"><strong>#${t.numero || i+1}</strong> ${chips}${t.note ? ' — <em style="color:var(--text3)">'+escHtml(t.note)+'</em>' : ''}</div>`;
        });
    }

    // HPO findings (unified renderer)
    html += renderHPOFindings(data);

    html = `<div data-raw-json='${escHtml(JSON.stringify(data,null,2))}'>${html}</div>`;
    return html;
}

function renderRadio(data) {
    if (!data) return '<span style="color:var(--text3)">Pas de données</span>';
    let html = '';

    // Terme
    const terme = data.terme || {};
    if (terme.sa) {
        html += kvTable([kvRow('Terme', terme.sa + ' SA' + (terme.jours ? ' + ' + terme.jours + 'j' : ''), '')], 'Terme');
    }

    // Aspect général
    if (data.aspect_general) {
        html += kvTable([kvRow('Description', data.aspect_general, '')], 'Aspect général');
    }

    // Côtes
    const cotes = data.cotes || {};
    if (cotes.droite || cotes.gauche) {
        html += kvTable([kvRow('Droite', cotes.droite || '—', ''), kvRow('Gauche', cotes.gauche || '—', '')], 'Côtes');
    }

    // Thorax
    if (data.thorax_forme) {
        html += kvTable([kvRow('Forme', data.thorax_forme, '')], 'Thorax');
    }

    // Vertèbres
    const vert = data.vertebres || {};
    if (vert.aspects && vert.aspects.length) {
        const rows = [kvRow('Aspects', vert.aspects.join(', '), '')];
        if (vert.remarques) rows.push(kvRow('Remarques', vert.remarques, ''));
        html += kvTable(rows, 'Vertèbres');
    }

    // Aspect des os
    const os = data.aspect_os || {};
    if (os.aspects && os.aspects.length) {
        const cls = os.aspects.includes('Normal') ? '' : 'color:var(--danger)';
        const rows = [`<tr><td style="color:var(--text2);font-size:12px;padding:3px 8px">Aspects</td><td style="font-size:13px;padding:3px 8px;${cls}">${escHtml(os.aspects.join(', '))}</td></tr>`];
        if (os.remarques) rows.push(kvRow('Remarques', os.remarques, ''));
        html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">Aspect des os</div><table style="width:100%;border-collapse:collapse">${rows.join('')}</table>`;
    }

    // Biométries osseuses
    const biom = data.biometries || {};
    if (biom.bip_osseux_mm || biom.pc_radio_mm || biom.os_longs) {
        const rows = [];
        if (biom.bip_osseux_mm) rows.push(kvRow('BIP osseux', biom.bip_osseux_mm, 'mm'));
        if (biom.pc_radio_mm) rows.push(kvRow('PC radio', biom.pc_radio_mm, 'mm'));
        html += kvTable(rows, 'Biométries osseuses');

        // Os longs table
        const bones = biom.os_longs || {};
        const boneKeys = Object.keys(bones).filter(k => bones[k].moyenne !== null);
        if (boneKeys.length) {
            html += '<table style="width:100%;border-collapse:collapse;margin-top:4px"><tr><th style="text-align:left;font-size:11px;color:var(--text3);padding:2px 8px">Os</th><th style="font-size:11px;color:var(--text3);padding:2px 8px">D</th><th style="font-size:11px;color:var(--text3);padding:2px 8px">G</th><th style="font-size:11px;color:var(--text3);padding:2px 8px">Moy</th><th style="font-size:11px;color:var(--text3);padding:2px 8px">Z-score</th></tr>';
            boneKeys.forEach(k => {
                const b = bones[k];
                const z = b.zscore_chitty;
                const zcls = z !== null ? (Math.abs(z) > 2 ? 'color:var(--danger);font-weight:600' : Math.abs(z) > 1 ? 'color:var(--warning)' : 'color:var(--success)') : '';
                html += `<tr><td style="font-size:12px;padding:2px 8px;font-weight:500">${escHtml(k)}</td><td style="font-size:12px;padding:2px 8px;text-align:center;font-family:var(--mono)">${b.droite ?? '—'}</td><td style="font-size:12px;padding:2px 8px;text-align:center;font-family:var(--mono)">${b.gauche ?? '—'}</td><td style="font-size:12px;padding:2px 8px;text-align:center;font-family:var(--mono)">${b.moyenne ?? '—'}</td><td style="font-size:12px;padding:2px 8px;text-align:center;font-family:var(--mono);${zcls}">${z !== null ? z : '—'}</td></tr>`;
            });
            html += '</table>';
        }
    }

    // Scores staturaux
    const scores = data.scores_staturaux || {};
    if (scores.hadlock_sa || scores.adalian_sa) {
        const rows = [];
        if (scores.hadlock_sa) rows.push(kvRow('Hadlock (1984)', scores.hadlock_sa, 'SA'));
        if (scores.adalian_sa) rows.push(kvRow('Adalian (2002)', scores.adalian_sa, 'SA'));
        html += kvTable(rows, 'Scores staturaux');
    }

    // Maturation osseuse
    const mat = data.maturation_osseuse || [];
    if (mat.length) {
        html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px;border-bottom:1px solid var(--border);padding-bottom:4px">Maturation osseuse (${mat.length} items)</div>`;
        mat.forEach(m => {
            const cls = m.status === 'present' ? 'color:var(--success)' : 'color:var(--danger)';
            const icon = m.status === 'present' ? '&#10003;' : '&#10007;';
            html += `<div style="font-size:12px;padding:2px 8px;${cls}"><span style="font-family:var(--mono);font-weight:600">${m.sa} SA</span> ${escHtml(m.label)} ${icon}</div>`;
        });
    }

    // Remarques
    if (data.remarques) {
        html += kvTable([kvRow('Remarques', data.remarques, '')], 'Remarques');
    }

    // HPO findings (unified renderer)
    html += renderHPOFindings(data);

    html = `<div data-raw-json='${escHtml(JSON.stringify(data,null,2))}'>${html}</div>`;
    return html;
}

function renderGenericModule(data) {
    if (!data || (typeof data === 'object' && !Object.keys(data).length)) {
        return '<span style="color:var(--text3)">Pas de données</span>';
    }

    if (Array.isArray(data)) {
        return `<pre style="background:var(--bg3);padding:12px;border-radius:var(--radius);font-family:var(--mono);font-size:11px;max-height:300px;overflow:auto;color:var(--text2)">${escHtml(JSON.stringify(data, null, 2))}</pre>`;
    }

    // Attempt structured rendering for any object
    let html = '';
    const rows = [];
    const nested = [];

    for (const [k, v] of Object.entries(data)) {
        if (v === null || v === undefined) continue;
        if (typeof v === 'object' && !Array.isArray(v)) {
            nested.push([k, v]);
        } else if (Array.isArray(v)) {
            nested.push([k, v]);
        } else {
            rows.push(kvRow(k, v, ''));
        }
    }

    if (rows.length) html += kvTable(rows, '');
    for (const [k, v] of nested) {
        if (k === 'hpo' || k === 'hpo_codes' || k === 'hpo_meta') continue;
        if (Array.isArray(v)) {
            html += `<div style="font-size:12px;font-weight:600;color:var(--accent);margin:12px 0 4px">${k}</div>`;
            html += `<pre style="background:var(--bg3);padding:8px;border-radius:var(--radius);font-family:var(--mono);font-size:11px;max-height:150px;overflow:auto;color:var(--text2)">${escHtml(JSON.stringify(v, null, 2))}</pre>`;
        } else {
            const subRows = Object.entries(v).map(([sk, sv]) => {
                if (typeof sv === 'object') return kvRow(sk, JSON.stringify(sv), '');
                return kvRow(sk, sv, '');
            });
            html += kvTable(subRows, k);
        }
    }

    // HPO findings
    html += renderHPOFindings(data);

    return html;
}

// ── Foekinator Panel ─────────────────────────
