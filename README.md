# Indianos Remaster

Assistente de desktop por voz para **Windows**, com IA na nuvem e local, visão de tela, automação de navegador e controle do celular. Projeto pessoal com foco em automação e integração de sistemas.

## Funcionalidades

**Voz e IA**
- Ativação por duas palmas ou pelo atalho `Ctrl+Shift+A`; escuta contínua por microfone e resposta falada (edge-tts).
- Google Gemini com rodízio automático de várias chaves e modelos quando a cota esgota, e fallback local via Ollama.
- Memória curta de conversa e log de auditoria dos comandos executados.

**Controle do computador**
- Visão de tela: tenta achar o elemento pela árvore de acessibilidade do Windows (pywinauto) e por OCR (Tesseract) antes de gastar chamada de IA com print.
- Mouse e teclado automatizados, digitação por comando (`Ctrl+Shift+Z`) e modo "vivo" que analisa a tela de forma proativa (`Ctrl+Shift+V`).
- Localizar, mover e excluir arquivos por voz (exclusão vai para a lixeira quando `send2trash` está instalado).
- Geração e execução de código por pedido, geração de imagens, notas, volume, desligar/reiniciar.

**Navegador**
- WhatsApp Web via Selenium (Edge) com perfil dedicado, para enviar mensagens por voz.

**Celular e hardware**
- Controle de celular Android via ADB: toques, deslize, volume, abrir apps, print, desbloqueio, rolagem automática.
- Página web servida por Flask para mandar comandos ao PC pelo celular.
- Controle de LEDs por Arduino via porta serial.

## Requisitos

- Windows 10/11 e Python 3.10 ou superior (no Python 3.13+, instale também `audioop-lts`).
- Microsoft Edge.
- Opcionais: Tesseract-OCR, Ollama, ADB (Android), Arduino.

```bash
pip install edge-tts keyboard mss pyaudio requests pyserial SpeechRecognition \
    pynput selenium webdriver-manager mouse pycaw comtypes send2trash flask \
    pywinauto pytesseract pillow
```

## Configuração

As chaves da API do Gemini são lidas de variáveis de ambiente. Defina antes de rodar:

```bash
setx GEMINI_KEY_1 "sua-chave"
setx GEMINI_KEY_2 "outra-chave"   # opcional, até GEMINI_KEY_10
```

Ajuste no código o que for específico do seu setup: número de WhatsApp (`MEU_NUMERO_ZAP`), PIN do celular (`SENHA_CELULAR`), porta do Arduino (`COM5`), caminho do Notepad++ e IP do celular para ADB.

## Como rodar

```bash
python indianos_remaster12.py
```

## Avisos de segurança

Este projeto executa ações reais no computador (mouse, teclado, arquivos, shell, desligamento). Use por sua conta e risco.

- O servidor Flask do celular escuta em `0.0.0.0` na porta 5000. Use somente em rede confiável e, de preferência, proteja com token.
- Comandos de voz podem apagar e mover arquivos e executar código gerado por IA.
- Nunca commite chaves de API, PIN do celular, número de telefone, `memoria_local.json`, `auditoria_indianos.log` ou o perfil do Edge usado no WhatsApp.
