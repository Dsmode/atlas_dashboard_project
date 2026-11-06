// Depois de concluir, o ✓ já não existe (entra o Reativar no lugar), então a posição dele é guardada
// no clique, antes do rerun, e o confete sai dali.
(function () {
    if (window.__atlasConfeteArmado) return;
    window.__atlasConfeteArmado = true;
    document.addEventListener('click', (e) => {
        const botao = e.target.closest('[class*="st-key-conc_"] button');
        if (!botao) return;
        const r = botao.getBoundingClientRect();
        window.__atlasConfetePonto = {x: r.left + r.width / 2, y: r.top + r.height / 2, t: Date.now()};
    }, true);
})();
