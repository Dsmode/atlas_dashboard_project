(function () {
    let tentativas = 0;
    const timer = setInterval(() => {
        const campo = document.querySelector('[class*="st-key-dlg_nova_tarefa"] input[type="text"]');
        if (campo) { campo.focus(); clearInterval(timer); }
        else if (++tentativas > 30) clearInterval(timer);
    }, 50);
})();
