async function renderCRPanel(c) {
    const el = document.getElementById('panel-cr');
    const caseId = c.id;

    // Charger les templates disponibles
    let templates = [];
    try {
        const res = await api('/api/cr/templates');
        templates = res.templates || [];
    } catch (e) {}

    // Charger le dernier CR et Ollama sauvegardés
    const lastCr = c.modules?.last_cr?.data || {};
    const lastOllama = c.modules?.last_cr_ollama?.data || {};

    el.innerHTML = `
    <div class="card" style="border-color:var(--accent)">
        <div class="card-title"><span class="icon">&#128196;</span> Génération de compte-rendu</div>

        <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:16px">
            <div class="ff" style="min-width:200px">
                <label class="flabel">Template</label>
                <select class="fselect" id="crTemplateSelect" onchange="crShowVersion()">
                    ${templates.map(t => `<option value="${t.id}" data-version="${t.version || '1.0.0'}" ${lastCr.template_id === t.id ? 'selected' : ''}>${t.label} (v${t.version || '1.0.0'})</option>`).join('')}
                </select>
            </div>
            <button class="btn btn-primary btn-sm" onclick="generateCR(${caseId})">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
                Générer le CR
            </button>
            <button class="btn btn-sm" onclick="crShowChangelog()" title="Historique des versions" style="border-color:var(--text3);color:var(--text3)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>
                Changelog
            </button>
            <span id="crStatus" style="font-size:11px;color:var(--text3)"></span>
        </div>

        <div id="crOutput" style="${lastCr.text ? '' : 'display:none'}">
            <div style="font-size:12px;font-weight:600;color:var(--success);margin-bottom:6px">CR généré</div>
            <pre id="crText" style="background:var(--bg);padding:14px;border-radius:var(--radius);font-family:var(--mono);font-size:11px;max-height:500px;overflow:auto;color:var(--text);white-space:pre-wrap;border:1px solid var(--border);line-height:1.6">${lastCr.text ? escHtml(lastCr.text) : ''}</pre>
            <div style="display:flex;gap:8px;margin-top:8px">
                <button class="btn btn-sm" onclick="copyCRText()">Copier</button>
            </div>
        </div>
    </div>

    <div class="card" style="border-color:var(--info);margin-top:16px">
        <div class="card-title"><span class="icon">&#128172;</span> Rédaction LLM (Ollama)</div>
        <p style="font-size:12px;color:var(--text3);margin-bottom:8px">Reformule le CR en texte médical rédigé par un LLM local.</p>
        <div style="display:inline-flex;align-items:center;gap:6px;background:var(--warning-bg, rgba(255,193,7,0.12));border:1px solid var(--warning, #ffc107);border-radius:var(--radius);padding:4px 10px;margin-bottom:12px;font-size:11px;color:var(--warning, #e6a700)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span><b>Research use only</b> — Le texte généré doit être relu et validé par le médecin.</span>
        </div>

        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
            <button class="btn btn-sm" id="crBtnOllamaConnect" onclick="crConnectOllama()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                Connecter Ollama
            </button>
            <span id="crOllamaStatus" style="font-size:11px;color:var(--text3)"></span>
            <select class="fselect" id="crOllamaModelSelect" style="display:none;min-width:220px;font-size:12px" disabled>
                <option value="">Connectez d'abord...</option>
            </select>
            <button class="btn btn-sm" id="crBtnOllamaGenerate" style="display:none;border-color:var(--info);color:var(--info)" onclick="crRunOllama(${caseId})" disabled>
                Rédiger avec LLM
            </button>
        </div>

        <div id="crOllamaOutput" style="${lastOllama.text ? '' : 'display:none'}">
            <div style="font-size:12px;font-weight:600;color:var(--info);margin-bottom:6px">Texte rédigé${lastOllama.model ? ' (' + lastOllama.model + ')' : ''}</div>
            <div id="crOllamaText" style="background:var(--bg);padding:14px;border-radius:var(--radius);font-size:13px;max-height:500px;overflow:auto;color:var(--text);border:1px solid var(--border);line-height:1.7">${lastOllama.text ? escHtml(lastOllama.text) : ''}</div>
            <div style="display:flex;gap:8px;margin-top:8px">
                <button class="btn btn-sm" onclick="navigator.clipboard.writeText(document.getElementById('crOllamaText').innerText);toast('Copié','success')">Copier</button>
            </div>
        </div>
    </div>
    `;
}

async function generateCR(caseId) {
    const tpl = document.getElementById('crTemplateSelect').value;
    const status = document.getElementById('crStatus');
    status.textContent = 'Génération...';
    status.style.color = 'var(--warning)';

    try {
        const res = await api('/api/cases/' + caseId + '/cr/generate', {
            method: 'POST', body: JSON.stringify({ template_id: tpl }),
        });
        if (res.error) { toast(res.error, 'error'); status.textContent = res.error; status.style.color = 'var(--danger)'; return; }

        document.getElementById('crText').textContent = res.text;
        document.getElementById('crOutput').style.display = '';
        status.textContent = 'CR généré';
        status.style.color = 'var(--success)';
        toast('CR généré', 'success');
    } catch (e) {
        toast('Erreur: ' + e.message, 'error');
        status.textContent = 'Erreur';
        status.style.color = 'var(--danger)';
    }
}

function copyCRText() {
    const text = document.getElementById('crText').innerText;
    navigator.clipboard.writeText(text).then(() => toast('CR copié', 'success'));
}

function crShowVersion() {
    const sel = document.getElementById('crTemplateSelect');
    const opt = sel.options[sel.selectedIndex];
    if (opt) {
        const v = opt.dataset.version || '?';
        toast(`Template v${v}`, 'info');
    }
}

async function crShowChangelog() {
    const tplId = document.getElementById('crTemplateSelect').value;
    try {
        const res = await api(`/api/cr/templates/${tplId}/changelog`);
        const entries = res.changelog || [];
        if (!entries.length) { toast('Pas de changelog', 'info'); return; }

        let html = `<div style="max-height:400px;overflow:auto;font-size:12px;line-height:1.6">`;
        entries.forEach(e => {
            html += `<div style="margin-bottom:12px">`;
            html += `<div style="font-weight:700;color:var(--accent)">v${escHtml(e.version)} <span style="font-weight:400;color:var(--text3)">(${escHtml(e.date)})</span></div>`;
            html += `<ul style="margin:4px 0 0 16px;padding:0">`;
            (e.changes || []).forEach(c => {
                html += `<li style="margin-bottom:2px">${escHtml(c)}</li>`;
            });
            html += `</ul></div>`;
        });
        html += `</div>`;

        // Afficher dans une modale simple
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
        overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
        overlay.innerHTML = `<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;max-width:500px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.3)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <span style="font-weight:700;font-size:14px">Changelog — ${escHtml(tplId)}</span>
                <button class="btn btn-sm" onclick="this.closest('[style*=fixed]').remove()">✕</button>
            </div>
            ${html}
        </div>`;
        document.body.appendChild(overlay);
    } catch (e) {
        toast('Erreur: ' + e.message, 'error');
    }
}

async function crConnectOllama() {
    const btn = document.getElementById('crBtnOllamaConnect');
    const status = document.getElementById('crOllamaStatus');
    const select = document.getElementById('crOllamaModelSelect');
    const genBtn = document.getElementById('crBtnOllamaGenerate');

    btn.disabled = true;
    btn.textContent = 'Connexion...';
    status.textContent = 'Démarrage d\'Ollama...';
    status.style.color = 'var(--warning)';

    try {
        const res = await api('/api/ollama/status', { method: 'POST', body: JSON.stringify({}) });
        if (res.error) {
            status.textContent = res.error; status.style.color = 'var(--danger)';
            btn.disabled = false; btn.textContent = 'Connecter Ollama'; return;
        }

        const models = res.models || [];
        status.textContent = res.started ? `Démarré — ${models.length} modèle(s)` : `En ligne — ${models.length} modèle(s)`;
        status.style.color = 'var(--success)';
        btn.textContent = 'Connecté';
        btn.style.borderColor = 'var(--success)';
        btn.style.color = 'var(--success)';

        if (!models.length) {
            select.innerHTML = '<option value="">Aucun modèle (ollama pull mistral)</option>';
            select.style.display = 'inline-block'; select.disabled = true; return;
        }

        select.innerHTML = models.map(m => `<option value="${m.name}">${m.name} (${m.size_gb} GB${m.params ? ' · ' + m.params : ''})</option>`).join('');
        select.style.display = 'inline-block'; select.disabled = false;
        genBtn.style.display = 'inline-flex'; genBtn.disabled = false;
    } catch (e) {
        status.textContent = 'Erreur: ' + e.message; status.style.color = 'var(--danger)';
        btn.disabled = false; btn.textContent = 'Connecter Ollama';
    }
}

async function crRunOllama(caseId) {
    const model = document.getElementById('crOllamaModelSelect').value;
    const crText = document.getElementById('crText')?.innerText || '';
    const status = document.getElementById('crOllamaStatus');
    const genBtn = document.getElementById('crBtnOllamaGenerate');

    if (!model) { toast('Sélectionnez un modèle', 'error'); return; }
    if (!crText) { toast('Générez d\'abord un CR', 'error'); return; }

    genBtn.disabled = true; genBtn.textContent = 'Génération...';
    status.textContent = `Envoi à ${model}...`; status.style.color = 'var(--info)';

    try {
        const res = await api('/api/cases/' + caseId + '/cr/ollama', {
            method: 'POST', body: JSON.stringify({ text: crText, model }),
        });
        if (res.error) {
            toast(res.error, 'error'); status.textContent = res.error; status.style.color = 'var(--danger)';
            genBtn.disabled = false; genBtn.textContent = 'Rédiger avec LLM'; return;
        }

        document.getElementById('crOllamaText').innerText = res.generated_text;
        document.getElementById('crOllamaOutput').style.display = '';
        status.textContent = `Généré (${res.model}, ${res.tokens} tokens)`;
        status.style.color = 'var(--success)';
        toast('Texte rédigé', 'success');
        genBtn.disabled = false; genBtn.textContent = 'Rédiger avec LLM';
    } catch (e) {
        toast('Erreur: ' + e.message, 'error');
        status.textContent = 'Erreur'; status.style.color = 'var(--danger)';
        genBtn.disabled = false; genBtn.textContent = 'Rédiger avec LLM';
    }
}

// ── Pairing (legacy, now integrated in Macroscopie) ──

