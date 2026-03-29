// ══════════════════════════════════════════════════════════════
// FOETOPATH VIEWER — AUTO-LOAD FROM URL PARAMS
// ══════════════════════════════════════════════════════════════
// Coller ce bloc à la FIN du <script> dans templates/index.html
// (juste avant </script>)
//
// URLs supportées :
//   /?root=/chemin/lames             → charge le dossier de lames
//   /?root=/chemin&slide=nom.mrxs    → charge + ouvre une lame
// ══════════════════════════════════════════════════════════════

(function autoLoadFromURL() {
    const params = new URLSearchParams(window.location.search);
    const autoRoot = params.get('root');
    const autoSlide = params.get('slide');

    if (!autoRoot) return;

    // Remplir le champ
    const input = document.getElementById('rootInput');
    if (input) input.value = autoRoot;

    // Charger après un court délai
    setTimeout(async () => {
        await loadCases();

        if (!state.cases || !state.cases.length) return;

        if (autoSlide) {
            // Chercher la lame dans les cas chargés
            for (let i = 0; i < state.cases.length; i++) {
                try {
                    const data = await api('/api/slides', { folder: state.cases[i].path });
                    const idx = (data.slides || []).findIndex(
                        s => s.path === autoSlide || s.filename === autoSlide || s.name === autoSlide
                    );
                    if (idx >= 0) {
                        await selectCase(i);
                        setTimeout(() => { if (state.slides) loadSlide(idx); }, 300);
                        return;
                    }
                } catch (e) {}
            }
            // Fallback : ouvrir le premier cas
            await selectCase(0);
        } else if (state.cases.length === 1) {
            // Un seul cas → auto-select
            selectCase(0);
        }
    }, 200);
})();
