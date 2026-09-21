import asyncio
import audioop
import hmac
import secrets
import base64
import ctypes
import io
import json
import os
import tempfile
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import turtle
import urllib.parse
import uuid
import webbrowser

import edge_tts
import keyboard
import mss
import pyaudio
import requests
import serial
import speech_recognition as sr
import winsound
from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Button, Controller as MouseController
from pynput import mouse as _pynput_mouse_listener_mod
from pynput import keyboard as _pynput_keyboard_listener_mod
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.microsoft import EdgeChromiumDriverManager

import mouse
VELOCIDADE_CURSOR = 20

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_DISPONIVEL = True
except Exception:
    PYCAW_DISPONIVEL = False
    print("[Volume] pycaw/comtypes não instalados. Rode: pip install pycaw comtypes --break-system-packages")

try:
    from send2trash import send2trash
    SEND2TRASH_DISPONIVEL = True
except Exception:
    SEND2TRASH_DISPONIVEL = False
    print("[Arquivos] send2trash não instalado (exclusão vai ser permanente). Rode: pip install send2trash --break-system-packages")

try:
    from flask import Flask, request, jsonify, Response
    FLASK_DISPONIVEL = True
except Exception:
    FLASK_DISPONIVEL = False
    print("[Rede] Flask não instalado (servidor pro celular fica desligado). Rode: pip install flask --break-system-packages")


try:
    from pywinauto.application import Application
    PYWINAUTO_DISPONIVEL = True
except Exception as e:
    PYWINAUTO_DISPONIVEL = False
    print(f"[Visão] pywinauto não carregou (erro real: {e}). Se já instalou, rode: pip install --upgrade pywinauto pywin32 --break-system-packages")

try:
    import pytesseract
    from PIL import Image
    PYTESSERACT_DISPONIVEL = True
except Exception as e:
    PYTESSERACT_DISPONIVEL = False
    print(f"[Visão] pytesseract/Pillow não carregou (erro real: {e}). Rode: pip install pytesseract pillow --break-system-packages "
          "(e instale o programa Tesseract-OCR: https://github.com/UB-Mannheim/tesseract/wiki)")


CHAVES_API = [
    v for v in (os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 11))
    if v
]
if not CHAVES_API:
    print("[AVISO] Nenhuma chave Gemini encontrada em GEMINI_KEY_1..GEMINI_KEY_10. "
          "A IA vai depender só do fallback local (Ollama), se estiver ativo.")

MODELOS = [
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-preview"

]


COMBOS = [(chave, modelo) for chave in CHAVES_API for modelo in MODELOS]

def montar_url(chave, modelo):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


OLLAMA_ATIVO = True
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODELO = "llama3.2:3b"

def _payload_tem_imagem(payload):
    try:
        for conteudo in payload.get("contents", []):
            for parte in conteudo.get("parts", []):
                if "inlineData" in parte:
                    return True
    except Exception:
        pass
    return False

def _extrair_ultimo_texto(payload):
    try:
        contents = payload.get("contents", [])
        for conteudo in reversed(contents):
            for parte in conteudo.get("parts", []):
                if parte.get("text", "").strip():
                    return parte["text"]
    except Exception:
        pass
    return None

def chamar_ollama_local(prompt_texto, timeout=30):
    if not OLLAMA_ATIVO:
        return None
    try:
        resposta = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODELO, "prompt": prompt_texto, "stream": False},
            timeout=timeout
        )
        if resposta.status_code == 200:
            texto = resposta.json().get("response", "").strip()
            return texto or None
        print(f"[Ollama] HTTP {resposta.status_code} ao chamar fallback local.")
    except requests.exceptions.RequestException as e:
        print(f"[Ollama] Fallback local indisponível (Ollama tá aberto?): {e}")
    return None

IDIOMA = "pt-BR"


QTD_MENSAGENS_LEMBRADAS = 20
ARQUIVO_MEMORIA_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memoria_local.json")

REGIAO_IRIUN = {"top": 0, "left": 640, "width": 640, "height": 500}
import ctypes
_user32 = ctypes.windll.user32
REGIAO_TELA_CHEIA = {"top": 0, "left": 0, "width": _user32.GetSystemMetrics(0), "height": _user32.GetSystemMetrics(1)}
ARQUIVO_NOTAS = "notas_indianos.txt"

import winreg

def _obter_pasta_real(chave_registro, fallback):
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        ) as chave:
            valor, _ = winreg.QueryValueEx(chave, chave_registro)
            valor = os.path.expandvars(valor)
            if os.path.isdir(valor):
                return valor
    except Exception:
        pass
    return fallback

_pastas_candidatas = [
    _obter_pasta_real("Desktop", os.path.join(os.path.expanduser("~"), "Desktop")),
    _obter_pasta_real("{374DE290-123F-4565-9164-39C4925E467B}",
                       os.path.join(os.path.expanduser("~"), "Downloads")),
    _obter_pasta_real("Personal", os.path.join(os.path.expanduser("~"), "Documents")),
    os.path.join(os.path.expanduser("~"), "OneDrive", "Área de Trabalho"),
    os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos"),
    os.path.join(os.path.expanduser("~"), "Desktop"),
    os.path.join(os.path.expanduser("~"), "Downloads"),
    os.path.join(os.path.expanduser("~"), "Documents"),
]

_vistas = set()
PASTAS_BUSCA_ARQUIVOS = []
for _p in _pastas_candidatas:
    if _p not in _vistas and os.path.isdir(_p):
        _vistas.add(_p)
        PASTAS_BUSCA_ARQUIVOS.append(_p)
print(f"[Arquivos] Pastas de busca reais detectadas: {PASTAS_BUSCA_ARQUIVOS}")

CHUNK = 512
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
THRESHOLD_PALMA = 5.0

COM_PORTA_ARDUINO = "COM5"


sistema_ativo = False
escutando_palmas = False
mic_pausado = False
robo_falando = False
estado_atual_rosto = "bloqueado"
led_estado = "on"
lock_sistema = threading.Lock()
lock_api = threading.Lock()
indice_combo_atual = 0
driver_zap = None


try:
    arduino = serial.Serial(COM_PORTA_ARDUINO, 9600, timeout=1)
    time.sleep(2)
    print(f"Arduino conectado na {COM_PORTA_ARDUINO}")
except Exception as e:
    print(f"Erro ao conectar no Arduino: {e}")
    arduino = None


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    _scale_raw = ctypes.windll.shcore.GetScaleFactorForDevice(0)
    FATOR_DPI = _scale_raw / 100.0
except Exception:
    FATOR_DPI = 1.0
print(f"[DPI] Fator de escala detectado: {FATOR_DPI}x (raw={FATOR_DPI * 100:.0f}%)")

mouse = MouseController()
teclado = KeyboardController()


wn = turtle.Screen()
wn.title("INDIANOS REMASTER - Core Visão Web")


wn.setup(width=220, height=220, startx=0, starty=0)
wn.bgcolor("#101010")
wn.tracer(0)


wn._root.attributes('-topmost', True)
wn._root.resizable(False, False)

turtle_status = turtle.Turtle()
turtle_status.hideturtle()
turtle_status.penup()
turtle_status.color("#00FFFF")

turtle_titulo = turtle.Turtle()
turtle_titulo.hideturtle()
turtle_titulo.penup()
turtle_titulo.color("#303030")

turtle_rosto = turtle.Turtle()
turtle_rosto.hideturtle()
turtle_rosto.penup()
turtle_rosto.speed(0)

def ocultar_janela_temporariamente():
    try:
        wn._root.after(0, wn._root.withdraw)
        time.sleep(0.2)
    except Exception as e:
        print(f"[Janela] Erro ao ocultar: {e}")

def restaurar_janela():
    try:
        wn._root.after(0, wn._root.deiconify)
        wn._root.after(0, lambda: wn._root.attributes('-topmost', True))
    except Exception as e:
        print(f"[Janela] Erro ao restaurar: {e}")


def chamar_gemini(payload, timeout=40, max_tentativas=None, permitir_fallback_local=True):
    global indice_combo_atual
    tentativas = max_tentativas or (len(COMBOS) * 2)

    for _ in range(tentativas):
        with lock_api:
            chave_atual, modelo_atual = COMBOS[indice_combo_atual]
        url = montar_url(chave_atual, modelo_atual)

        try:
            resposta = requests.post(
                url, headers={'Content-Type': 'application/json', 'x-goog-api-key': chave_atual},
                data=json.dumps(payload), timeout=timeout
            )
        except requests.exceptions.RequestException as e:
            print(f"[API] Falha de conexão: {e}. Tentando de novo em 2s...")
            time.sleep(2)
            continue

        if resposta.status_code == 429:
            with lock_api:
                indice_combo_atual = (indice_combo_atual + 1) % len(COMBOS)
            print(f"[COTA] '{modelo_atual}' esgotou. Trocando pro próximo modelo/chave...")
            continue

        if resposta.status_code in (500, 502, 503, 504):


            print(f"[API] '{modelo_atual}' indisponível agora (HTTP {resposta.status_code}). "
                  f"Tentando de novo em 2s...")
            time.sleep(2)
            with lock_api:
                indice_combo_atual = (indice_combo_atual + 1) % len(COMBOS)
            continue

        if resposta.status_code != 200:
            print(f"[API] Erro HTTP {resposta.status_code}: {resposta.text[:200]}")
            return None

        try:
            dados = resposta.json()
            return dados['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"[API] Resposta em formato inesperado: {e}")
            return None

    print("[COTA] Todos os combos chave+modelo esgotaram por agora.")


    if not _payload_tem_imagem(payload) and permitir_fallback_local:
        prompt_local = _extrair_ultimo_texto(payload)
        if prompt_local:
            print("[Fallback] Gemini indisponível, tentando modelo local (Ollama)...")
            resposta_local = chamar_ollama_local(prompt_local)
            if resposta_local:
                print("[Fallback] Modelo local respondeu.")
                return resposta_local

    return None


def _executar_fluxo_controle(x_destino, y_destino, texto_para_digitar=None):
    try:
        print(f"ALVO: ({x_destino}, {y_destino})")
        mouse.position = (x_destino, y_destino)
        time.sleep(0.5)
        mouse.click(Button.right, 1)
        if texto_para_digitar:
            time.sleep(0.5)
            teclado.type(texto_para_digitar)
            time.sleep(0.2)
            teclado.press(Key.enter)
            teclado.release(Key.enter)
    except Exception as e:
        print(f"[Erro de Automação] {e}")

def acionar_atalho_teclado():
    if not sistema_ativo:
        print("[Hotkey] Ativação forçada via teclado.")
        protocolo_palmas()

def abrir_caixa_texto_main_thread():
    global mic_pausado
    try:
        atualizar_corpo("processando")
        mostrar_texto("DIGITANDO MENSAGEM...")
        texto = wn.textinput("Entrada de Texto", "Digite sua mensagem para a IA:")
        if texto and texto.strip():
            threading.Thread(target=processar_resposta_texto, args=(texto,), daemon=True).start()
        else:
            mic_pausado = False
            atualizar_corpo("espera")
            mostrar_texto("SISTEMAS ONLINE")
    except Exception:
        mic_pausado = False

def enviar_texto_digitado():
    global mic_pausado
    if not sistema_ativo:
        return
    mic_pausado = True
    wn._root.after(0, abrir_caixa_texto_main_thread)


def tocar_wav_com_volume(caminho_arquivo, volume=1.0):
    try:
        if os.path.exists(caminho_arquivo):
            winsound.PlaySound(caminho_arquivo, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        print(f"[Áudio] Erro ao tocar {caminho_arquivo}: {e}")

def _tocar_audio_nativo(caminho):
    global robo_falando
    try:
        if not robo_falando:
            return
        ctypes.windll.winmm.mciSendStringW(f'open "{caminho}" type mpegvideo alias voz_robo', None, 0, None)
        ctypes.windll.winmm.mciSendStringW('play voz_robo wait', None, 0, None)
        ctypes.windll.winmm.mciSendStringW('close voz_robo', None, 0, None)
    except Exception:
        pass

def falar(texto):
    global mic_pausado, robo_falando, estado_atual_rosto
    nome_arquivo = None
    try:
        mic_pausado = True
        robo_falando = True
        estado_atual_rosto = "falando"


        pasta_audio = os.path.join(tempfile.gettempdir(), "indianos_remaster_audio")
        os.makedirs(pasta_audio, exist_ok=True)
        nome_arquivo = os.path.join(pasta_audio, f"audio_{int(time.time() * 1000)}.mp3")

        async def _gerar():


            communicate = edge_tts.Communicate(
                texto, voice="pt-BR-AntonioNeural", rate="-5%", pitch="-30Hz"
            )
            await communicate.save(nome_arquivo)

        asyncio.run(_gerar())
        t_som = threading.Thread(target=_tocar_audio_nativo, args=(nome_arquivo,), daemon=True)
        t_som.start()
        while t_som.is_alive() and robo_falando:
            time.sleep(0.05)
    except Exception as e:
        print(f"[Voz] Erro: {e}")
    finally:
        robo_falando = False
        mic_pausado = False
        estado_atual_rosto = "espera"
        atualizar_corpo("espera")
        if nome_arquivo and os.path.exists(nome_arquivo):
            try:
                os.remove(nome_arquivo)
            except Exception:
                pass

def mic_loop_continuo():
    global mic_pausado, estado_atual_rosto
    recognizer = sr.Recognizer()
    try:
        mic_device = sr.Microphone()
    except Exception as e:
        print(f"[Mic] Nenhum microfone encontrado: {e}")
        return
    with mic_device as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("\n[SISTEMA] Escuta ativa pronta.")
        while sistema_ativo:
            if mic_pausado or robo_falando:
                time.sleep(0.2)
                continue
            estado_atual_rosto = "ouvindo"
            mostrar_texto("OUVINDO... FALE SUA ORDEM")
            try:
                audio_data = recognizer.listen(source, timeout=1, phrase_time_limit=50)
                if mic_pausado or robo_falando or not sistema_ativo:
                    continue
                estado_atual_rosto = "processando"
                atualizar_corpo("processando")
                mostrar_texto("PROCESSANDO SUA FALA...")
                texto = recognizer.recognize_google(audio_data, language=IDIOMA)
                if len(texto) < 2:
                    continue
                mic_pausado = True
                threading.Thread(target=processar_resposta_texto, args=(texto,), daemon=True).start()
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                pass
            except Exception:
                time.sleep(0.2)


def definir_volume(porcentagem):
    porcentagem = max(0, min(100, porcentagem))
    if not PYCAW_DISPONIVEL:
        return False
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(porcentagem / 100.0, None)
        return True
    except Exception as e:
        print(f"[Volume] Erro: {e}")
        return False


CORES_ESTADO = {
    "ouvindo": "#FF6A00",
    "bloqueado": "#333333",
    "espera": "#00FFFF",
    "processando": "#FFFF00",
    "falando": "#00FF00",
}

def _desenhar_interface_estatica_seguro():
    turtle_titulo.clear()
    turtle_titulo.goto(0, 230)
    turtle_titulo.color("#00FFFF")
    turtle_titulo.write("INDIANOS REMASTER [SISTEMA ONLINE]", align="center", font=("Consolas", 11, "bold"))
    wn.update()

def _desenhar_tela_bloqueada_seguro():
    turtle_titulo.clear()
    turtle_titulo.goto(0, 230)
    turtle_titulo.color("#505050")
    turtle_titulo.write("[ CORE DORMENTE ]", align="center", font=("Consolas", 11, "bold"))
    turtle_status.clear()
    turtle_status.goto(0, -150)
    turtle_status.write(
        "BATA 2 PALMAS OU USE CTRL+SHIFT+PLUS PARA INICIALIZAR\nDIGITE COM CTRL+SHIFT+T QUANDO ATIVO",
        align="center", font=("Verdana", 10, "bold")
    )
    wn.update()

def _mostrar_texto_seguro(texto):
    turtle_status.clear()
    turtle_status.goto(0, 150)
    turtle_status.write(texto, align="center", font=("Verdana", 11, "bold"))
    wn.update()

def _renderizar_rosto_real(estado, pulso=False):
    turtle_rosto.clear()
    cor = CORES_ESTADO.get(estado, "#FFFFFF")
    raio_interno = 52 if pulso else 45
    raio_externo = raio_interno + 22

    turtle_rosto.color(cor)
    turtle_rosto.width(3)
    turtle_rosto.penup()
    turtle_rosto.goto(0, -raio_externo)
    turtle_rosto.setheading(0)
    turtle_rosto.pendown()
    turtle_rosto.circle(raio_externo)

    turtle_rosto.penup()
    turtle_rosto.goto(0, -raio_interno)
    turtle_rosto.pendown()
    turtle_rosto.begin_fill()
    turtle_rosto.circle(raio_interno)
    turtle_rosto.end_fill()
    wn.update()

def atualizar_corpo(estado):
    wn._root.after(0, lambda: _renderizar_rosto_real(estado))

def desenhar_interface_estatica():
    wn._root.after(0, _desenhar_interface_estatica_seguro)

def desenhar_tela_bloqueada():
    wn._root.after(0, _desenhar_tela_bloqueada_seguro)

def mostrar_texto(texto):
    wn._root.after(0, lambda: _mostrar_texto_seguro(texto))

def loop_animacao_rosto():
    pulso = False
    while True:
        time.sleep(0.15)
        estado = estado_atual_rosto
        pulso = (not pulso) if estado in ("ouvindo", "processando", "falando") else False
        try:
            wn._root.after(0, lambda e=estado, p=pulso: _renderizar_rosto_real(e, p))
        except RuntimeError:
            break


def _normalizar_texto_busca(texto):
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.lower()

_PALAVRAS_DIGITACAO = ("digita", "digite", "escreve", "escreva", "pesquisa",
                       "pesquise", "procura", "procure", "busca", "busque", "escrever")

def _comando_pede_digitacao(comando):
    comando_norm = _normalizar_texto_busca(comando)
    return any(p in comando_norm for p in _PALAVRAS_DIGITACAO)

_TIPOS_CLICAVEIS_UIA = ("Button", "MenuItem", "ListItem", "Hyperlink", "TabItem", "TreeItem", "CheckBox")

def localizar_elemento_ui_por_texto(comando_usuario):
    if not PYWINAUTO_DISPONIVEL:
        return None
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        app = Application(backend="uia").connect(handle=hwnd, timeout=2)
        janela = app.window(handle=hwnd)

        palavras_busca = [p for p in re.findall(r"\w+", _normalizar_texto_busca(comando_usuario)) if len(p) > 2]
        if not palavras_busca:
            return None

        melhor_controle, melhor_score = None, 0
        for controle in janela.descendants():
            try:
                if controle.element_info.control_type not in _TIPOS_CLICAVEIS_UIA:
                    continue
                nome = controle.window_text()
                if not nome or not controle.is_visible():
                    continue
                nome_norm = _normalizar_texto_busca(nome)
                score = sum(1 for p in palavras_busca if p in nome_norm)
                if score > melhor_score:
                    melhor_score, melhor_controle = score, controle
            except Exception:
                continue

        if melhor_controle and melhor_score > 0:
            rect = melhor_controle.rectangle()
            x, y = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
            print(f"[UIA] Achou '{melhor_controle.window_text()}' sem gastar API, em ({x},{y}).")
            return (x, y)
    except Exception as e:
        print(f"[UIA] Não deu pra usar UI Automation agora (app pode não suportar): {e}")
    return None

def ler_texto_tela_ocr(regiao=None):
    if not PYTESSERACT_DISPONIVEL:
        return None
    try:
        regiao = regiao or REGIAO_TELA_CHEIA
        with mss.mss() as sct:
            sct_img = sct.grab(regiao)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        return pytesseract.image_to_string(img, lang="por").strip() or None
    except Exception as e:
        print(f"[OCR] Erro ao ler tela: {e}")
        return None

def executar_analise_foto_unica():
    try:
        print("[VISÃO] Capturando imagem para análise didática/gestos...")
        mostrar_texto("CAPTURANDO FOTO...")
        atualizar_corpo("processando")
        with mss.mss() as sct:
            sct_img = sct.grab(REGIAO_IRIUN)
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size, level=9)
            foto_base64 = base64.b64encode(img_bytes).decode('utf-8')
        pergunta = (
            "Você é um professor particular de escola. Analise a imagem capturada. "
            "A imagem pode conter uma questão de livro didático com texto, gráficos, figuras geométricas ou fórmulas.\n\n"
            "REGRAS DE PRIORIDADE:\n"
            "1. Se houver um gesto de 'dedo do meio', retorne APENAS: DEDO_MEIO\n"
            "2. Se houver uma questão escolar ou conta matemática: repita a parte mais importante do enunciado, "
            "diga que entendeu e dê o resultado final resumido.\n"
            "3. Se a imagem contiver texto em outro idioma, traduza para o português.\n"
            "4. Se não houver nada visível, retorne APENAS: NADA."
        )
        texto_resposta = chamar_gemini({"contents": [{"parts": [
            {"text": pergunta},
            {"inlineData": {"mimeType": "image/png", "data": foto_base64}}
        ]}]}, timeout=40)

        if not texto_resposta:
            mostrar_texto("API SEM RESPOSTA - TENTE NOVAMENTE")
            return

        resultado = texto_resposta.strip()
        print(f"[SCANNER VISUAL]: {resultado}")
        resultado_upper = resultado.upper()
        if "DEDO_MEIO" in resultado_upper:
            mostrar_texto("Gesto ofensivo detectado!")
            falar("Ei, tira esse dedo da tela, moleque sem noção.")
        elif "NADA" in resultado_upper and len(resultado) < 10:
            mostrar_texto("Tudo limpo, nenhum conteúdo detectado.")
        else:
            mostrar_texto("Questão resolvida com sucesso!")
            falar(resultado)
    except Exception as e:
        print(f"[Análise Visão] Erro: {e}")
        mostrar_texto("Erro ao processar imagem.")

def gerar_imagem_ia(descricao_usuario):
    try:
        mostrar_texto("GERANDO IMAGEM...")
        atualizar_corpo("processando")
        nome_arquivo = f"img_{uuid.uuid4().hex[:8]}.png"
        prompt_encoded = urllib.parse.quote(descricao_usuario)
        url_imagem = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=1024&nologo=true"
        for tentativa in range(3):
            resposta_img = requests.get(url_imagem, timeout=90)
            if resposta_img.status_code == 200:
                with open(nome_arquivo, 'wb') as f:
                    f.write(resposta_img.content)
                mostrar_texto(f"IMAGEM SALVA: {nome_arquivo}")
                falar("Imagem gerada e salva com sucesso.")
                os.startfile(nome_arquivo)
                return
            elif resposta_img.status_code == 402:
                mostrar_texto(f"LIMITE DE REQUISIÇÕES, AGUARDANDO... ({tentativa + 1}/3)")
                time.sleep(30)
            else:
                falar("Não consegui gerar a imagem. Tente novamente.")
                return
        mostrar_texto("FALHOU APÓS 3 TENTATIVAS")
        falar("Não consegui gerar a imagem após várias tentativas.")
    except Exception as e:
        print(f"[Imagem] Erro: {e}")
        falar("Erro ao gerar imagem.")

def tirar_print(comando_usuario=""):
    ocultar_janela_temporariamente()
    try:


        if not _comando_pede_digitacao(comando_usuario):
            alvo_ui = localizar_elemento_ui_por_texto(comando_usuario)
            if alvo_ui:
                _executar_fluxo_controle(alvo_ui[0], alvo_ui[1])
                return

        with mss.mss() as sct:
            sct_img = sct.grab(REGIAO_TELA_CHEIA)
            largura, altura = sct_img.size
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size, level=9)
            foto_base64 = base64.b64encode(img_bytes).decode('utf-8')
        pergunta = (
            "Você é o Indianos Remaster. O usuário deu esta ordem: "
            f"'{comando_usuario}'.\n\n"
            "Olhe a imagem da tela com MUITO CUIDADO e identifique exatamente o "
            "elemento (ícone, botão, aba, campo de texto) que precisa ser clicado. "
            "Mire sempre no CENTRO EXATO desse elemento — nunca em cantos vazios "
            "da tela, nunca na barra de tarefas a menos que o pedido seja sobre "
            "ela.\n\n"
            "O canto superior esquerdo da imagem é (0,0) e o canto inferior "
            "direito é (1000,1000). Se a ordem pedir algo simples como 'abre o "
            "youtube', faça tudo: CLIQUE no campo certo e DIGITE o restante.\n\n"
            "Responda SOMENTE neste formato exato, sem markdown, sem texto extra:\n"
            "ACAO: CLIQUE[x,y] DIGITE[texto_ou_vazio]\n"
            "onde x e y são NORMALIZADOS de 0 a 1000 (não são pixels reais)."
        )
        texto_resposta = chamar_gemini({"contents": [{"parts": [
            {"text": pergunta},
            {"inlineData": {"mimeType": "image/png", "data": foto_base64}}
        ]}]}, timeout=40)

        if not texto_resposta:
            mostrar_texto("API SEM RESPOSTA - TENTE NOVAMENTE")
            return

        resultado = texto_resposta.strip()
        print(f"\n--- IA RESPONDEU ---\n{resultado}")
        if "ACAO:" in resultado and "CLIQUE[" in resultado:
            try:
                coords = resultado.split("CLIQUE[")[1].split("]")[0].replace(" ", "").split(",")
                x_norm, y_norm = int(float(coords[0])), int(float(coords[1]))
                x = int(x_norm / 1000 * largura)
                y = int(y_norm / 1000 * altura)
                texto = None
                if "DIGITE[" in resultado:
                    txt_extra = resultado.split("DIGITE[")[1].split("]")[0]
                    if txt_extra.strip():
                        texto = txt_extra
                _executar_fluxo_controle(x, y, texto)
            except Exception as e_parse:
                print(f"[Parser] Erro: {e_parse}")
    except Exception as e:
        print(f"[Visão] Erro: {e}")
    finally:
        restaurar_janela()

def arrastar_para(comando_usuario):
    ocultar_janela_temporariamente()
    try:
        with mss.mss() as sct:
            sct_img = sct.grab(REGIAO_TELA_CHEIA)
            largura, altura = sct_img.size
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size, level=9)
            foto_base64 = base64.b64encode(img_bytes).decode('utf-8')

        pergunta = (
            "Você é o Indianos Remaster. O usuário deu esta ordem de ARRASTAR "
            f"um item de um lugar pro outro na tela (drag and drop): '{comando_usuario}'.\n\n"
            "Identifique o ponto de ORIGEM (o item que vai ser arrastado) e o ponto "
            "de DESTINO (pra onde ele deve ir). O canto superior esquerdo da imagem "
            "é (0,0) e o inferior direito é (1000,1000).\n\n"
            "Responda SOMENTE neste formato exato, sem markdown, sem texto extra:\n"
            "ORIGEM[x,y] DESTINO[x,y]"
        )
        texto_resposta = chamar_gemini({"contents": [{"parts": [
            {"text": pergunta},
            {"inlineData": {"mimeType": "image/png", "data": foto_base64}}
        ]}]}, timeout=40)

        if not texto_resposta:
            falar("Não consegui analisar a tela pra arrastar.")
            return

        resultado = texto_resposta.strip()
        print(f"\n--- IA RESPONDEU (arrastar) ---\n{resultado}")

        origem_norm = resultado.split("ORIGEM[")[1].split("]")[0].replace(" ", "").split(",")
        destino_norm = resultado.split("DESTINO[")[1].split("]")[0].replace(" ", "").split(",")
        ox = int(float(origem_norm[0]) / 1000 * largura)
        oy = int(float(origem_norm[1]) / 1000 * altura)
        dx = int(float(destino_norm[0]) / 1000 * largura)
        dy = int(float(destino_norm[1]) / 1000 * altura)

        mouse.position = (ox, oy)
        time.sleep(0.3)
        mouse.press(Button.right)
        time.sleep(0.15)
        passos = 12
        for i in range(1, passos + 1):
            x = ox + (dx - ox) * i / passos
            y = oy + (dy - oy) * i / passos
            mouse.position = (int(x), int(y))
            time.sleep(0.03)
        time.sleep(0.15)
        mouse.release(Button.right)
        print(f"[Arrastar] ({ox},{oy}) -> ({dx},{dy})")
        falar("Pronto, arrastei.")
    except Exception as e:
        print(f"[Arrastar] Erro: {e}")
        falar("Tive um problema tentando arrastar isso.")
    finally:
        restaurar_janela()

TAMANHO_ZOOM = 90

def _refinar_coordenada_com_zoom(descricao, x_aprox, y_aprox, largura_tela, altura_tela):
    try:
        esquerda = max(0, x_aprox - TAMANHO_ZOOM)
        topo = max(0, y_aprox - TAMANHO_ZOOM)
        largura_crop = min(TAMANHO_ZOOM * 2, largura_tela - esquerda)
        altura_crop = min(TAMANHO_ZOOM * 2, altura_tela - topo)

        with mss.mss() as sct:
            regiao_crop = {"left": esquerda, "top": topo, "width": largura_crop, "height": altura_crop}
            sct_img = sct.grab(regiao_crop)
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size, level=9)
            foto_base64 = base64.b64encode(img_bytes).decode('utf-8')

        prompt = (
            f"Esta é uma imagem AMPLIADA (zoom) de uma região da tela, onde "
            f"'{descricao}' deveria estar visível, perto do centro. O canto "
            "superior esquerdo desta imagem é (0,0) e o inferior direito é "
            "(1000,1000). Responda SOMENTE com JSON, sem markdown:\n"
            '{"encontrado": true ou false, "x": <int 0-1000>, "y": <int 0-1000>}\n'
            "Mire exatamente no centro real do alvo."
        )
        texto_resposta = chamar_gemini({"contents": [{"parts": [
            {"text": prompt},
            {"inlineData": {"mimeType": "image/png", "data": foto_base64}}
        ]}]}, timeout=20)
        if not texto_resposta:
            return x_aprox, y_aprox

        texto_limpo = texto_resposta.strip().replace("```json", "").replace("```", "").strip()
        resultado = json.loads(texto_limpo)
        if not resultado.get("encontrado"):
            return x_aprox, y_aprox

        x_refinado = esquerda + int(resultado["x"] / 1000 * largura_crop)
        y_refinado = topo + int(resultado["y"] / 1000 * altura_crop)
        print(f"[Refinamento] '{descricao}' ({x_aprox},{y_aprox}) -> ({x_refinado},{y_refinado})")
        return x_refinado, y_refinado
    except Exception as e:
        print(f"[Refinamento] Erro (usando coordenada aproximada): {e}")
        return x_aprox, y_aprox

def jogar_xadrez(comando_usuario):
    texto_min = comando_usuario.lower()
    if "branca" in texto_min:
        cor = "branca"
    elif "preta" in texto_min:
        cor = "preta"
    else:
        cor = "que estiver com o turno atual, a julgar pelo estado do jogo"

    ocultar_janela_temporariamente()
    try:
        with mss.mss() as sct:
            sct_img = sct.grab(REGIAO_TELA_CHEIA)
            largura, altura = sct_img.size
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size, level=9)
            foto_base64 = base64.b64encode(img_bytes).decode('utf-8')

        pergunta = (
            "Você está vendo um print de um jogo de xadrez (tipo Chess Titans do "
            f"Windows). O usuário pediu pra jogar com as peças da cor {cor}.\n\n"
            "Analise a posição atual do tabuleiro com cuidado — identifique onde "
            "cada peça está — e decida uma jogada válida e sensata pra essa cor.\n\n"
            "Esse jogo NÃO aceita arrastar peça: o movimento é feito clicando "
            "PRIMEIRO na peça que vai mover, e DEPOIS na casa de destino (dois "
            "cliques separados, não um arrasto).\n\n"
            "O canto superior esquerdo da imagem é (0,0) e o inferior direito é "
            "(1000,1000). Responda SOMENTE neste formato exato, sem markdown:\n"
            "PECA[x,y] DESTINO[x,y] JOGADA[descrição curta da jogada]"
        )
        texto_resposta = chamar_gemini({"contents": [{"parts": [
            {"text": pergunta},
            {"inlineData": {"mimeType": "image/png", "data": foto_base64}}
        ]}]}, timeout=40)

        if not texto_resposta:
            falar("Não consegui analisar o tabuleiro agora.")
            return

        resultado = texto_resposta.strip()
        print(f"\n--- IA RESPONDEU (xadrez) ---\n{resultado}")

        peca_norm = resultado.split("PECA[")[1].split("]")[0].replace(" ", "").split(",")
        destino_norm = resultado.split("DESTINO[")[1].split("]")[0].replace(" ", "").split(",")
        px = int(float(peca_norm[0]) / 1000 * largura)
        py = int(float(peca_norm[1]) / 1000 * altura)
        dx = int(float(destino_norm[0]) / 1000 * largura)
        dy = int(float(destino_norm[1]) / 1000 * altura)

        jogada_desc = ""
        if "JOGADA[" in resultado:
            jogada_desc = resultado.split("JOGADA[")[1].split("]")[0]


        px, py = _refinar_coordenada_com_zoom("a peça a ser movida", px, py, largura, altura)
        dx, dy = _refinar_coordenada_com_zoom("a casa de destino da jogada", dx, dy, largura, altura)


        mouse.position = (px, py)
        time.sleep(0.3)
        mouse.click(Button.right, 1)
        time.sleep(0.4)


        mouse.position = (dx, dy)
        time.sleep(0.2)
        mouse.click(Button.right, 1)

        print(f"[Xadrez] Peça ({px},{py}) -> Destino ({dx},{dy}) | {jogada_desc}")
        falar(f"Jogada feita.{(' ' + jogada_desc) if jogada_desc else ''}")
    except Exception as e:
        print(f"[Xadrez] Erro: {e}")
        falar("Tive um problema tentando fazer essa jogada.")
    finally:
        restaurar_janela()


PASTA_CODIGOS = os.path.join(os.path.expanduser("~"), "Desktop", "codigos_indianos")
os.makedirs(PASTA_CODIGOS, exist_ok=True)


CAMINHO_NOTEPADPP = r"C:\Program Files\Notepad++\notepad++.exe"

def gerar_e_rodar_codigo(comando_usuario):
    editor_pedido = "notepad++" if "notepad" in comando_usuario.lower() else "idle"

    pergunta = (
        f"Escreva um código Python que faça o seguinte: '{comando_usuario}'\n\n"
        "Responda SOMENTE com o código Python puro, pronto pra rodar — "
        "sem explicação nenhuma, sem markdown, sem ```python, só o código."
    )
    codigo = chamar_gemini({"contents": [{"parts": [{"text": pergunta}]}]}, timeout=30)
    if not codigo:
        falar("Não consegui gerar o código agora.")
        return

    codigo = codigo.strip()
    for marcador in ["```python", "```py", "```"]:
        codigo = codigo.replace(marcador, "")
    codigo = codigo.strip()

    nome_arquivo = f"codigo_{int(time.time())}.py"
    caminho = os.path.join(PASTA_CODIGOS, nome_arquivo)
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(codigo)
    except Exception as e:
        print(f"[Programar] Erro ao salvar arquivo: {e}")
        falar("Gerei o código mas não consegui salvar o arquivo.")
        return


    try:
        if editor_pedido == "notepad++" and os.path.exists(CAMINHO_NOTEPADPP):
            subprocess.Popen([CAMINHO_NOTEPADPP, caminho])
        else:
            subprocess.Popen([sys.executable, "-m", "idlelib.idle", caminho])
    except Exception as e:
        print(f"[Programar] Não consegui abrir o editor (código já foi salvo em {caminho}): {e}")

    if os.environ.get("INDIANOS_RODAR_CODIGO") != "1":
        falar("Escrevi o código e abri no editor. A execução automática está desligada por segurança.")
        return
    falar("Escrevi o código, vou rodar agora pra ver se tem erro.")
    try:
        resultado = subprocess.run(
            [sys.executable, caminho],
            capture_output=True, text=True, timeout=15
        )
        if resultado.returncode == 0:
            saida = resultado.stdout.strip() or "(sem nada impresso na tela)"
            mostrar_texto(f"Rodou sem erro. Saída: {saida[:300]}")
            falar(f"Rodou sem erro. {('Saída: ' + saida[:200]) if resultado.stdout.strip() else 'Não imprimiu nada na tela.'}")
        else:
            erro = resultado.stderr.strip()
            mostrar_texto(f"Erro: {erro[-300:]}")
            falar(f"Deu erro rodando. {erro.splitlines()[-1] if erro else ''}")
            print(f"[Programar] Erro completo:\n{erro}")
    except subprocess.TimeoutExpired:
        falar("O código ficou rodando mais de 15 segundos, então cortei — pode ser um loop infinito.")
    except Exception as e:
        print(f"[Programar] Erro ao rodar: {e}")
        falar("Tive um problema tentando rodar o código.")


def _iniciar_driver_zap():
    global driver_zap
    try:
        if driver_zap is not None:
            return True
        print("[ZAP] Abrindo Edge com perfil dedicado...")
        mostrar_texto("ABRINDO WHATSAPP WEB...")
        falar("Abrindo WhatsApp Web.")
        options = Options()


        options.add_argument(r"--user-data-dir=C:\Users\%USERNAME%\IndianosEdgeProfile".replace(
            "%USERNAME%", os.environ.get("USERNAME", "Usuario")))
        options.add_argument("--profile-directory=Default")
        edgedriver_path = EdgeChromiumDriverManager().install()
        driver_zap = webdriver.Edge(service=Service(edgedriver_path), options=options)
        driver_zap.maximize_window()
        driver_zap.get("https://web.whatsapp.com")
        WebDriverWait(driver_zap, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="3"]'))
        )
        print("[ZAP] WhatsApp Web conectado!")
        mostrar_texto("WHATSAPP CONECTADO!")
        falar("WhatsApp conectado!")
        return True
    except Exception as e:
        print(f"[ZAP] Erro: {e}")
        falar("Erro ao abrir WhatsApp Web.")
        driver_zap = None
        return False

def _extrair_info_zap(texto_usuario):
    try:
        pergunta = (
            f"Extraia do texto abaixo o NOME DO CONTATO e a MENSAGEM a ser enviada no WhatsApp.\n"
            f"Texto: '{texto_usuario}'\n\n"
            "Responda SOMENTE neste formato JSON sem nenhum texto extra:\n"
            '{"contato": "nome aqui", "mensagem": "mensagem aqui"}'
        )
        texto_ia = chamar_gemini({"contents": [{"parts": [{"text": pergunta}]}]}, timeout=15)
        if not texto_ia:
            return "", ""
        texto_ia = texto_ia.strip().replace("```json", "").replace("```", "").strip()
        dados = json.loads(texto_ia)
        return dados.get("contato", ""), dados.get("mensagem", "")
    except Exception as e:
        print(f"[ZAP Parser] Erro: {e}")
        return "", ""

def _resolver_mensagem_zap(texto_usuario, nome_contato, mensagem_bruta):
    if any(p in texto_usuario for p in ["exatamente", "exato", "literalmente", "só isso", "apenas isso"]):
        return mensagem_bruta
    try:
        pergunta = (
            f"Você é o Indianos Remaster. O usuário quer mandar uma mensagem pro contato '{nome_contato}' no WhatsApp.\n"
            f"Mensagem base: '{mensagem_bruta}'\n"
            f"Pedido completo: '{texto_usuario}'\n\n"
            "Elabore a mensagem de forma natural, mantendo o tom pedido. "
            "Retorne APENAS o texto final da mensagem, sem explicações."
        )
        texto_resposta = chamar_gemini({"contents": [{"parts": [{"text": pergunta}]}]}, timeout=15)
        return texto_resposta.strip() if texto_resposta else mensagem_bruta
    except Exception:
        return mensagem_bruta

def enviar_whatsapp(texto_usuario):
    try:
        mostrar_texto("PROCESSANDO MENSAGEM ZAP...")
        atualizar_corpo("processando")
        nome_contato, mensagem_bruta = _extrair_info_zap(texto_usuario)
        if not nome_contato or not mensagem_bruta:
            texto_min = texto_usuario.lower()
            for gatilho in ["manda zap pro", "zap pro", "manda pro", "whatsapp pro"]:
                if gatilho in texto_min:
                    resto = texto_min.split(gatilho)[1].strip()
                    partes = resto.split(" ", 1)
                    nome_contato = partes[0].capitalize()
                    mensagem_bruta = partes[1] if len(partes) > 1 else "oi"
                    break
        if not nome_contato or not mensagem_bruta:
            falar("Não entendi pra quem mandar ou o que mandar.")
            return
        mensagem_final = _resolver_mensagem_zap(texto_usuario, nome_contato, mensagem_bruta)
        print(f"[ZAP] Contato: {nome_contato} | Mensagem: {mensagem_final}")
        if not _iniciar_driver_zap():
            return
        falar(f"Mandando mensagem pro {nome_contato} no WhatsApp.")
        mostrar_texto(f"MANDANDO ZAP PRO {nome_contato.upper()}...")
        search_box = WebDriverWait(driver_zap, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="3"]'))
        )
        search_box.click()
        time.sleep(0.5)
        search_box.send_keys(Keys.CONTROL + "a")
        search_box.send_keys(Keys.DELETE)
        search_box.send_keys(nome_contato)
        time.sleep(2)
        primeiro_resultado = WebDriverWait(driver_zap, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="cell-frame-container"]'))
        )
        primeiro_resultado.click()
        time.sleep(1)
        caixa_msg = WebDriverWait(driver_zap, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="10"]'))
        )
        caixa_msg.click()
        caixa_msg.send_keys(mensagem_final)
        time.sleep(0.5)
        caixa_msg.send_keys(Keys.ENTER)
        time.sleep(1)
        print(f"[ZAP] Mensagem enviada pro {nome_contato}!")
        mostrar_texto(f"ZAP ENVIADO PRO {nome_contato.upper()}!")
        falar(f"Mensagem enviada pro {nome_contato} com sucesso!")
        registrar_auditoria("WHATSAPP ENVIADO", f"Para: {nome_contato} | Msg: {mensagem_final}")
    except Exception as e:
        print(f"[ZAP] Erro: {e}")
        falar("Erro ao enviar mensagem.")
        mostrar_texto("ERRO AO ENVIAR ZAP")


def escrever_no_bloco(conteudo):
    try:
        with open(ARQUIVO_NOTAS, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 40}\n[{time.strftime('%d/%m/%Y %H:%M:%S')}]\n{conteudo}\n")
        subprocess.Popen(f'notepad "{ARQUIVO_NOTAS}"')
    except Exception as e:
        print(f"[Notas] Erro: {e}")

def apagar_bloco():
    try:
        subprocess.Popen("taskkill /f /im notepad.exe", shell=True)
        time.sleep(0.3)
        if os.path.exists(ARQUIVO_NOTAS):
            os.remove(ARQUIVO_NOTAS)
    except Exception as e:
        print(f"[Notas] Erro ao apagar: {e}")

GATILHOS_ESCRITA_LITERAL = [
    "escreve exatamente", "escreva exatamente", "escreve literalmente",
    "escreva literalmente", "anota exatamente", "escreve exato", "escreva exato",
]

def processar_comando_escrever(texto, texto_min):
    for gatilho in GATILHOS_ESCRITA_LITERAL:
        if gatilho in texto_min:
            idx = texto_min.find(gatilho) + len(gatilho)
            conteudo = texto[idx:].strip(" :.")
            escrever_no_bloco(conteudo)
            falar(f"Escrevi exatamente: {conteudo}")
            return

    pedido_ia = (
        f"O usuário pediu para escrever isto no bloco de notas: '{texto}'. "
        "Gere APENAS o conteúdo final e completo que deve ser escrito no bloco "
        "de notas, sem introduções, sem explicações e sem comentários — só o "
        "conteúdo puro e pronto, exatamente como deve aparecer no arquivo."
    )
    conteudo_gerado = responder_usuario(pedido_ia)
    escrever_no_bloco(conteudo_gerado)
    falar("Escrevi no bloco de notas.")


def controlar_leds(texto_min):
    if not arduino:
        return
    if any(p in texto_min for p in ["acender", "liga", "ligar"]):
        arduino.write(b"APAGAR\n")
        print("Comando ACENDER enviado")
    elif any(p in texto_min for p in ["apagar", "desligar", "apaga"]):
        arduino.write(b"ACENDER\n")
        print("Comando APAGAR enviado")

def fechar_sistema_e_voltar_espera():
    global sistema_ativo, mic_pausado
    with lock_sistema:
        sistema_ativo = False
    mic_pausado = False
    desenhar_tela_bloqueada()
    atualizar_corpo("bloqueado")
    threading.Thread(target=escutar_palmas_loop, daemon=True).start()

def verificar_protocolo_apoio(texto):
    termos_crise = [
        "me matar", "suicidio", "suicídio", "quero morrer", "desistir da vida",
        "fim da minha vida", "tirar minha vida", "me cortar", "automutilacao"
    ]
    if any(termo in texto.lower() for termo in termos_crise):
        return (
            "Se você ou alguém que você conhece está passando por um momento difícil, "
            "saiba que você não está sozinho. Existe apoio disponível. No Brasil, ligue para o "
            "Centro de Valorização da Vida pelo número 188 ou acesse cvv.org.br para atendimento gratuito e 24h."
        )
    return None

def _extrair_nome_apos_ancora(texto_min, ancora="arquivo"):
    idx = texto_min.rfind(ancora)
    if idx == -1:
        return ""
    resto = texto_min[idx + len(ancora):]
    for conector in [" chamado ", " que se chama ", " com o nome ", " de nome "]:
        resto = resto.replace(conector, " ")
    return resto.strip(" :.,")

_VERBOS_APAGAR = ["apag", "delet", "exclu", "remov"]
_VERBOS_MOVER = ["mov", "manda", "leva", "transfer"]

def _eh_comando_apagar_arquivo(texto_min):
    return "arquivo" in texto_min and any(v in texto_min for v in _VERBOS_APAGAR)

def _eh_comando_mover_arquivo(texto_min):
    return "arquivo" in texto_min and any(v in texto_min for v in _VERBOS_MOVER)

def processar_resposta_texto(texto):
    global mic_pausado, estado_atual_rosto
    mostrar_texto(f"Você: '{texto}'")

    mensagem_apoio = verificar_protocolo_apoio(texto)
    if mensagem_apoio:
        estado_atual_rosto = "espera"
        atualizar_corpo("espera")
        mostrar_texto("CANAL DE APOIO")
        falar(mensagem_apoio)
        mic_pausado = False
        return

    texto_min = texto.lower()
    controlar_leds(texto_min)


    if any(g in texto_min for g in ["manda zap", "manda whatsapp", "envia zap",
                                     "manda mensagem no zap", "manda no whatsapp",
                                     "zap pro", "whatsapp pro"]):
        threading.Thread(target=enviar_whatsapp, args=(texto,), daemon=True).start()
        mic_pausado = False
        return


    elif "celular" in texto_min or re.search(r"\bcel\b", texto_min):
        if any(p in texto_min for p in ["liga a tela", "acorda", "ativa a tela"]):
            erro = celular_ligar_tela()
            falar("Não consegui ligar a tela do celular." if erro else "Tela do celular ligada.")
        elif any(p in texto_min for p in ["desbloqueia", "desbloquear", "poe a senha", "põe a senha", "coloca a senha"]):
            erro = celular_desbloquear()
            falar("Não consegui desbloquear o celular." if erro else "Celular desbloqueado.")
            registrar_auditoria("CELULAR - DESBLOQUEAR")
        elif any(p in texto_min for p in ["desliga o", "desligar o"]):
            erro = celular_desligar()
            falar(f"Não consegui desligar o celular: {erro}" if erro else "Desligando o celular.")
            registrar_auditoria("CELULAR - DESLIGAR")
        elif any(p in texto_min for p in ["liga o", "ligar o"]):
            falar("Não dá pra ligar o celular pelo A D B — com ele desligado, o computador não consegue se comunicar com ele de jeito nenhum. Isso só seria possível com um botão físico automatizado, por exemplo usando o Arduino.")
        elif any(p in texto_min for p in ["rola pra baixo", "desce a tela", "rola a tela"]):
            erro = celular_rolar("baixo")
            falar("Não consegui rolar a tela do celular." if erro else "Rolando a tela do celular.")
        elif any(p in texto_min for p in ["rola pra cima", "sobe a tela"]):
            erro = celular_rolar("cima")
            falar("Não consegui rolar a tela do celular." if erro else "Rolando a tela do celular.")
        elif any(p in texto_min for p in ["proximo video", "próximo vídeo", "passa o video", "passa o vídeo", "pula o video", "pula o vídeo"]):
            erro = celular_video_seguinte()
            falar("Não consegui passar o vídeo." if erro else "Passando o vídeo.")
        elif any(p in texto_min for p in ["video anterior", "vídeo anterior", "volta o video", "volta o vídeo"]):
            erro = celular_video_anterior()
            falar("Não consegui voltar o vídeo." if erro else "Voltando o vídeo.")
        elif any(p in texto_min for p in ["rola sozinho", "rolar sozinho", "fica rolando", "rola automatico", "rola automático"]):
            numeros = re.findall(r"\d+", texto_min)
            intervalo = int(numeros[0]) if numeros else 6
            erro = celular_iniciar_auto_rolar(intervalo)
            falar(erro if erro else f"Beleza, vou passar os vídeos sozinha a cada {intervalo} segundos. Fale 'para de rolar sozinho' pra eu parar.")
        elif any(p in texto_min for p in ["para de rolar", "parar de rolar", "para de rolar sozinho"]):
            celular_parar_auto_rolar()
            falar("Parei de rolar sozinha.")
        elif "volta" in texto_min:
            celular_voltar()
            falar("Voltando no celular.")
        elif any(p in texto_min for p in ["home", "tela inicial"]):
            celular_home()
            falar("Indo pra tela inicial do celular.")
        elif "print" in texto_min:
            caminho, erro = celular_tirar_print()
            if erro:
                falar(f"Não consegui tirar print do celular: {erro}")
            else:
                falar("Print do celular tirado.")
                registrar_auditoria("CELULAR - PRINT DE TELA", caminho)
        elif any(p in texto_min for p in ["wifi", "wi-fi"]):
            ligar = not any(p in texto_min for p in ["desliga", "desativa"])
            erro = celular_wifi(ligar)
            falar("Não consegui mexer no Wi-Fi do celular." if erro else f"Wi-Fi do celular {'ligado' if ligar else 'desligado'}.")
            registrar_auditoria(f"CELULAR - WIFI {'LIGADO' if ligar else 'DESLIGADO'}")
        elif any(p in texto_min for p in ["bluetooth"]):
            ligar = not any(p in texto_min for p in ["desliga", "desativa"])
            erro = celular_bluetooth(ligar)
            falar("Não consegui mexer no Bluetooth do celular." if erro else f"Bluetooth do celular {'ligado' if ligar else 'desligado'}.")
            registrar_auditoria(f"CELULAR - BLUETOOTH {'LIGADO' if ligar else 'DESLIGADO'}")
        elif any(p in texto_min for p in ["abre", "abrir"]):
            nome_app = texto_min
            for termo in ["abre", "abrir", "no celular", "do celular", "no cel", "do cel"]:
                nome_app = nome_app.replace(termo, "")
            nome_app = nome_app.strip()
            erro = celular_abrir_app(nome_app)
            if erro:
                falar(f"Não consegui abrir no celular: {erro}")
            else:
                falar(f"Abrindo {nome_app} no celular.")
                registrar_auditoria("CELULAR - ABRIR APP", nome_app)
        elif any(p in texto_min for p in ["digita", "digite", "escreve"]):
            threading.Thread(target=_digitar_no_celular_thread, args=(texto,), daemon=True).start()
        elif any(p in texto_min for p in ["clica", "clique", "toca"]):
            falar("Deixa comigo, vou olhar a tela do celular.")
            threading.Thread(target=_clicar_no_celular_thread, args=(texto,), daemon=True).start()
        else:
            falar("Não entendi o que fazer no celular.")
        mic_pausado = False
        return


    elif any(g in texto_min for g in ["clica", "clique", "digite", "digita", "print"]):
        falar("Deixa comigo, vou analisar a tela para agir.")
        tirar_print(texto)
        mic_pausado = False
        return


    elif any(g in texto_min for g in ["arrasta", "arraste"]):
        falar("Deixa comigo, vou arrastar isso.")
        threading.Thread(target=arrastar_para, args=(texto,), daemon=True).start()
        mic_pausado = False
        return


    elif any(g in texto_min for g in ["mova a peca", "mova a peça", "move a peca", "move a peça",
                                       "faz uma jogada", "faça uma jogada", "joga de xadrez",
                                       "jogada de xadrez"]):
        threading.Thread(target=jogar_xadrez, args=(texto,), daemon=True).start()
        mic_pausado = False
        return


    elif any(g in texto_min for g in ["programa", "programe", "codifica", "codifique",
                                       "escreve um codigo", "escreve um código",
                                       "cria um codigo", "cria um código", "faz um codigo",
                                       "faz um código"]):
        threading.Thread(target=gerar_e_rodar_codigo, args=(texto,), daemon=True).start()
        mic_pausado = False
        return


    elif any(g in texto_min for g in ["camera", "rosto", "verificar"]):
        falar("Deixa comigo, vou analisar a câmera para agir.")
        executar_analise_foto_unica()
        mic_pausado = False
        return


    elif "volume" in texto_min:
        numeros = re.findall(r"\d+", texto_min)
        if numeros:
            alvo = int(numeros[0])
            if definir_volume(alvo):
                falar(f"Volume ajustado para {alvo} por cento.")
            else:
                falar("Não consegui ajustar o volume. Verifique se o pycaw está instalado.")
        else:
            falar("Não entendi para quantos por cento ajustar o volume.")
        mic_pausado = False
        return


    elif any(p in texto_min for p in ["maximiza", "maximizar"]):
        keyboard.send('windows+up')
        falar("Maximizando.")
        mic_pausado = False
        return
    elif any(p in texto_min for p in ["minimiza", "minimizar"]):
        keyboard.send('windows+down')
        falar("Minimizando.")
        mic_pausado = False
        return
    elif any(p in texto_min for p in ["fecha a aba", "fechar aba", "fecha aba", "fechar a aba"]):
        teclado.press(Key.ctrl)
        teclado.press('w')
        teclado.release('w')
        teclado.release(Key.ctrl)
        falar("Aba fechada.")
        mic_pausado = False
        return


    elif any(p in texto_min for p in ["desligar o pc", "desligar o computador", "desliga o pc", "desliga o computador"]):
        falar("Desligando o computador em dez segundos. Diga cancelar desligamento para impedir.")
        subprocess.run("shutdown /s /t 10", shell=True)
        registrar_auditoria("DESLIGAR PC", "comando por voz")
        mic_pausado = False
        return
    elif any(p in texto_min for p in ["reiniciar o pc", "reiniciar o computador", "reinicia o pc", "reinicia o computador"]):
        falar("Reiniciando o computador em dez segundos.")
        subprocess.run("shutdown /r /t 10", shell=True)
        registrar_auditoria("REINICIAR PC", "comando por voz")
        mic_pausado = False
        return
    elif any(p in texto_min for p in ["cancela desligamento", "cancelar desligamento", "não desliga", "nao desliga"]):
        subprocess.run("shutdown /a", shell=True)
        falar("Desligamento cancelado.")
        mic_pausado = False
        return


    elif any(p in texto_min for p in ["dispositivos conectados", "dispositivos usb",
                                       "o que ta conectado", "o que esta conectado",
                                       "conectado no pc", "conectado no computador"]):
        dispositivos = listar_dispositivos_usb()
        if dispositivos:
            falar(f"Dispositivos conectados: {', '.join(dispositivos[:8])}.")
        else:
            falar("Não consegui listar os dispositivos USB agora.")
        mic_pausado = False
        return


    elif any(p in texto_min for p in ["log de auditoria", "ultimas acoes", "últimas ações",
                                       "o que voce fez", "o que você fez"]):
        ultimas = ler_ultimas_auditorias(5)
        if ultimas:
            falar("Últimas ações registradas: " + ". ".join(ultimas))
        else:
            falar("Nenhuma ação sensível registrada ainda.")
        mic_pausado = False
        return


    elif _eh_comando_apagar_arquivo(texto_min):
        nome = _extrair_nome_apos_ancora(texto_min)
        ok, caminho = excluir_arquivo_por_nome(nome)
        if ok:
            falar(f"Arquivo {os.path.basename(caminho)} enviado para a lixeira.")
        else:
            falar(f"Não encontrei nenhum arquivo parecido com '{nome}' nas pastas conhecidas.")
        mic_pausado = False
        return
    elif _eh_comando_mover_arquivo(texto_min):
        partes = _extrair_nome_apos_ancora(texto_min)
        if " para " in partes:
            nome, destino = partes.split(" para ", 1)
        else:
            nome, destino = partes, ""
        nome = nome.strip()
        destino = destino.strip() or os.path.join(os.path.expanduser("~"), "Desktop")
        ok, caminho = mover_arquivo_por_nome(nome, destino)
        if ok:
            falar(f"Movi o arquivo para {destino}.")
        else:
            falar("Não encontrei esse arquivo para mover.")
        mic_pausado = False
        return


    elif any(g in texto_min for g in ["anota", "anote", "escreva", "escreve", "salva no bloco", "escreve no bloco"]):
        estado_atual_rosto = "processando"
        atualizar_corpo("processando")
        processar_comando_escrever(texto, texto_min)
        mic_pausado = False
        return


    elif any(g in texto_min for g in ["gera", "cria", "crie", "criar", "desenha", "gerar imagem", "cria uma imagem"]):
        gerar_imagem_ia(texto_min)
        falar("Criando imagem.")
        mic_pausado = False
        return

    elif any(g in texto_min for g in ["apaga nota", "limpa bloco", "apaga bloco"]):
        apagar_bloco()
        falar("Bloco de notas limpo.")
        mic_pausado = False
        return


    elif "pesquisar" in texto_min or "buscar" in texto_min:
        termo_busca = texto_min
        for gatilho in ["pesquisar sobre", "pesquisar", "busca por", "buscar"]:
            termo_busca = termo_busca.replace(gatilho, "")
        termo_busca = termo_busca.strip().replace("navegador", "")
        if termo_busca:
            falar(f"Pesquisando sobre {termo_busca} no seu navegador.")
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(termo_busca)}")
        else:
            falar("Abrindo a página inicial do Google.")
            webbrowser.open("https://www.google.com")
        mic_pausado = False
        return


    elif any(p in texto_min for p in ["abrir arquivo", "abrir programa", "abrir"]):
        alvo = texto_min.replace("abrir arquivo", "").replace("abrir programa", "").replace("abrir", "").strip()
        if alvo and re.search(r'[&|<>^%"`\n\r]', alvo):
            falar("Esse nome tem caracteres que não posso usar para abrir.")
        elif alvo:
            try:
                falar(f"Tentando abrir {alvo}.")
                subprocess.Popen(["cmd", "/c", "start", "", alvo])
            except Exception:
                falar("Não consegui abrir esse arquivo específico.")
        mic_pausado = False
        return


    elif any(p in texto_min for p in ["desligar sistema", "dormir", "encerrar"]):
        falar("Entendido. Retornando ao modo de segurança.")
        fechar_sistema_e_voltar_espera()
        return


    elif any(p in texto_min for p in ["mova o mouse", "mova", "mouse", "mause"]):
        falar("movendo")
        cord = texto_min.replace("mova o mouse", "").replace("mova", "").replace("mouse", "").replace("mause", "")
        mexer(cord)
        return


    estado_atual_rosto = "processando"
    atualizar_corpo("processando")
    resposta_ia = responder_usuario(texto)
    mostrar_texto(resposta_ia)
    falar(resposta_ia)

def mexer(cord):
    global mic_pausado
    try:
        pergunta = (
            f"Analise esta frase do usuário: '{cord}'\n"
            "Responda APENAS com uma das letras abaixo, sem pontuação, sem explicações e sem aspas:\n"
            "D - Se for para a direita\n"
            "E - Se for para a esquerda\n"
            "B - Se for para baixo\n"
            "C - Se for para cima\n"
            "CP - Se for para clicar ou apertar"
        )
        texto_resposta = chamar_gemini({"contents": [{"parts": [{"text": pergunta}]}]}, timeout=40)
        if not texto_resposta:
            return
        linha = texto_resposta.strip().upper()
        print(f"[SCANNER VISUAL]: Comando detectado -> {linha}")
        if linha == 'C':
            mouse.move(0, -VELOCIDADE_CURSOR)
        elif linha == 'B':
            mouse.move(0, VELOCIDADE_CURSOR)
        elif linha == 'E':
            mouse.move(-VELOCIDADE_CURSOR, 0)
        elif linha == 'D':
            mouse.move(VELOCIDADE_CURSOR, 0)
        elif linha == 'CP':
            mouse.click(button='left')
    except Exception as e:
        print(f"[Erro no Mouse] {e}")
    finally:
        mic_pausado = False


def listar_dispositivos_usb():
    try:
        comando = (
            'powershell -NoProfile -Command "Get-PnpDevice -PresentOnly | '
            "Where-Object {$_.InstanceId -like '*USB*'} | "
            'Select-Object -ExpandProperty FriendlyName"'
        )
        resultado = subprocess.run(comando, shell=True, capture_output=True, text=True, timeout=15)
        return [l.strip() for l in resultado.stdout.splitlines() if l.strip()]
    except Exception as e:
        print(f"[USB] Erro ao listar dispositivos: {e}")
        return []

PASTA_PERFIL_USUARIO = os.path.expanduser("~")

def localizar_arquivo(nome_arquivo):
    alvo = nome_arquivo.strip().lower()
    if not alvo:
        print("[Arquivos] Nome de arquivo vazio depois de extrair do comando.")
        return None

    for pasta in PASTAS_BUSCA_ARQUIVOS:
        if not os.path.isdir(pasta):
            continue
        for raiz, _, arquivos in os.walk(pasta):
            for arq in arquivos:
                if alvo in arq.lower():
                    print(f"[Arquivos] '{alvo}' encontrado em: {os.path.join(raiz, arq)}")
                    return os.path.join(raiz, arq)

    print(f"[Arquivos] Não achou nas pastas comuns, expandindo busca pro perfil inteiro...")
    for raiz, dirs, arquivos in os.walk(PASTA_PERFIL_USUARIO):

        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                   ('AppData', 'NTUSER.DAT', '$Recycle.Bin')]
        for arq in arquivos:
            if alvo in arq.lower():
                print(f"[Arquivos] '{alvo}' encontrado (busca ampla) em: {os.path.join(raiz, arq)}")
                return os.path.join(raiz, arq)

    print(f"[Arquivos] '{alvo}' não encontrado em lugar nenhum do perfil do usuário.")
    return None

def excluir_arquivo_por_nome(nome_arquivo):
    caminho = localizar_arquivo(nome_arquivo)
    if not caminho:
        return False, None
    try:
        if SEND2TRASH_DISPONIVEL:
            send2trash(caminho)
        else:
            os.remove(caminho)
        registrar_auditoria("EXCLUIR ARQUIVO", caminho)
        return True, caminho
    except Exception as e:
        print(f"[Arquivos] Erro ao excluir '{caminho}': {e}")
        return False, caminho

def mover_arquivo_por_nome(nome_arquivo, pasta_destino):
    caminho = localizar_arquivo(nome_arquivo)
    if not caminho:
        return False, None
    try:
        os.makedirs(pasta_destino, exist_ok=True)
        destino_final = os.path.join(pasta_destino, os.path.basename(caminho))
        shutil.move(caminho, destino_final)
        registrar_auditoria("MOVER ARQUIVO", f"{caminho} -> {destino_final}")
        return True, destino_final
    except Exception as e:
        print(f"[Arquivos] Erro ao mover '{caminho}': {e}")
        return False, caminho


def _carregar_memoria_local():
    if os.path.exists(ARQUIVO_MEMORIA_LOCAL):
        try:
            with open(ARQUIVO_MEMORIA_LOCAL, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def _salvar_memoria_local(historico):
    try:
        with open(ARQUIVO_MEMORIA_LOCAL, "w", encoding="utf-8") as f:
            json.dump(historico[-200:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Memória] Falha ao salvar: {e}")

def salvar_mensagem_memoria(role, texto):
    entrada = {"role": role, "texto": texto, "ts": int(time.time() * 1000)}
    historico = _carregar_memoria_local()
    historico.append(entrada)
    _salvar_memoria_local(historico)

def carregar_historico_memoria():
    historico_local = _carregar_memoria_local()[-QTD_MENSAGENS_LEMBRADAS:]
    contents = []
    for m in historico_local:
        papel = "model" if m.get("role") == "ia" else "user"
        contents.append({"role": papel, "parts": [{"text": m.get("texto", "")}]})
    return contents

def responder_usuario(texto_usuario):
    try:
        historico = carregar_historico_memoria()
        instrucao_sistema = (
            "Você é o Indianos Remaster, uma inteligência artificial que gerencia "
            "os componentes do computador para o seu criador.\n\n"
        )
        contents = []
        if not historico:
            contents.append({"role": "user", "parts": [{"text": instrucao_sistema}]})
            contents.append({"role": "model", "parts": [{"text": "Entendido, estou pronto."}]})
        else:
            contents.extend(historico)
        contents.append({"role": "user", "parts": [{"text": texto_usuario}]})

        texto_resposta = chamar_gemini({"contents": contents}, timeout=15)
        if not texto_resposta:
            return "API indisponível no momento."

        salvar_mensagem_memoria("usuario", texto_usuario)
        salvar_mensagem_memoria("ia", texto_resposta)
        return texto_resposta
    except Exception as e:
        print(f"[Gemini API Error] {e}")
        return "Erro de comunicação com o servidor."


def escutar_palmas_loop():
    global escutando_palmas
    if sistema_ativo:
        return
    with lock_sistema:
        if escutando_palmas:
            return
        escutando_palmas = True

    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    except Exception as e:
        print(f"[Audio] Falha ao abrir stream de palmas: {e}")
        with lock_sistema:
            escutando_palmas = False
        p.terminate()
        return

    media_ambiente = 500
    contador_palmas = 0
    ultimo_pico = 0
    tempo_limite = time.time() + 15
    mostrar_texto("AGUARDANDO PALMAS...")
    atualizar_corpo("bloqueado")

    while not sistema_ativo:
        if time.time() > tempo_limite:
            break
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            if not data:
                continue
            rms = audioop.rms(data, 2)
            tempo_atual = time.time()
            if rms > media_ambiente * THRESHOLD_PALMA and rms > 3000:
                if (tempo_atual - ultimo_pico) > 0.15:
                    contador_palmas = contador_palmas + 1 if (tempo_atual - ultimo_pico) < 1.3 else 1
                    ultimo_pico = tempo_atual
                    if contador_palmas == 2:
                        break
            else:
                if rms > 10:
                    media_ambiente = int(media_ambiente * 0.95 + rms * 0.05)
                media_ambiente = max(media_ambiente, 300)
        except Exception:
            break

    try:
        stream.stop_stream()
        stream.close()
    except Exception:
        pass
    p.terminate()
    with lock_sistema:
        escutando_palmas = False

    if contador_palmas == 2 and not sistema_ativo:
        protocolo_palmas()
    elif not sistema_ativo:
        desenhar_tela_bloqueada()
        atualizar_corpo("bloqueado")

def protocolo_palmas():
    global sistema_ativo, escutando_palmas, mic_pausado
    with lock_sistema:
        if sistema_ativo:
            return
        escutando_palmas = False
        sistema_ativo = True
        mic_pausado = False
    desenhar_interface_estatica()
    atualizar_corpo("espera")
    mostrar_texto("SISTEMAS ONLINE")
    tocar_wav_com_volume("acorda.wav", 1.0)
    threading.Thread(target=mic_loop_continuo, daemon=True).start()
    falar("Sistemas ativados com sucesso.")


MODO_VIVO_ATIVO = True
TEMPO_OCIOSO_PARA_ANALISAR = 45
INTERVALO_MIN_ENTRE_ANALISES = 90

_ultima_atividade_ts = time.time()
_ultima_analise_proativa_ts = 0.0
_lock_atividade = threading.Lock()

def _marcar_atividade(*args, **kwargs):
    global _ultima_atividade_ts
    with _lock_atividade:
        _ultima_atividade_ts = time.time()

def iniciar_monitor_atividade():
    listener_mouse = _pynput_mouse_listener_mod.Listener(
        on_move=_marcar_atividade, on_click=_marcar_atividade, on_scroll=_marcar_atividade
    )
    listener_teclado = _pynput_keyboard_listener_mod.Listener(on_press=_marcar_atividade)
    listener_mouse.daemon = True
    listener_teclado.daemon = True
    listener_mouse.start()
    listener_teclado.start()

def alternar_modo_vivo():
    global MODO_VIVO_ATIVO
    MODO_VIVO_ATIVO = not MODO_VIVO_ATIVO
    estado = "ATIVADO" if MODO_VIVO_ATIVO else "DESATIVADO"
    print(f"[Modo Vivo] {estado} via atalho (Ctrl+Shift+V).")
    mostrar_texto(f"MODO VIVO {estado}")

def analisar_tela_proativamente():
    try:
        texto_ocr = ler_texto_tela_ocr()
        with mss.mss() as sct:
            sct_img = sct.grab(REGIAO_TELA_CHEIA)
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size, level=9)
            foto_base64 = base64.b64encode(img_bytes).decode('utf-8')

        contexto_ocr = f"\n\nTexto lido na tela via OCR (contexto extra, pode ter ruído): {texto_ocr[:800]}" if texto_ocr else ""

        pergunta = (
            "Você é o Indianos Remaster, olhando a tela do seu criador de forma espontânea "
            "agora — ele NÃO pediu nada. Olhe a imagem e decida com bom senso e MUITO "
            "conservador:\n\n"
            "- Se não houver nada relevante, óbvio e útil pra comentar: responda SOMENTE 'NADA'.\n"
            "- Se perceber algo que você já sabe fazer sozinho (uma das suas funções) e que "
            "claramente ajudaria agora, responda: ACAO: <descrição curta, no mesmo estilo de "
            "um comando de voz que você entenderia>\n"
            "- Se for algo que vale um comentário, mas não é pra você agir sozinho, responda: "
            "SUGESTAO: <frase curta e natural, como se estivesse puxando assunto>\n\n"
            "Nunca comente sobre conteúdo sensível, íntimo ou privado que aparecer na tela. "
            "Na dúvida entre falar e ficar quieto, fique quieto (responda NADA)."
            + contexto_ocr
        )

        texto_resposta = chamar_gemini({"contents": [{"parts": [
            {"text": pergunta},
            {"inlineData": {"mimeType": "image/png", "data": foto_base64}}
        ]}]}, timeout=30)

        if not texto_resposta:
            return
        resultado = texto_resposta.strip()

        if resultado.upper().startswith("NADA"):
            return

        if resultado.startswith("SUGESTAO:"):
            sugestao = resultado.split("SUGESTAO:", 1)[1].strip()
            if sugestao:
                print(f"[Modo Vivo] Sugestão espontânea: {sugestao}")
                falar(sugestao)

        elif resultado.startswith("ACAO:"):
            ordem = resultado.split("ACAO:", 1)[1].strip()
            if ordem:
                print(f"[Modo Vivo] Ação espontânea: {ordem}")
                falar(f"Percebi uma coisa e já vou resolver: {ordem}")
                threading.Thread(target=processar_resposta_texto, args=(ordem,), daemon=True).start()
    except Exception as e:
        print(f"[Modo Vivo] Erro na análise proativa: {e}")

def loop_modo_vivo():
    global _ultima_analise_proativa_ts
    iniciar_monitor_atividade()
    while True:
        time.sleep(5)
        if not MODO_VIVO_ATIVO or not sistema_ativo:
            continue

        if estado_atual_rosto in ("processando", "falando", "ouvindo"):
            continue
        with _lock_atividade:
            ocioso_ha = time.time() - _ultima_atividade_ts
        desde_ultima_analise = time.time() - _ultima_analise_proativa_ts
        if ocioso_ha >= TEMPO_OCIOSO_PARA_ANALISAR and desde_ultima_analise >= INTERVALO_MIN_ENTRE_ANALISES:
            _ultima_analise_proativa_ts = time.time()
            analisar_tela_proativamente()


ARQUIVO_AUDITORIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auditoria_indianos.log")

def registrar_auditoria(acao, detalhes=""):
    try:
        linha = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {acao}"
        if detalhes:
            linha += f" — {detalhes}"
        with open(ARQUIVO_AUDITORIA, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
        print(f"[Auditoria] {linha}")
    except Exception as e:
        print(f"[Auditoria] Erro ao registrar: {e}")

def ler_ultimas_auditorias(qtd=5):
    try:
        if not os.path.exists(ARQUIVO_AUDITORIA):
            return []
        with open(ARQUIVO_AUDITORIA, "r", encoding="utf-8") as f:
            linhas = [l.strip() for l in f.readlines() if l.strip()]
        return linhas[-qtd:]
    except Exception as e:
        print(f"[Auditoria] Erro ao ler: {e}")
        return []


PORTA_SERVIDOR_REDE = 5000

_PAGINA_CELULAR = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Indianos Remaster</title>
<style>
  body { font-family: sans-serif; background:#111; color:#eee; padding:16px; }
  h1 { font-size: 20px; }
  #status { padding:8px 12px; border-radius:8px; background:#222; margin-bottom:12px; }
  input { width:100%; padding:12px; font-size:16px; border-radius:8px; border:none; margin-bottom:8px; box-sizing:border-box; }
  button { width:100%; padding:12px; font-size:16px; border-radius:8px; border:none; background:#3a7; color:#fff; }
  ul { padding-left:18px; font-size:14px; color:#aaa; }
</style>
</head>
<body>
  <h1>Indianos Remaster</h1>
  <div id="status">Carregando status...</div>
  <input id="comando" placeholder="Digite um comando (ex: coloca o volume em 30%)">
  <button onclick="enviar()">Enviar</button>
  <h3>Últimas ações (auditoria)</h3>
  <ul id="auditoria"></ul>
<script>
const TOKEN = new URLSearchParams(location.search).get('token') || '';
async function atualizarStatus() {
  try {
    const r = await fetch('/status', {headers: {'X-Token': TOKEN}});
    const d = await r.json();
    document.getElementById('status').innerText =
      'Sistema: ' + (d.sistema_ativo ? 'ATIVO' : 'bloqueado') + ' | Estado: ' + d.estado_rosto + ' | Modo Vivo: ' + (d.modo_vivo ? 'ligado' : 'desligado');
    document.getElementById('auditoria').innerHTML =
      d.auditoria.map(l => '<li>' + String(l).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) + '</li>').join('');
  } catch(e) {}
}
async function enviar() {
  const campo = document.getElementById('comando');
  const texto = campo.value.trim();
  if (!texto) return;
  await fetch('/comando', {
    method: 'POST', headers: {'Content-Type':'application/json', 'X-Token': TOKEN},
    body: JSON.stringify({texto: texto})
  });
  campo.value = '';
}
setInterval(atualizarStatus, 3000);
atualizarStatus();
</script>
</body>
</html>"""

TOKEN_REDE = os.environ.get("INDIANOS_TOKEN") or secrets.token_urlsafe(16)

if FLASK_DISPONIVEL:
    app_rede = Flask(__name__)
    app_rede.logger.disabled = True

    @app_rede.before_request
    def _exigir_token():
        enviado = request.headers.get("X-Token") or request.args.get("token") or ""
        if not hmac.compare_digest(enviado.encode("utf-8"), TOKEN_REDE.encode("utf-8")):
            return jsonify({"ok": False, "erro": "nao autorizado"}), 401

    @app_rede.route("/")
    def _pagina_inicial():
        return Response(_PAGINA_CELULAR, mimetype="text/html")

    @app_rede.route("/status")
    def _status_json():
        return jsonify({
            "sistema_ativo": sistema_ativo,
            "estado_rosto": estado_atual_rosto,
            "modo_vivo": MODO_VIVO_ATIVO,
            "auditoria": ler_ultimas_auditorias(8),
        })

    @app_rede.route("/comando", methods=["POST"])
    def _receber_comando():
        dados = request.get_json(silent=True) or {}
        texto = (dados.get("texto") or "").strip()
        if not texto:
            return jsonify({"ok": False, "erro": "texto vazio"}), 400
        if not sistema_ativo:
            return jsonify({"ok": False, "erro": "sistema bloqueado — desperte a Indianos primeiro (senha/palmas)"}), 409
        print(f"[Rede] Comando recebido do celular: {texto}")
        threading.Thread(target=processar_resposta_texto, args=(texto,), daemon=True).start()
        return jsonify({"ok": True})

def _obter_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def _listar_ips_locais():
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    try:
        saida = subprocess.run("ipconfig", shell=True, capture_output=True, text=True, timeout=5).stdout
        for linha in saida.splitlines():
            linha = linha.strip()
            if linha.lower().startswith("ipv4"):
                partes = linha.split(":")
                if len(partes) == 2:
                    ip = partes[1].strip()
                    if ip and not ip.startswith("127."):
                        ips.add(ip)
    except Exception:
        pass
    return sorted(ips) or [_obter_ip_local()]

def iniciar_servidor_rede():
    if not FLASK_DISPONIVEL:
        return
    ips = _listar_ips_locais()
    print("[Rede] Servidor pro celular no ar. Endereços possíveis (teste o que combina com a rede do seu celular):")
    for ip in ips:
        marca = "  <- provável, se usar Hotspot Móvel do Windows" if ip.startswith("192.168.137.") else ""
        print(f"          http://{ip}:{PORTA_SERVIDOR_REDE}/?token={TOKEN_REDE}{marca}")
    try:
        app_rede.run(host="0.0.0.0", port=PORTA_SERVIDOR_REDE, debug=False, use_reloader=False)
    except Exception as e:
        print(f"[Rede] Erro ao subir servidor: {e}")


ADB_CELULAR_IP = ""

def adb_conectado():
    try:
        saida = subprocess.run("adb devices", shell=True, capture_output=True, text=True, timeout=5).stdout
        linhas = [l for l in saida.splitlines() if l.strip() and "List of devices" not in l]
        return any(l.strip().endswith("device") for l in linhas)
    except Exception:
        return False

def adb_reconectar():
    if adb_conectado():
        return True
    if ADB_CELULAR_IP:
        subprocess.run(f"adb connect {ADB_CELULAR_IP}", shell=True, capture_output=True, text=True, timeout=8)
    return adb_conectado()

def adb_shell(comando):
    if not adb_reconectar():
        return None, "celular não conectado (confira o cabo/Wi-Fi e o ADB_CELULAR_IP)"
    try:
        r = subprocess.run(f'adb shell {comando}', shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip(), None
    except Exception as e:
        return None, str(e)

def celular_tocar(x, y):
    _, erro = adb_shell(f"input tap {x} {y}")
    return erro

def celular_tocar_repetido(x, y, vezes=2, intervalo=0.35):
    for i in range(max(1, vezes)):
        celular_tocar(x, y)
        if i < vezes - 1:
            time.sleep(intervalo)

def celular_toque_duplo(x, y):
    celular_tocar(x, y)
    time.sleep(0.08)
    celular_tocar(x, y)

_MAPA_NUMEROS_EXTENSO = {
    "uma": 1, "um": 1, "duas": 2, "dois": 2, "tres": 3, "três": 3,
    "quatro": 4, "cinco": 5, "seis": 6,
}

def _extrair_quantidade_toques(texto):
    texto_min = texto.lower()
    numeros = re.findall(r"\d+", texto_min)
    if numeros:
        return int(numeros[0])
    for palavra, valor in _MAPA_NUMEROS_EXTENSO.items():
        if palavra in texto_min:
            return valor
    return 1

def celular_deslizar(x1, y1, x2, y2, duracao_ms=300):
    _, erro = adb_shell(f"input swipe {x1} {y1} {x2} {y2} {duracao_ms}")
    return erro

def celular_voltar():
    _, erro = adb_shell("input keyevent KEYCODE_BACK")
    return erro

def celular_home():
    _, erro = adb_shell("input keyevent KEYCODE_HOME")
    return erro

def celular_volume(subir=True, quantas_vezes=3):
    tecla = "KEYCODE_VOLUME_UP" if subir else "KEYCODE_VOLUME_DOWN"
    for _ in range(quantas_vezes):
        adb_shell(f"input keyevent {tecla}")


APPS_CELULAR = {
    "whatsapp": "com.whatsapp",
    "youtube": "com.google.android.youtube",
    "instagram": "com.instagram.android",
    "insta": "com.instagram.android",
    "tiktok": "com.zhiliaoapp.musically",
    "tik tok": "com.zhiliaoapp.musically",
    "camera": "com.sec.android.app.camera",
    "câmera": "com.sec.android.app.camera",
    "chrome": "com.android.chrome",
    "spotify": "com.spotify.music",
}

def celular_abrir_app(nome_app):
    nome = nome_app.lower().strip()
    for artigo in ("o ", "a ", "os ", "as "):
        if nome.startswith(artigo):
            nome = nome[len(artigo):].strip()
            break
    pacote = APPS_CELULAR.get(nome)
    if not pacote:

        for chave, pac in APPS_CELULAR.items():
            if chave in nome or nome in chave:
                pacote = pac
                break
    if not pacote:
        return f"não conheço o pacote do app '{nome_app}' (adiciona em APPS_CELULAR)"
    _, erro = adb_shell(f"monkey -p {pacote} -c android.intent.category.LAUNCHER 1")
    return erro

def celular_tirar_print(caminho_local="celular_print.png"):
    if not adb_reconectar():
        return None, "celular não conectado"
    try:
        subprocess.run("adb shell screencap -p /sdcard/_indianos_print.png", shell=True, timeout=10)
        subprocess.run(f"adb pull /sdcard/_indianos_print.png {caminho_local}", shell=True, capture_output=True, timeout=10)
        subprocess.run("adb shell rm /sdcard/_indianos_print.png", shell=True, timeout=5)
        return caminho_local, None
    except Exception as e:
        return None, str(e)

def celular_wifi(ligar=True):
    estado = "enable" if ligar else "disable"
    _, erro = adb_shell(f"svc wifi {estado}")
    return erro

def celular_bluetooth(ligar=True):
    estado = "enable" if ligar else "disable"
    _, erro = adb_shell(f"svc bluetooth {estado}")
    return erro

def celular_enviar_sms(numero, mensagem):
    numero_limpo = re.sub(r"[^0-9+]", "", numero)
    msg_escapada = mensagem.replace('"', "'")
    _, erro = adb_shell(
        f'am start -a android.intent.action.SENDTO -d sms:{numero_limpo} --es sms_body "{msg_escapada}" --ez exit_on_sent true'
    )
    return erro

def celular_resolucao():
    saida, _ = adb_shell("wm size")
    if saida:
        m = re.search(r"(\d+)x(\d+)", saida)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None

def celular_interpretar_texto_a_digitar(pedido):
    pergunta = (
        "O usuário deu esta ordem de voz pedindo pra digitar algo num celular: "
        f"'{pedido}'.\n\n"
        "Responda SOMENTE com o texto exato que deve ser digitado — sem "
        "explicações, sem aspas, sem markdown, sem comentário nenhum.\n"
        "Se o pedido já É o próprio texto a digitar (ex: 'escreve bom dia'), "
        "apenas devolva esse texto ('bom dia').\n"
        "Se o pedido pede algo que precisa ser gerado (ex: 'o alfabeto', "
        "'os números de 1 a 10', 'meu nome de trás pra frente'), gere o "
        "resultado certo.\n\n"
        "Exemplos:\n"
        "Pedido: 'digite o alfabeto no celular' -> Resposta: abcdefghijklmnopqrstuvwxyz\n"
        "Pedido: 'escreve bom dia no celular' -> Resposta: bom dia\n"
        "Pedido: 'digita os números de 1 a 5' -> Resposta: 12345"
    )
    resposta = chamar_gemini(
        {"contents": [{"parts": [{"text": pergunta}]}]},
        timeout=45, permitir_fallback_local=False
    )
    if not resposta or not resposta.strip():
        print("[Celular] Gemini não respondeu nada pro pedido de digitação — usando o texto literal.")
        return pedido
    resultado = resposta.strip().strip('"').strip("'")
    print(f"[Celular] Vou digitar: {resultado!r}")
    return resultado

def celular_digitar(texto):
    texto_adb = re.sub(r'[`$\\;&|<>()]', "", texto).replace(" ", "%s").replace('"', "").replace("'", "")
    comando = f'input text "{texto_adb}"'
    print(f"[Celular] Rodando: adb shell {comando}")
    saida, erro = adb_shell(comando)
    if erro:
        print(f"[Celular] Erro ao digitar: {erro}")
    return erro

def celular_rolar(direcao="baixo"):
    resolucao = celular_resolucao()
    if not resolucao:
        return "não consegui saber a resolução do celular"
    largura, altura = resolucao
    cx = largura // 2
    if direcao == "cima":
        y1, y2 = int(altura * 0.25), int(altura * 0.75)
    else:
        y1, y2 = int(altura * 0.75), int(altura * 0.25)
    return celular_deslizar(cx, y1, cx, y2, 200)

def celular_video_seguinte():
    resolucao = celular_resolucao()
    if not resolucao:
        return "não consegui saber a resolução do celular"
    largura, altura = resolucao
    cx = largura // 2
    return celular_deslizar(cx, int(altura * 0.85), cx, int(altura * 0.15), 120)

def celular_video_anterior():
    resolucao = celular_resolucao()
    if not resolucao:
        return "não consegui saber a resolução do celular"
    largura, altura = resolucao
    cx = largura // 2
    return celular_deslizar(cx, int(altura * 0.15), cx, int(altura * 0.85), 120)

_AUTO_ROLAR_ATIVO = False

def _loop_auto_rolar_celular(intervalo_segundos):
    global _AUTO_ROLAR_ATIVO
    while _AUTO_ROLAR_ATIVO:
        celular_video_seguinte()
        time.sleep(intervalo_segundos)

def celular_iniciar_auto_rolar(intervalo_segundos=6):
    global _AUTO_ROLAR_ATIVO
    if _AUTO_ROLAR_ATIVO:
        return "já está rolando sozinho"
    _AUTO_ROLAR_ATIVO = True
    threading.Thread(target=_loop_auto_rolar_celular, args=(intervalo_segundos,), daemon=True).start()
    return None

def celular_parar_auto_rolar():
    global _AUTO_ROLAR_ATIVO
    _AUTO_ROLAR_ATIVO = False

def celular_ligar_tela():
    _, erro = adb_shell("input keyevent KEYCODE_WAKEUP")
    return erro

SENHA_CELULAR = os.environ.get("CELULAR_PIN", "")

def celular_desbloquear():
    celular_ligar_tela()
    time.sleep(0.6)
    resolucao = celular_resolucao()
    if resolucao:
        largura, altura = resolucao
        celular_deslizar(largura // 2, int(altura * 0.8), largura // 2, int(altura * 0.3), 300)
        time.sleep(0.6)
    if SENHA_CELULAR and SENHA_CELULAR.isalnum():
        adb_shell(f"input text {SENHA_CELULAR}")
        adb_shell("input keyevent KEYCODE_ENTER")
        return None
    return None

def celular_desligar():
    saida, erro = adb_shell("reboot -p")
    if erro:
        return erro
    if saida and ("not allowed" in saida.lower() or "permission" in saida.lower()):
        return "Android recusou (precisa de root pra desligar via ADB)"
    return None

def celular_clicar_com_visao(comando_usuario):
    caminho, erro = celular_tirar_print()
    if erro:
        return f"não consegui tirar print do celular ({erro})"


    largura = altura = None
    try:
        from PIL import Image
        with Image.open(caminho) as img:
            largura, altura = img.size
        print(f"[Celular] Tamanho real do print: {largura}x{altura}")
    except Exception as e:
        print(f"[Celular] Não consegui ler o tamanho do print via Pillow ({e}), usando 'wm size'.")
        resolucao = celular_resolucao()
        if resolucao:
            largura, altura = resolucao
    if not largura or not altura:
        return "não consegui saber a resolução do celular"

    try:
        with open(caminho, "rb") as f:
            foto_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"erro lendo o print do celular ({e})"

    pergunta = (
        "Você é o Indianos Remaster olhando a tela de um CELULAR Android (não é PC). "
        f"O usuário pediu: '{comando_usuario}'.\n\n"
        "Olhe a imagem com cuidado e identifique o elemento (ícone, botão, campo de "
        "texto) que precisa ser tocado. Mire no CENTRO EXATO dele.\n\n"
        "O canto superior esquerdo da imagem é (0,0) e o inferior direito é "
        "(1000,1000).\n\n"
        "Responda SOMENTE neste formato, sem markdown, sem texto extra:\n"
        "ACAO: TOQUE[x,y] DIGITE[texto_ou_vazio]"
    )
    texto_resposta = chamar_gemini({"contents": [{"parts": [
        {"text": pergunta},
        {"inlineData": {"mimeType": "image/png", "data": foto_base64}}
    ]}]}, timeout=40, permitir_fallback_local=False)
    if not texto_resposta:
        return "a IA não respondeu"
    print(f"[Celular] Resposta bruta da IA: {texto_resposta!r}")

    resultado = texto_resposta.strip()
    if "TOQUE[" not in resultado:
        return "não consegui entender a resposta da IA"
    try:
        coords = resultado.split("TOQUE[")[1].split("]")[0].replace(" ", "").split(",")
        x = int(int(float(coords[0])) / 1000 * largura)
        y = int(int(float(coords[1])) / 1000 * altura)
        print(f"[Celular] Vou tocar em pixel real: ({x}, {y}) numa tela de {largura}x{altura}")

        pedido_min = comando_usuario.lower()
        eh_duplo_toque_nativo = any(p in pedido_min for p in
            ["duplo toque", "double tap", "dá um zoom", "da um zoom", "curte a foto", "curtir a foto"])
        if eh_duplo_toque_nativo:
            celular_toque_duplo(x, y)
        else:
            quantidade = _extrair_quantidade_toques(comando_usuario)
            if quantidade > 1:
                celular_tocar_repetido(x, y, quantidade)
            else:
                celular_tocar(x, y)

        if "DIGITE[" in resultado:
            txt_extra = resultado.split("DIGITE[")[1].split("]")[0]
            if txt_extra.strip():
                time.sleep(0.6)
                celular_digitar(txt_extra)
        return None
    except Exception as e:
        return f"erro ao interpretar a coordenada ({e})"

def _digitar_no_celular_thread(texto_comando):
    texto_a_digitar = celular_interpretar_texto_a_digitar(texto_comando)
    erro = celular_digitar(texto_a_digitar)
    if erro:
        falar("Não consegui digitar no celular.")
    else:
        falar(f"Digitei: {texto_a_digitar}")

def _clicar_no_celular_thread(texto_comando):
    erro = celular_clicar_com_visao(texto_comando)
    if erro:
        falar(f"Não consegui: {erro}")


def arduino_control_loop():
    global led_estado
    while True:
        try:
            if keyboard.is_pressed('space') and arduino:
                if led_estado == 'off':
                    led_estado = 'on'
                    arduino.write(b"APAGAR\n")
                    print("Comando APAGAR enviado ao Arduino")
                elif led_estado == 'on':
                    led_estado = 'off'
                    arduino.write(b"ACENDER\n")
                    print("Comando ACENDER enviado ao Arduino")

            if arduino and arduino.in_waiting > 0:
                resposta = arduino.readline().decode('utf-8').strip()
                if resposta == "LED_OFF":
                    winsound.Beep(500, 700)
                elif resposta == "LED_ON":
                    winsound.Beep(1500, 900)
        except Exception as e:
            print(f"[Arduino Loop] Erro: {e}")
            time.sleep(0.1)


if __name__ == "__main__":
    keyboard.add_hotkey('ctrl+shift+a', acionar_atalho_teclado)
    keyboard.add_hotkey('ctrl+shift+z', enviar_texto_digitado)
    keyboard.add_hotkey('ctrl+shift+v', alternar_modo_vivo)

    threading.Thread(target=arduino_control_loop, daemon=True).start()
    threading.Thread(target=loop_animacao_rosto, daemon=True).start()
    threading.Thread(target=escutar_palmas_loop, daemon=True).start()
    threading.Thread(target=loop_modo_vivo, daemon=True).start()
    threading.Thread(target=iniciar_servidor_rede, daemon=True).start()

    desenhar_tela_bloqueada()
    atualizar_corpo("bloqueado")

    print("[CORE] Indianos Remaster inicializado com sucesso!")
    wn.mainloop()
