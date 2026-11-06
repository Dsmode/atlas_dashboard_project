// Confete em canvas próprio, sem biblioteca: sai do ✓ clicado e some em cerca de 2,6 s.
(function () {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const cores = ['#b44cff', '#39ff9c', '#ff5fa2', '#4cc9f0', '#ffd166'];
    const tela = document.createElement('canvas');
    tela.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:99999';
    tela.width = window.innerWidth; tela.height = window.innerHeight;
    document.body.appendChild(tela);
    const g = tela.getContext('2d');
    const duracao = 2600, inicio = performance.now();
    const ponto = window.__atlasConfetePonto;
    window.__atlasConfetePonto = null;
    const origem = ponto && Date.now() - ponto.t < 10000 ? ponto : {x: tela.width / 2, y: tela.height * 0.4};
    const pecas = Array.from({length: 140}, () => {
        const angulo = Math.random() * Math.PI * 2, forca = 4 + Math.random() * 9;
        return {x: origem.x, y: origem.y, vx: Math.cos(angulo) * forca, vy: Math.sin(angulo) * forca - 4,
                l: 5 + Math.random() * 5, a: 3 + Math.random() * 4, giro: Math.random() * 6.28,
                vgiro: (Math.random() - 0.5) * 0.4, cor: cores[Math.floor(Math.random() * cores.length)]};
    });
    (function quadro(agora) {
        const t = agora - inicio;
        g.clearRect(0, 0, tela.width, tela.height);
        for (const p of pecas) {
            p.vx *= 0.985; p.vy = p.vy * 0.985 + 0.28; p.x += p.vx; p.y += p.vy; p.giro += p.vgiro;
            g.save(); g.globalAlpha = Math.max(0, 1 - t / duracao);
            g.translate(p.x, p.y); g.rotate(p.giro); g.fillStyle = p.cor; g.fillRect(-p.l / 2, -p.a / 2, p.l, p.a);
            g.restore();
        }
        if (t < duracao) requestAnimationFrame(quadro); else tela.remove();
    })(inicio);
})();
