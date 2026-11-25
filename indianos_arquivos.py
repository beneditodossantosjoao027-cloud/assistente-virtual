import base64
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

LIMITE_CHARS_ARQ = 60_000
LIMITE_CHARS_TOTAL = 150_000
LIMITE_BYTES_BINARIO = 15 * 1024 * 1024
LIMITE_BYTES_UPLOAD = 25 * 1024 * 1024
LINHAS_MAX_REESCREVER = 700
LIMITE_CHARS_EDICAO = 300_000
MAX_TENTATIVAS = 3
TIMEOUT_EXECUCAO = 15
MAX_VERSOES = 30
PERMITIR_REDE_NA_EXECUCAO = False
PASTAS_PROIBIDAS = ("\\windows\\", "\\program files", "\\programdata\\", "\\appdata\\")

EXT_TEXTO = {
    ".py", ".pyw", ".txt", ".md", ".json", ".csv", ".tsv", ".js", ".ts", ".jsx",
    ".tsx", ".html", ".htm", ".css", ".c", ".h", ".cpp", ".hpp", ".cs", ".java",
    ".kt", ".go", ".rs", ".php", ".rb", ".sh", ".bat", ".ps1", ".sql", ".ino",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".log", ".xml", ".lua",
}
EXT_NAO_CODIGO = {".txt", ".md", ".json", ".csv", ".tsv", ".log", ".xml", ".ini",
                  ".cfg", ".yml", ".yaml", ".toml"}
MIME_BINARIO = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".pdf": "application/pdf",
}
EXT_BLOQUEADAS_UPLOAD = {".exe", ".bat", ".cmd", ".msi", ".ps1", ".vbs", ".scr",
                         ".lnk", ".dll", ".jar", ".com", ".js", ".hta"}

_cfg = {
    "gemini": None,
    "falar": print,
    "mostrar": print,
    "localizar": None,
    "pasta_codigos": os.path.join(os.path.expanduser("~"), "codigos_indianos"),
    "pasta_recebidos": os.path.join(os.path.expanduser("~"), "indianos_recebidos"),
    "pastas": {},
    "editor": None,
    "auditoria": None,
    "pasta_versoes": None,
    "nao_rodar": [],
}


def configurar(**kw):
    _cfg.update({k: v for k, v in kw.items() if v is not None})
    principal = getattr(sys.modules.get("__main__"), "__file__", None)
    if principal:
        principal = os.path.abspath(principal)
        if principal not in _cfg["nao_rodar"]:
            _cfg["nao_rodar"] = list(_cfg["nao_rodar"]) + [principal]
    for p in (_cfg["pasta_codigos"], _cfg["pasta_recebidos"]):
        try:
            os.makedirs(p, exist_ok=True)
        except Exception as e:
            print(f"[Arquivos IA] não consegui criar {p}: {e}")


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower()


def _falar(t):
    try:
        _cfg["falar"](t)
    except Exception:
        print(t)


def _mostrar(t):
    try:
        _cfg["mostrar"](t)
    except Exception:
        print(t)


def _auditar(acao, detalhes=""):
    try:
        if _cfg["auditoria"]:
            _cfg["auditoria"](acao, detalhes)
    except Exception:
        pass


def _nome_livre(caminho):
    if not os.path.exists(caminho):
        return caminho
    base, ext = os.path.splitext(caminho)
    n = 2
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def _carimbo():
    return time.strftime("%Y%m%d_%H%M%S")


def _para_fala(txt, limite=380):
    txt = re.sub(r"```.*?```", " ", txt, flags=re.S)
    txt = re.sub(r"[#*`>|_]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) <= limite:
        return txt
    corte = txt[:limite]
    ponto = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
    return (corte[:ponto + 1] if ponto > 120 else corte) + " (o resto está no arquivo salvo)"


def _abrir(caminho):
    try:
        if _cfg["editor"]:
            _cfg["editor"](caminho)
        elif hasattr(os, "startfile"):
            os.startfile(caminho)
    except Exception as e:
        print(f"[Arquivos IA] não consegui abrir {caminho}: {e}")


def _ultimo_recebido():
    pasta = _cfg["pasta_recebidos"]
    try:
        itens = [os.path.join(pasta, f) for f in os.listdir(pasta)]
        itens = [p for p in itens if os.path.isfile(p)]
        return max(itens, key=os.path.getmtime) if itens else None
    except Exception:
        return None


def _pede_ultimo_recebido(texto):
    return bool(re.search(
        r"\bultim[oa]\s+arquivo\b|\barquivo\s+recebid[oa]\b|\b(?:recebid[oa]|mandei|enviei)\b",
        _norm(texto)))


def _variantes(nome):
    nome = re.sub(r"\s+ponto\s+", ".", nome.strip())
    v = [nome, re.sub(r"\s+", "_", nome), re.sub(r"\s+", "", nome), re.sub(r"\s+", "-", nome)]
    saida = []
    for x in v:
        if x and x not in saida:
            saida.append(x)
    return saida


def resolver(nome):
    if not nome:
        return None
    if nome == "__ultimo__" or _pede_ultimo_recebido(nome):
        return _ultimo_recebido()
    cands = _variantes(nome)
    for c in cands:
        if os.path.isfile(c):
            return c
    for c in cands:
        p = os.path.join(_cfg["pasta_recebidos"], c)
        if os.path.isfile(p):
            return p
    if _cfg["localizar"]:
        for c in cands:
            p = _cfg["localizar"](c)
            if p and os.path.isfile(p):
                return p
    return _busca_fuzzy(nome)


def _so_alnum(s):
    return re.sub(r"[^a-z0-9.]", "", _norm(s))


def _busca_fuzzy(nome):
    alvo = _so_alnum(re.sub(r"\s+ponto\s+", ".", nome))
    if len(alvo) < 3:
        return None
    raizes = [_cfg["pasta_recebidos"], _cfg["pasta_codigos"]] + list(dict.fromkeys(_cfg["pastas"].values()))
    for raiz in raizes:
        if not raiz or not os.path.isdir(raiz):
            continue
        base_prof = raiz.rstrip("\\/").count(os.sep)
        for dirpath, dirs, files in os.walk(raiz):
            if dirpath.count(os.sep) - base_prof >= 3:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if alvo in _so_alnum(f):
                    return os.path.join(dirpath, f)
    return None


_STOP = re.compile(
    r"\s+(?:com|usando|use|pra|para|faz|faca|cria|crie|gera|gere|adiciona|adicione|"
    r"que|no|na|baseado|baseada|e\s+faz|e\s+cria|e\s+crie|e\s+gera|"
    r"roda|rode|testa|teste|executa|execute|corrige|corrija|conserta|conserte|arruma|arrume|"
    r"depois|ate|sozinha?|desfaz|volta|melhora|melhore|edita|edite|muda|mude)\b|[,;]"
)


def extrair_nomes(texto_min):
    t = _norm(texto_min)
    if _pede_ultimo_recebido(t):
        return ["__ultimo__"]
    nomes = []
    for m in re.finditer(r"arquivos?\s+", t):
        plural = t[m.start():m.end()].startswith("arquivos")
        resto = t[m.end():]
        corte = _STOP.search(resto)
        trecho = (resto[:corte.start()] if corte else resto).strip(" :.,\"'")
        trecho = re.sub(r"^(chamado|que se chama|de nome|com o nome)\s+", "", trecho)
        trecho = re.sub(r"\s+e(\s+(?:o|a|os|as))?$", "", trecho)
        partes = re.split(r"\s+e\s+|\s*,\s*", trecho) if plural else [trecho]
        for p in partes:
            p = re.sub(r"^(o|a|os|as|no|na)\s+", "", p.strip(" :.,\"'"))
            if p and p not in nomes:
                nomes.append(p)
    return nomes


def _ler_texto(caminho):
    with open(caminho, "rb") as f:
        raw = f.read(LIMITE_CHARS_ARQ * 4 + 1)
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _ler_docx(caminho):
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(caminho) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p"))


def _ler_xlsx(caminho):
    try:
        import openpyxl
    except ImportError:
        return None
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    saida = []
    for ws in wb.worksheets[:5]:
        saida.append(f"--- planilha: {ws.title} ---")
        for i, linha in enumerate(ws.iter_rows(values_only=True)):
            if i >= 200:
                saida.append("... (cortado em 200 linhas)")
                break
            saida.append("\t".join("" if v is None else str(v) for v in linha))
    return "\n".join(saida)


def ler_arquivo(caminho, orcamento_chars):
    nome = os.path.basename(caminho)
    ext = os.path.splitext(nome)[1].lower()
    try:
        tamanho = os.path.getsize(caminho)
        if ext in MIME_BINARIO:
            if tamanho > LIMITE_BYTES_BINARIO:
                return {"erro": f"{nome} é grande demais ({tamanho // 1024 // 1024} MB)"}
            with open(caminho, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"parts": [{"text": f"=== ARQUIVO: {nome} ==="},
                              {"inlineData": {"mimeType": MIME_BINARIO[ext], "data": b64}}],
                    "aviso": None, "chars": 2000, "linhas": 0, "ext": ext}

        if ext in EXT_TEXTO:
            conteudo = _ler_texto(caminho)
        elif ext == ".docx":
            conteudo = _ler_docx(caminho)
        elif ext == ".xlsx":
            conteudo = _ler_xlsx(caminho)
            if conteudo is None:
                return {"erro": f"pra ler {nome} instale: pip install openpyxl"}
        else:
            conteudo = _ler_texto(caminho)
            if conteudo.count("\x00") or sum(c < " " and c not in "\r\n\t" for c in conteudo[:2000]) > 20:
                return {"erro": f"não sei ler arquivos {ext or 'sem extensão'} ({nome})"}

        linhas = conteudo.count("\n") + 1
        limite = min(LIMITE_CHARS_ARQ, max(orcamento_chars, 0))
        aviso = None
        if len(conteudo) > limite:
            conteudo = conteudo[:limite]
            aviso = f"{nome} foi cortado em {limite} caracteres"
        return {"parts": [{"text": f"=== ARQUIVO: {nome} ===\n{conteudo}"}],
                "aviso": aviso, "chars": len(conteudo), "linhas": linhas, "ext": ext}
    except Exception as e:
        return {"erro": f"erro lendo {nome}: {e}"}


def _juntar(caminhos):
    parts, avisos, infos, restante = [], [], [], LIMITE_CHARS_TOTAL
    for c in caminhos:
        r = ler_arquivo(c, restante)
        if "erro" in r:
            avisos.append(r["erro"])
            continue
        restante -= r["chars"]
        parts.extend(r["parts"])
        infos.append({"caminho": c, "linhas": r["linhas"], "ext": r["ext"]})
        if r["aviso"]:
            avisos.append(r["aviso"])
    return parts, avisos, infos


def _gemini(parts, timeout=90):
    if not _cfg["gemini"]:
        return None
    return _cfg["gemini"]({"contents": [{"parts": parts}]}, timeout=timeout,
                          permitir_fallback_local=False)


def analisar(pedido, caminhos):
    parts, avisos, infos = _juntar(caminhos)
    if not infos:
        _falar("Não consegui ler esse arquivo. " + (avisos[0] if avisos else ""))
        return None
    instrucao = (
        "Você é a Indianos Remaster. O usuário pediu: "
        f"'{pedido}'.\nAnalise o(s) arquivo(s) abaixo e responda em português do Brasil, "
        "direto e organizado. Se o pedido for genérico ('analisa', 'resume'), diga: o que é, "
        "como funciona, pontos principais e, se for código, bugs ou riscos prováveis."
    )
    resposta = _gemini([{"text": instrucao}] + parts)
    if not resposta:
        _falar("A API não respondeu agora, tenta de novo daqui a pouco.")
        return None
    pasta = os.path.join(_cfg["pasta_recebidos"], "analises")
    os.makedirs(pasta, exist_ok=True)
    base = os.path.splitext(os.path.basename(infos[0]["caminho"]))[0]
    saida = _nome_livre(os.path.join(pasta, f"analise_{base}_{_carimbo()}.md"))
    with open(saida, "w", encoding="utf-8") as f:
        f.write(f"# Análise — {', '.join(os.path.basename(i['caminho']) for i in infos)}\n\n")
        f.write(f"Pedido: {pedido}\n\n{resposta.strip()}\n")
    print(f"\n[Arquivos IA] ANÁLISE:\n{resposta}\n(salvo em {saida})")
    _mostrar(_para_fala(resposta, 300))
    extra = f" Atenção: {avisos[0]}." if avisos else ""
    _falar(_para_fala(resposta) + extra)
    _auditar("ANALISAR ARQUIVO", ", ".join(i["caminho"] for i in infos))
    return saida


def _achar_pasta_existente(nome):
    alvo = _norm(nome).strip()
    for raiz in {v for v in _cfg["pastas"].values() if v}:
        try:
            for d in os.listdir(raiz):
                if _norm(d) == alvo and os.path.isdir(os.path.join(raiz, d)):
                    return os.path.join(raiz, d)
        except Exception:
            pass
    return None


def _resolver_destino(destino, origem):
    d = _norm(destino).strip(" .")
    d = re.sub(r"^(a |o |na |no )?(pasta |diretorio )?(de |do |da )?", "", d).strip()
    if not d:
        return os.path.dirname(origem), True
    for chave, pasta in _cfg["pastas"].items():
        if chave in d and pasta:
            return pasta, False
    if os.path.isdir(destino.strip()):
        return destino.strip(), False
    achada = _achar_pasta_existente(d)
    if achada:
        return achada, False
    base = _cfg["pastas"].get("area de trabalho") or os.path.dirname(origem)
    return os.path.join(base, d), False


def copiar(texto_min):
    t = _norm(texto_min)
    m = re.search(r"arquivo\s+(.+)$", t)
    if not m:
        _falar("Qual arquivo você quer copiar?")
        return None
    resto = m.group(1)
    partes = re.split(r"\s+(?:para|pra|pro|na pasta|em)\s+", resto, maxsplit=1)
    nome = partes[0].strip(" .,")
    destino = partes[1] if len(partes) > 1 else ""
    origem = resolver(nome)
    if not origem:
        _falar(f"Não encontrei nenhum arquivo parecido com {nome}.")
        return None
    pasta, mesma_pasta = _resolver_destino(destino, origem)
    try:
        os.makedirs(pasta, exist_ok=True)
        base, ext = os.path.splitext(os.path.basename(origem))
        nome_final = f"{base}_copia{ext}" if mesma_pasta else os.path.basename(origem)
        final = _nome_livre(os.path.join(pasta, nome_final))
        shutil.copy2(origem, final)
    except Exception as e:
        print(f"[Arquivos IA] erro copiando: {e}")
        _falar("Não consegui copiar esse arquivo.")
        return None
    _mostrar(f"Copiado: {final}")
    _falar(f"Copiei {os.path.basename(origem)} para {os.path.basename(pasta) or pasta}.")
    _auditar("COPIAR ARQUIVO", f"{origem} -> {final}")
    return final


def mover(texto_min):
    t = _norm(texto_min)
    m = re.search(r"arquivo\s+(.+)$", t)
    if not m:
        _falar("Qual arquivo você quer mover?")
        return None
    partes = re.split(r"\s+(?:para|pra|pro|na pasta|em)\s+", m.group(1), maxsplit=1)
    nome = partes[0].strip(" .,")
    destino = partes[1].strip() if len(partes) > 1 else ""
    if not destino:
        _falar("Pra onde eu movo? Fala assim: move o arquivo tal para downloads.")
        return None
    origem = resolver(nome)
    if not origem:
        _falar(f"Não encontrei nenhum arquivo parecido com {nome}.")
        return None
    abs_origem = os.path.abspath(origem)
    if os.path.normcase(abs_origem) in {os.path.normcase(os.path.abspath(p)) for p in _cfg["nao_rodar"] if p}:
        _falar("Esse é o programa que está rodando agora, não vou mover ele.")
        return None
    pasta, _ = _resolver_destino(destino, origem)
    for caminho in (abs_origem, os.path.abspath(pasta)):
        if any(x in caminho.lower().replace("/", "\\") + "\\" for x in PASTAS_PROIBIDAS):
            _falar("Não mexo em arquivos de pasta de sistema.")
            return None
    if os.path.normcase(os.path.abspath(pasta)) == os.path.normcase(os.path.dirname(abs_origem)):
        _falar(f"{os.path.basename(origem)} já está nessa pasta.")
        return origem
    try:
        os.makedirs(pasta, exist_ok=True)
        final = _nome_livre(os.path.join(pasta, os.path.basename(origem)))
        shutil.move(origem, final)
    except Exception as e:
        print(f"[Arquivos IA] erro movendo: {e}")
        _falar("Não consegui mover esse arquivo.")
        return None
    print(f"[Arquivos IA] movido: {origem} -> {final}")
    _mostrar(f"Movido: {final}")
    _falar(f"Movi {os.path.basename(origem)} para {os.path.basename(pasta) or pasta}.")
    _auditar("MOVER ARQUIVO", f"{origem} -> {final}")
    return final


def _extrair_codigo(resposta):
    blocos = re.findall(r"```[\w+#.-]*\n(.*?)```", resposta, flags=re.S)
    if blocos:
        return max(blocos, key=len).strip("\n") + "\n"
    return resposta.replace("```", "").strip("\n") + "\n"


def _erro_sintaxe_python(codigo):
    try:
        compile(codigo, "<indianos>", "exec")
        return None
    except SyntaxError as e:
        return f"linha {e.lineno}: {e.msg}"


def codar_baseado(pedido, caminhos):
    parts, avisos, infos = _juntar(caminhos)
    if not infos:
        _falar("Não consegui ler os arquivos base. " + (avisos[0] if avisos else ""))
        return None

    principal = next((i for i in infos if i["ext"] in EXT_TEXTO and i["ext"] not in EXT_NAO_CODIGO), infos[0])
    ext = principal["ext"] if principal["ext"] in EXT_TEXTO else ".py"
    base = os.path.splitext(os.path.basename(principal["caminho"]))[0]
    modo_trechos = principal["linhas"] > LINHAS_MAX_REESCREVER
    os.makedirs(_cfg["pasta_codigos"], exist_ok=True)

    if modo_trechos:
        instrucao = (
            "Você é a Indianos Remaster, assistente de programação.\n"
            f"PEDIDO DO USUÁRIO: '{pedido}'\n"
            "Os arquivos abaixo são a BASE. O arquivo principal é grande demais pra reescrever inteiro. "
            "Responda em markdown curto: pra cada mudança diga ONDE colocar (nome da função/trecho "
            "âncora) e traga o código COMPLETO das funções novas ou alteradas, em blocos de código. "
            "Preserve o estilo do código original."
        )
        resposta = _gemini([{"text": instrucao}] + parts, timeout=120)
        if not resposta:
            _falar("A API não respondeu agora, tenta de novo daqui a pouco.")
            return None
        saida = _nome_livre(os.path.join(_cfg["pasta_codigos"], f"{base}_trechos_{_carimbo()}.md"))
        with open(saida, "w", encoding="utf-8") as f:
            f.write(f"# Trechos para {os.path.basename(principal['caminho'])}\n\nPedido: {pedido}\n\n{resposta.strip()}\n")
        _mostrar(f"Trechos salvos: {saida}")
        _falar("O arquivo é grande, então não reescrevi inteiro. Salvei só os trechos novos, "
               "com onde colocar cada um, e abri pra você.")
        _abrir(saida)
        _auditar("CODAR BASEADO EM ARQUIVO (trechos)", f"{principal['caminho']} -> {saida}")
        return saida

    instrucao = (
        "Você é a Indianos Remaster, assistente de programação.\n"
        f"PEDIDO DO USUÁRIO: '{pedido}'\n"
        "Os arquivos abaixo são a BASE (código/referência existente). Entregue o arquivo NOVO pedido, "
        "COMPLETO e pronto pra usar, preservando o que já funciona e o estilo do original. "
        "Responda SOMENTE com o conteúdo do arquivo, sem explicação e sem markdown."
    )
    resposta = _gemini([{"text": instrucao}] + parts, timeout=120)
    if not resposta:
        _falar("A API não respondeu agora, tenta de novo daqui a pouco.")
        return None
    codigo = _extrair_codigo(resposta)

    aviso_sintaxe = None
    if ext in (".py", ".pyw"):
        erro = _erro_sintaxe_python(codigo)
        if erro:
            retry = _gemini([{"text": (
                f"O código abaixo tem erro de sintaxe ({erro}). Corrija SÓ isso e devolva o arquivo "
                f"completo, sem explicação e sem markdown.\n\n{codigo}")}], timeout=120)
            if retry:
                codigo2 = _extrair_codigo(retry)
                if not _erro_sintaxe_python(codigo2):
                    codigo, erro = codigo2, None
        if erro:
            aviso_sintaxe = erro

    saida = _nome_livre(os.path.join(_cfg["pasta_codigos"], f"{base}_indianos_{_carimbo()}{ext}"))
    with open(saida, "w", encoding="utf-8") as f:
        f.write(codigo)
    _mostrar(f"Código salvo: {saida}")
    msg = ("Escrevi o arquivo novo baseado no que você mandou e abri pra você. "
           "Não mexi no original e não rodei o código.")
    if aviso_sintaxe:
        msg += f" Atenção: ainda ficou um erro de sintaxe na {aviso_sintaxe}."
    _falar(msg)
    _abrir(saida)
    _auditar("CODAR BASEADO EM ARQUIVO", f"{', '.join(i['caminho'] for i in infos)} -> {saida}")
    return saida


def salvar_upload(arquivos):
    os.makedirs(_cfg["pasta_recebidos"], exist_ok=True)
    salvos, recusados = [], []
    for f in arquivos:
        original = os.path.basename((f.filename or "").replace("\\", "/"))
        nome = re.sub(r"[^\w.\- ()]", "_", original).strip(" .")
        if not nome:
            continue
        if os.path.splitext(nome)[1].lower() in EXT_BLOQUEADAS_UPLOAD:
            recusados.append(nome)
            continue
        destino = _nome_livre(os.path.join(_cfg["pasta_recebidos"], nome))
        f.save(destino)
        salvos.append(destino)
        _auditar("RECEBER ARQUIVO", destino)
    return salvos, recusados


def _sha(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def _pasta_versoes(caminho):
    raiz = _cfg["pasta_versoes"] or os.path.join(
        os.path.dirname(_cfg["pasta_codigos"].rstrip("\\/")), "indianos_versoes")
    h = hashlib.sha1(os.path.abspath(caminho).lower().encode("utf-8")).hexdigest()[:6]
    return os.path.join(raiz, f"{os.path.basename(caminho)}__{h}")


def _indice(pasta):
    try:
        with open(os.path.join(pasta, "indice.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _salvar_indice(pasta, itens):
    with open(os.path.join(pasta, "indice.json"), "w", encoding="utf-8") as f:
        json.dump(itens, f, ensure_ascii=False, indent=1)


def _gravar_bytes(caminho, dados):
    tmp = caminho + ".indianos_tmp"
    with open(tmp, "wb") as f:
        f.write(dados)
    os.replace(tmp, caminho)


def salvar_versao(caminho, motivo):
    pasta = _pasta_versoes(caminho)
    os.makedirs(pasta, exist_ok=True)
    with open(caminho, "rb") as f:
        dados = f.read()
    sha = hashlib.sha1(dados).hexdigest()
    itens = _indice(pasta)
    if itens and itens[-1]["sha"] == sha:
        return itens[-1]
    n = (itens[-1]["n"] + 1) if itens else 1
    ext = os.path.splitext(caminho)[1]
    arq = f"v{n:04d}_{_carimbo()}{ext}"
    with open(os.path.join(pasta, arq), "wb") as f:
        f.write(dados)
    item = {"n": n, "arquivo": arq, "data": time.strftime("%Y-%m-%d %H:%M:%S"),
            "motivo": (motivo or "")[:120], "sha": sha}
    itens.append(item)
    while len(itens) > MAX_VERSOES:
        velho = itens.pop(0)
        try:
            os.remove(os.path.join(pasta, velho["arquivo"]))
        except Exception:
            pass
    _salvar_indice(pasta, itens)
    return item


def listar_versoes(caminho):
    return _indice(_pasta_versoes(caminho))


def restaurar(caminho, n=None):
    pasta = _pasta_versoes(caminho)
    itens = _indice(pasta)
    if not itens:
        return None, "não tenho nenhuma versão guardada desse arquivo"
    if n is None:
        atual = _sha(caminho)
        candidatas = [i for i in itens if i["sha"] != atual]
        if not candidatas:
            return None, "o arquivo já está igual à última versão guardada"
        alvo = candidatas[-1]
    else:
        alvo = next((i for i in itens if i["n"] == n), None)
        if not alvo:
            return None, f"não existe a versão {n}"
    origem = os.path.join(pasta, alvo["arquivo"])
    if not os.path.isfile(origem):
        return None, "o arquivo dessa versão sumiu da pasta de versões"
    with open(origem, "rb") as f:
        dados = f.read()
    salvar_versao(caminho, f"antes de voltar pra v{alvo['n']}")
    _gravar_bytes(caminho, dados)
    return alvo, None


def _alvo_editavel(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext not in EXT_TEXTO:
        return f"só edito arquivos de texto ou código, não {ext or 'arquivo sem extensão'}"
    p = os.path.abspath(caminho).lower().replace("/", "\\")
    if any(x in p for x in PASTAS_PROIBIDAS):
        return "esse arquivo fica numa pasta de sistema"
    if os.path.getsize(caminho) > LIMITE_CHARS_EDICAO:
        return "o arquivo é grande demais pra eu editar"
    return None


def _ler_para_edicao(caminho):
    with open(caminho, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        enc = "utf-8-sig"
    else:
        try:
            raw.decode("utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            enc = "cp1252"
    crlf = raw.count(b"\r\n") > raw.count(b"\n") / 2
    return raw.decode(enc, errors="replace").replace("\r\n", "\n"), enc, crlf


def _gravar_texto(caminho, texto, enc, crlf):
    if crlf:
        texto = texto.replace("\n", "\r\n")
    _gravar_bytes(caminho, texto.encode(enc, errors="replace"))


_RE_BLOCO = re.compile(
    r"<{5,9}\s*(?:BUSCAR|SEARCH)[^\n]*\n(.*?)\n?={5,9}[ \t]*\n(.*?)\n?>{5,9}\s*(?:SUBSTITUIR|REPLACE)",
    re.S)


def _parse_blocos(resposta):
    resumo = ""
    m = re.search(r"^\s*RESUMO:\s*(.+)$", resposta, re.M)
    if m:
        resumo = m.group(1).strip()
    return resumo, _RE_BLOCO.findall(resposta)


def _aplicar_blocos(conteudo, blocos):
    erros, atual = [], conteudo
    for i, (busca, novo) in enumerate(blocos, 1):
        busca, novo = busca.replace("\r\n", "\n"), novo.replace("\r\n", "\n")
        if busca.strip() == "":
            atual = atual.rstrip("\n") + "\n\n" + novo.strip("\n") + "\n"
            continue
        vezes = atual.count(busca)
        if vezes == 1:
            atual = atual.replace(busca, novo, 1)
            continue
        if vezes > 1:
            erros.append(f"Bloco {i}: o trecho BUSCAR aparece {vezes} vezes; inclua mais linhas "
                         "de contexto pra ele ficar único.")
            continue
        linhas = atual.split("\n")
        alvo = [l.rstrip() for l in busca.strip("\n").split("\n")]
        k = len(alvo)
        achados = [j for j in range(len(linhas) - k + 1)
                   if [l.rstrip() for l in linhas[j:j + k]] == alvo]
        if len(achados) == 1:
            j = achados[0]
            novas = novo.strip("\n").split("\n") if novo.strip("\n") else []
            atual = "\n".join(linhas[:j] + novas + linhas[j + k:])
        elif len(achados) > 1:
            erros.append(f"Bloco {i}: o trecho BUSCAR aparece várias vezes; inclua mais contexto.")
        else:
            erros.append(f"Bloco {i}: não achei o trecho BUSCAR no arquivo (copie EXATAMENTE como "
                         f"está, com a mesma indentação). Começa com: {busca.strip()[:80]!r}")
    return atual, erros


_PERIGOS = [
    (r"\bos\.(?:remove|unlink|rmdir|removedirs|system|startfile|popen|rename|replace|kill)\b"
     r"|\bshutil\.(?:rmtree|move)\b|\bsend2trash\b|\.unlink\(",
     "apaga/move arquivos ou executa comandos"),
    (r"\bsubprocess\b|\bctypes\b|\bwinreg\b", "chama programas/Windows diretamente"),
    (r"\b(?:pynput|pyautogui|keyboard|mouse|serial|pyaudio|selenium|speech_recognition|"
     r"win32api|win32gui|tkinter|turtle|pygame|PyQt5|PyQt6|PySide2|PySide6|cv2)\b",
     "controla mouse/teclado/microfone/hardware ou abre janela"),
    (r"\b(?:requests|urllib|httpx|aiohttp|smtplib|socket|ftplib)\b", "acessa a rede"),
]


def _python_exe():
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[:-len("pythonw.exe")] + "python.exe"
    return exe


def _motivo_nao_rodar(caminho, texto):
    ext = os.path.splitext(caminho)[1].lower()
    if ext not in (".py", ".pyw"):
        return "não é um programa Python"
    protegidos = {os.path.normcase(os.path.abspath(p)) for p in _cfg["nao_rodar"] if p}
    if os.path.normcase(os.path.abspath(caminho)) in protegidos:
        return "é o programa que está rodando agora (rodar abriria outra cópia)"
    for padrao, motivo in _PERIGOS:
        if motivo == "acessa a rede" and PERMITIR_REDE_NA_EXECUCAO:
            continue
        if re.search(padrao, texto):
            return f"o código {motivo}"
    return None


def _pyflakes_msgs(texto):
    try:
        from pyflakes.api import check
        from pyflakes.reporter import Reporter
    except Exception:
        return None
    saida, erro = io.StringIO(), io.StringIO()
    check(texto, "arquivo.py", Reporter(saida, erro))
    msgs = []
    for linha in saida.getvalue().splitlines():
        m = re.match(r"arquivo\.py:(\d+)(?::\d+)?:? (.*)$", linha)
        if m and re.search(r"undefined name|undefined local|referenced before assignment|"
                           r"invalid syntax|unexpected indent", m.group(2)):
            msgs.append((m.group(1), m.group(2)))
    return msgs


def _preparar_sandbox(caminho_real, texto_novo):
    tmp = tempfile.mkdtemp(prefix="indianos_sbx_")
    base, copiados = os.path.dirname(os.path.abspath(caminho_real)), 0
    try:
        for f in os.listdir(base):
            p = os.path.join(base, f)
            if copiados >= 40:
                break
            if (os.path.isfile(p) and os.path.getsize(p) <= 1_000_000
                    and os.path.splitext(f)[1].lower() in EXT_TEXTO):
                shutil.copy2(p, os.path.join(tmp, f))
                copiados += 1
    except Exception:
        pass
    destino = os.path.join(tmp, os.path.basename(caminho_real))
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto_novo)
    return tmp, destino


def _rodar(args, cwd):
    env = {k: v for k, v in os.environ.items()
           if not re.search(r"GEMINI|API[_-]?KEY|TOKEN|SECRET|PASSW|SENHA", k, re.I)}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_EXECUCAO,
                           stdin=subprocess.DEVNULL, env=env)
        return r.returncode, r.stdout or "", r.stderr or "", False
    except subprocess.TimeoutExpired:
        return None, "", "", True


def _resumo_erro(stderr, tmp):
    linhas = (stderr or "").replace(tmp + os.sep, "").strip().splitlines()
    return "\n".join(linhas[-30:])


def verificar(texto_novo, caminho, texto_orig=None, executar=True):
    ext = os.path.splitext(caminho)[1].lower()
    checks = []

    def falha(onde, msg):
        return {"ok": False, "onde": onde, "msg": msg, "checks": checks}

    if ext == ".json":
        try:
            json.loads(texto_novo)
            return {"ok": True, "onde": "", "msg": "", "checks": ["JSON válido"]}
        except Exception as e:
            return falha("json", f"JSON inválido: {e}")

    if ext not in (".py", ".pyw"):
        return {"ok": True, "onde": "", "msg": "", "checks": ["sem verificação automática pra esse tipo"]}

    erro = _erro_sintaxe_python(texto_novo)
    if erro:
        return falha("sintaxe", f"SyntaxError na {erro}")
    checks.append("sintaxe ok")

    novos = _pyflakes_msgs(texto_novo)
    if novos is None:
        checks.append("sem pyflakes (pip install pyflakes acha mais erros)")
    else:
        antigos = {m for _, m in (_pyflakes_msgs(texto_orig) or [])} if texto_orig else set()
        so_novos = [f"linha {l}: {m}" for l, m in novos if m not in antigos]
        if so_novos:
            return falha("nomes", "\n".join(so_novos[:15]))
        checks.append("nomes/imports ok")

    if not executar:
        return {"ok": True, "onde": "", "msg": "", "checks": checks}

    motivo = _motivo_nao_rodar(caminho, texto_novo)
    if motivo:
        checks.append(f"não rodei: {motivo}")
        return {"ok": True, "onde": "", "msg": "", "checks": checks}

    tmp, destino = _preparar_sandbox(caminho, texto_novo)
    try:
        base = os.path.splitext(os.path.basename(caminho))[0]
        teste = next((t for t in (f"test_{base}.py", f"{base}_test.py")
                      if os.path.isfile(os.path.join(tmp, t))), None)
        if teste:
            cod, out, err, estourou = _rodar([_python_exe(), "-X", "utf8", teste], tmp)
            if cod not in (0, None):
                return falha("testes", f"O teste {teste} falhou:\n{_resumo_erro(err or out, tmp)}")
            checks.append(f"teste {teste} {'passou' if cod == 0 else 'rodou sem terminar'}")

        cod, out, err, estourou = _rodar([_python_exe(), "-X", "utf8", destino], tmp)
        if estourou:
            checks.append(f"rodou {TIMEOUT_EXECUCAO}s sem erro (loop/servidor?), considerei ok")
        elif cod == 0:
            checks.append("rodou sem erro")
        elif "EOFError" in err and "input" in err.lower():
            checks.append("pede digitação (input): não dá pra rodar sozinha")
        elif cod == 2 and "usage:" in err.lower():
            checks.append("precisa de argumentos: não dá pra rodar sozinha")
        else:
            return falha("execução", _resumo_erro(err, tmp) or f"saiu com código {cod}")
        return {"ok": True, "onde": "", "msg": "", "checks": checks}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _prompt_edicao(pedido, nome, conteudo, erro, tentativa):
    instr = (
        "Você é a Indianos Remaster, editora de código. Edite o arquivo conforme o pedido usando "
        "SOMENTE blocos de busca e substituição neste formato EXATO (quantos blocos precisar):\n\n"
        "<<<<<<< BUSCAR\n(trecho EXATO que já existe no arquivo, com 2+ linhas de contexto, copiado "
        "sem mudar espaços nem indentação)\n=======\n(trecho novo que substitui)\n>>>>>>> SUBSTITUIR\n\n"
        "Regras: cada BUSCAR tem que aparecer UMA ÚNICA vez no arquivo; não reescreva o arquivo "
        "inteiro; mude o mínimo necessário e mantenha o estilo; pra acrescentar algo no FINAL do "
        "arquivo deixe o BUSCAR vazio. Antes dos blocos escreva UMA linha começando com 'RESUMO:' "
        "dizendo o que muda. Sem markdown e sem ```.\n\n"
        f"PEDIDO: {pedido}\n"
    )
    if erro:
        intro = ("Problema apontado ANTES de editar" if tentativa == 1 else
                 f"TENTATIVA {tentativa} de {MAX_TENTATIVAS}. Houve um problema na tentativa anterior")
        instr += f"\n{intro}, corrija:\n{erro}\n"
    return instr + f"\n=== ARQUIVO A EDITAR: {nome} ===\n{conteudo}"


def _stats_diff(antes, depois):
    add = rem = 0
    for l in difflib.ndiff(antes.splitlines(), depois.splitlines()):
        if l.startswith("+ "):
            add += 1
        elif l.startswith("- "):
            rem += 1
    return add, rem


def editar_com_autonomia(pedido, caminho, refs=(), so_testar=False, diagnosticar=False):
    nome = os.path.basename(caminho)
    motivo = _alvo_editavel(caminho)
    if motivo:
        _falar(f"Não vou editar {nome}: {motivo}.")
        return None
    orig, enc, crlf = _ler_para_edicao(caminho)

    erro = None
    ref_flakes = orig
    if so_testar:
        ref_flakes = None
        res = verificar(orig, caminho, texto_orig=None, executar=True)
        if res["ok"]:
            _mostrar("Conferi: " + ", ".join(res["checks"]))
            _falar("Conferi o arquivo e não achei erro. " + "; ".join(res["checks"]) + ".")
            return caminho
        erro = f"Ao verificar o arquivo atual a verificação falhou ({res['onde']}):\n{res['msg']}"
        pedido = "Corrija o erro apontado, mudando o mínimo possível."
        print(f"[Arquivos IA] erro inicial:\n{erro}")
    elif diagnosticar:
        res0 = verificar(orig, caminho, texto_orig=None, executar=True)
        if not res0["ok"]:
            ref_flakes = None
            erro = f"A verificação do arquivo atual falhou ({res0['onde']}):\n{res0['msg']}"
            print(f"[Arquivos IA] diagnóstico inicial:\n{erro}")

    refs_parts = []
    if refs:
        refs_parts, _, _ = _juntar(list(refs))

    atual, melhor, resumo = orig, None, ""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        _mostrar(f"Editando {nome}... tentativa {tentativa}/{MAX_TENTATIVAS}")
        resp = _gemini([{"text": _prompt_edicao(pedido, nome, atual, erro, tentativa)}] + refs_parts,
                       timeout=150)
        if not resp:
            _falar("A API não respondeu agora. O arquivo não foi alterado.")
            return None
        resumo_t, blocos = _parse_blocos(resp)
        resumo = resumo_t or resumo
        if not blocos:
            erro = "Você não devolveu nenhum bloco no formato BUSCAR/SUBSTITUIR."
            continue
        novo, erros_aplic = _aplicar_blocos(atual, blocos)
        if erros_aplic:
            erro = "Não consegui aplicar seus blocos:\n" + "\n".join(erros_aplic)
            print(f"[Arquivos IA] {erro}")
            continue
        res = verificar(novo, caminho, texto_orig=ref_flakes, executar=True)
        if res["ok"]:
            item = salvar_versao(caminho, f"antes de: {pedido}")
            _gravar_texto(caminho, novo, enc, crlf)
            add, rem = _stats_diff(orig, novo)
            _auditar("EDITAR ARQUIVO", f"{caminho} (+{add}/-{rem}, v{item['n']}, {tentativa} tentativa(s))")
            aviso = ""
            protegidos = {os.path.normcase(os.path.abspath(p)) for p in _cfg["nao_rodar"] if p}
            if os.path.normcase(os.path.abspath(caminho)) in protegidos:
                aviso = " Como esse é o meu próprio código, só vale quando você me reiniciar."
            vezes = "de primeira" if tentativa == 1 else f"na tentativa {tentativa}, depois de me corrigir sozinha"
            msg = (f"Pronto, editei {nome} {vezes}. {resumo or ''} Mudei mais {add} e menos {rem} linhas. "
                   f"A versão anterior ficou guardada como v{item['n']}. Conferi: {'; '.join(res['checks'])}.{aviso}")
            print(f"[Arquivos IA] {msg}")
            _mostrar(f"✅ {nome} editado (v{item['n']} guardada)")
            _falar(_para_fala(msg, 420))
            return caminho
        erro = (f"Depois da sua edição a verificação falhou ({res['onde']}):\n{res['msg']}")
        print(f"[Arquivos IA] tentativa {tentativa} falhou:\n{erro}")
        atual, melhor = novo, novo

    guardado = ""
    if melhor:
        ext = os.path.splitext(nome)[1]
        saida = _nome_livre(os.path.join(_cfg["pasta_codigos"],
                                         f"{os.path.splitext(nome)[0]}_tentativa_{_carimbo()}{ext}"))
        os.makedirs(_cfg["pasta_codigos"], exist_ok=True)
        with open(saida, "w", encoding="utf-8", newline="\n") as f:
            f.write(melhor)
        guardado = f" Salvei a melhor tentativa em {os.path.basename(saida)} pra você olhar."
    _mostrar(f"❌ Não consegui deixar {nome} sem erro")
    _falar(f"Tentei {MAX_TENTATIVAS} vezes e não consegui deixar sem erro, então não mexi no arquivo "
           f"original.{guardado}")
    return None


def desfazer(caminho, n=None):
    item, erro = restaurar(caminho, n)
    nome = os.path.basename(caminho)
    if erro:
        _falar(f"Não consegui voltar {nome}: {erro}.")
        return None
    _auditar("RESTAURAR ARQUIVO", f"{caminho} <- v{item['n']}")
    _mostrar(f"↩️ {nome} voltou pra v{item['n']}")
    _falar(f"Voltei {os.path.basename(caminho)} pra versão {item['n']}, de {item['data']}. "
           "Se quiser refazer, é só desfazer de novo.")
    return caminho


def mostrar_versoes(caminho):
    itens = listar_versoes(caminho)
    nome = os.path.basename(caminho)
    if not itens:
        _falar(f"Não tenho nenhuma versão guardada de {nome} ainda.")
        return None
    linhas = [f"v{i['n']} — {i['data']} — {i['motivo']}" for i in itens]
    print(f"\n[Arquivos IA] Versões de {nome}:\n" + "\n".join(linhas) + "\n")
    _mostrar(f"{nome}: {len(itens)} versões (veja o console)")
    ult = itens[-1]
    _falar(f"{nome} tem {len(itens)} versões guardadas. A mais recente é a {ult['n']}, de {ult['data']}.")
    return itens


_COPIAR = ("copia", "copie", "duplica", "duplique", "clona", "clone")
_BASEADO = ("baseado", "baseada", "baseando", "com base", "a partir d", "converte",
            "converta", "traduz", "traduza")
_EDITAR = ("edita", "edite", "altera", "altere", "modifica", "modifique", "conserta",
           "conserte", "arruma", "arrume", "corrige", "corrija", "melhora", "melhore",
           "adiciona", "adicione", "atualiza", "atualize", "refatora", "refatore",
           "otimiza", "otimize", "muda", "mude", "troca", "substitui")
_TESTAR = ("roda", "rode", "executa", "execute", "testa", "teste")
_DESFAZER = ("desfaz", "desfac", "volta", "reverte", "reverta", "restaura", "restaure")
_VERSOES = ("versoes", "versao", "historico")
_ANALISAR = ("analis", "resum", "explic", "le o arquivo", "leia", "ler o arquivo",
             "o que tem", "o que faz", "revis", "confere", "confira")


def _detectar_acao(trecho):
    if any(v in trecho for v in _DESFAZER):
        return "desfazer"
    if any(v in trecho for v in _VERSOES):
        return "versoes"
    if any(v in trecho for v in _COPIAR):
        return "copiar"
    if any(v in trecho for v in _BASEADO):
        return "codar"
    if any(v in trecho for v in _EDITAR):
        return "editar"
    if any(v in trecho for v in _TESTAR):
        return "testar"
    if any(v in trecho for v in _ANALISAR):
        return "analisar"
    return None


def _sem_nomes(texto_min):
    t = _norm(texto_min)
    for n in extrair_nomes(texto_min):
        if n != "__ultimo__":
            t = t.replace(_norm(n), " ")
    return t


def tratar_comando(texto, texto_min):
    t = _norm(texto_min)
    if "arquivo" not in t:
        return False
    antes = t.split("arquivo")[0]
    verbo_destrutivo = r"\b(?:apag|delet|exclu|remov|mov|transfer|manda|leva)\w*"
    parte_do_arquivo = (r"(?:\s+(?:a|o|as|os|essa|esse|uma|um))?\s+(?:funcao|funcoes|linha|linhas|"
                        r"trecho|parte|codigo|bloco|classe|metodo|import|imports|comentario|"
                        r"comentarios|variavel)")
    edicao_parcial = bool(re.search(verbo_destrutivo + parte_do_arquivo, antes))
    if not edicao_parcial and re.search(r"\b(?:apag|delet|exclu|remov)\w*", antes):
        return False
    if not edicao_parcial and re.search(r"\b(?:mov|transfer|manda|leva)\w*", antes):
        acao = "mover"
    else:
        acao = "editar" if edicao_parcial else (
            _detectar_acao(antes) or _detectar_acao(_sem_nomes(texto_min)))
    if not acao:
        return False
    threading.Thread(target=_executar, args=(acao, texto, texto_min), daemon=True).start()
    return True


def _executar(acao, texto, texto_min):
    try:
        if acao == "copiar":
            copiar(texto_min)
            return
        if acao == "mover":
            mover(texto_min)
            return
        t = _norm(texto_min)
        nomes = extrair_nomes(texto_min)
        caminhos, faltando = [], []
        for n in nomes:
            p = resolver(n)
            if not p:
                faltando.append(n)
            elif p not in caminhos:
                caminhos.append(p)
        if not caminhos:
            _falar("Não encontrei esse arquivo. Fala o nome com a extensão, "
                   "ou manda pelo celular e pede o último arquivo que você mandou.")
            return
        if faltando:
            _falar(f"Não achei {', '.join(faltando)}, vou seguir só com o que achei.")
        print(f"[Arquivos IA] {acao}: {caminhos}")
        _mostrar(f"Arquivo: {', '.join(os.path.basename(c) for c in caminhos)}")
        if acao == "analisar":
            analisar(texto, caminhos)
        elif acao == "codar":
            codar_baseado(texto, caminhos)
        elif acao == "editar":
            diag = bool(re.search(r"corrig|conserta|conserte|arruma|arrume|debug|\bbug|erro",
                                  _sem_nomes(texto_min)))
            editar_com_autonomia(texto, caminhos[0], refs=caminhos[1:], diagnosticar=diag)
        elif acao == "testar":
            editar_com_autonomia(texto, caminhos[0], so_testar=True)
        elif acao == "desfazer":
            m = re.search(r"versao\s*(\d+)|\bv\s*(\d+)\b", t)
            desfazer(caminhos[0], int(m.group(1) or m.group(2)) if m else None)
        elif acao == "versoes":
            mostrar_versoes(caminhos[0])
    except Exception as e:
        print(f"[Arquivos IA] erro: {e}")
        _falar("Tive um problema com esse arquivo.")
