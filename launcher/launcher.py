"""Abre o ATLAS numa janela própria: sobe o Streamlit escondido e mostra o app via pywebview.

Uso: pythonw launcher\\launcher.py   (o atalho criado por criar_atalho.ps1 faz isso).
Ao fechar a janela, o servidor Streamlit é encerrado junto.
"""
import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import webview

RAIZ = Path(__file__).resolve().parent.parent
ICONE = Path(__file__).resolve().parent / "atlas.ico"
TITULO = "ATLAS"
COR_FUNDO = "#0d0d11"
LIMITE_INICIO = 90  # segundos esperando o Streamlit ficar pronto
LOG = Path(os.environ.get("LOCALAPPDATA", RAIZ)) / "ATLAS" / "atlas.log"

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

TELA_ABERTURA = f"""
<html><body style="margin:0;background:{COR_FUNDO};color:#ececf1;font-family:Segoe UI,sans-serif;
display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh">
<div style="font-size:42px;font-weight:700;letter-spacing:8px;color:#b44cff">ATLAS</div>
<div style="margin-top:14px;font-size:14px;opacity:.6">Iniciando…</div>
</body></html>
"""


# ---------- instância única ----------
def _trazer_janela_existente():
    hwnd = user32.FindWindowW(None, TITULO)
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)


def _garantir_instancia_unica():
    # o mutex vive enquanto o processo viver; guardado em global para não ser coletado
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ATLAS.Dashboard.Instancia")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        _trazer_janela_existente()
        sys.exit(0)


# ---------- servidor Streamlit ----------
def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _iniciar_streamlit(porta):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":  # python.exe + CREATE_NO_WINDOW dá logs sem abrir console
        python = python.with_name("python.exe")
    comando = [
        str(python), "-m", "streamlit", "run", "app.py",
        "--server.port", str(porta), "--server.address", "127.0.0.1",
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
    ]
    log = open(LOG, "w", encoding="utf-8")
    return subprocess.Popen(
        comando, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _encerrar_streamlit(proc):
    if proc.poll() is None:
        # /T derruba também os processos filhos do Streamlit
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)


def _aguardar_pronto(proc, porta):
    url = f"http://127.0.0.1:{porta}/_stcore/health"
    fim = time.time() + LIMITE_INICIO
    while time.time() < fim and proc.poll() is None:
        try:
            if urllib.request.urlopen(url, timeout=1).status == 200:
                return True
        except OSError:
            time.sleep(0.4)
    return False


# ---------- aparência da janela (Windows) ----------
def _colorref(hex_cor):
    r, g, b = (int(hex_cor[i:i + 2], 16) for i in (1, 3, 5))
    return ctypes.c_int(r | (g << 8) | (b << 16))


def _estilizar_janela():
    """Barra de título escura, cor do ATLAS no Windows 11 e ícone próprio na barra de tarefas."""
    hwnd = 0
    for _ in range(50):
        hwnd = user32.FindWindowW(None, TITULO)
        if hwnd:
            break
        time.sleep(0.1)
    if not hwnd:
        return
    escuro = ctypes.c_int(1)
    dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(escuro), 4)  # modo escuro (Win10 20H1+ e Win11)
    if sys.getwindowsversion().build >= 22000:  # cores exatas só existem no Windows 11
        for atributo, cor in ((35, COR_FUNDO), (34, COR_FUNDO), (36, "#ececf1")):  # barra, borda, texto
            valor = _colorref(cor)
            dwmapi.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(valor), 4)
    if ICONE.exists():
        for tipo, tamanho in ((0, 16), (1, 32)):  # ICON_SMALL, ICON_BIG
            hicon = user32.LoadImageW(None, str(ICONE), 1, tamanho, tamanho, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            user32.SendMessageW(hwnd, 0x80, tipo, hicon)  # WM_SETICON


# ---------- principal ----------
def main():
    _garantir_instancia_unica()
    # sem isto a barra de tarefas agrupa o ATLAS sob o ícone do Python
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ATLAS.Dashboard")

    porta = _porta_livre()
    proc = _iniciar_streamlit(porta)

    janela = webview.create_window(
        TITULO, html=TELA_ABERTURA, width=1440, height=880, min_size=(1000, 640),
        background_color=COR_FUNDO,
    )

    def ao_iniciar():
        _estilizar_janela()
        if _aguardar_pronto(proc, porta):
            janela.load_url(f"http://127.0.0.1:{porta}")
        else:
            janela.load_html(TELA_ABERTURA.replace("Iniciando…", f"Falha ao iniciar. Veja o log em {LOG}"))

    try:
        webview.start(ao_iniciar)
    finally:
        _encerrar_streamlit(proc)


if __name__ == "__main__":
    main()
