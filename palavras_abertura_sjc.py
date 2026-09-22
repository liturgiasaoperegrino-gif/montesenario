# -*- coding: utf-8 -*-
"""
palavras_abertura_sjc.py — Montesenario

Extrai conteúdo do boletim dominical "Semanário Litúrgico" da Diocese
de São José dos Campos, publicado mensalmente em PDF na categoria
"Nova Aliança" do site da diocese:
    https://diocese-sjc.org.br/categoria/nova-alianca/

Cobre 3 seções do roteiro, todas extraídas de UM ÚNICO download do PDF
do dia (ver obter_conteudo_boletim):
  - Seção 02 (palavras de abertura) — a introdução antes do Canto de
    Abertura.
  - Seção 11 (Aclamação ao Evangelho) — refrão + versículo. Usada como
    FALLBACK do Pocket Terço (fonte principal — ver
    scraper.extrair_aclamacao_pocketterco), pra quando este não
    responder.
  - Seção 16 (Prefácio) — nome/referência (ex.: "Prefácio dos
    Domingos do Tempo Comum IX") e texto completo, extraídos de dentro
    da seção "Oração Eucarística" do boletim. Único automatismo para o
    Prefácio; a seleção manual pela pasta do Drive continua disponível
    e tem prioridade se o operador escolher outra.

Só cobre domingos — é um boletim dominical. Em dia de semana, cada
função retorna None/vazio e a respectiva seção do roteiro segue no
comportamento de antes (em branco ou dependente de outra fonte).

Fluxo:
1. Página do mês (uma por mês, reúne os PDFs de todos os domingos):
       https://diocese-sjc.org.br/nova-alianca-{mes}-{ano}/
2. Nessa página, acha o link cujo texto visível começa com
   "{DD} de {mes}" (ex.: "20 de setembro - 25º Domingo do Tempo
   Comum") e pega a URL do .pdf correspondente.
3. Baixa o PDF e extrai o texto com pdfplumber (uma vez só).
4. Cada seção é isolada por regex sobre esse texto — ver cada função
   _extrair_* abaixo para o padrão exato confirmado por inspeção
   manual em 20/09/2026 (numeração de seção do próprio boletim: 1.
   CANTO DE ABERTURA ... 10. ACLAMAÇÃO AO EVANGELHO ... 15. ORAÇÃO
   EUCARÍSTICA II (Prefácio dos Domingos do Tempo Comum IX – MR, pág.
   482) ...).

Requisitos:
    pip install requests beautifulsoup4 pdfplumber
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
except ImportError:  # tratado em tempo de execução — ver obter_palavras_abertura
    pdfplumber = None

BASE_URL = "https://diocese-sjc.org.br"

# Cópia local (não importa de scraper.py): scraper.py importa deste
# módulo para as palavras de abertura, então importar de volta criaria
# um import circular (ImportError na inicialização do Streamlit Cloud).
MESES = {
    1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril", 5: "maio",
    6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
    11: "novembro", 12: "dezembro",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _sem_acento(txt: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c)
    )


def montar_url_categoria(dia: date) -> str:
    mes_nome = MESES[dia.month]
    return f"{BASE_URL}/nova-alianca-{mes_nome}-{dia.year}/"


def _achar_url_pdf(dia: date) -> Optional[str]:
    """Abre a página mensal e procura o link cujo texto visível começa
    com '{DD} de {mes}' (ignorando maiúsculas/acentos), devolvendo a
    URL do PDF correspondente a esse dia. None se a página do mês
    ainda não existir, ou não tiver link para esse dia específico
    (comum em dia de semana — o boletim é só dominical)."""
    url_categoria = montar_url_categoria(dia)
    try:
        resp = requests.get(url_categoria, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return None

    # BeautifulSoup detecta o charset sozinho a partir dos bytes brutos
    # (meta tag/BOM), mais confiável que o "chute" do requests quando o
    # header Content-Type não declara charset explicitamente.
    soup = BeautifulSoup(resp.content, "html.parser")
    alvo = _sem_acento(f"{dia.day:02d} de {MESES[dia.month]}").lower()

    for link in soup.find_all("a", href=True):
        texto = _sem_acento(link.get_text(" ", strip=True)).lower()
        if texto.startswith(alvo) and link["href"].lower().endswith(".pdf"):
            href = link["href"]
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    return None


# Próximo cabeçalho numerado do boletim (ex.: "11. PROFISSÃO DE FÉ"),
# usado como limite direito ao isolar uma seção — mais confiável do que
# listar cada nome de seção manualmente, já que todas são numeradas.
_PROXIMO_CABECALHO = re.compile(r"\n\s*\d{1,2}\s*[.\-–]\s*[A-ZÀ-Ú]")

_PADRAO_ACLAMACAO_SEM_SIMBOLO = re.compile(
    r"(Aleluia,?\s*Aleluia,?\s*Aleluia\.?)\s*(.*)", re.IGNORECASE | re.DOTALL
)


def _isolar_secao(texto_pdf: str, cabecalho_regex: str) -> str:
    """Isola o texto entre um cabeçalho numerado (ex.: 'ACLAMAÇÃO AO
    EVANGELHO', com ou sem o número/pontuação na frente) e o próximo
    cabeçalho numerado do boletim. String vazia se o cabeçalho não for
    encontrado."""
    m_ini = re.search(
        r"\d{1,2}\s*[.\-–]\s*" + cabecalho_regex, texto_pdf, flags=re.IGNORECASE
    )
    if not m_ini:
        return ""
    resto = texto_pdf[m_ini.end():]
    m_fim = _PROXIMO_CABECALHO.search(resto)
    return (resto[: m_fim.start()] if m_fim else resto).strip()


def _extrair_introducao(texto_pdf: str) -> str:
    """A introdução fica entre a linha do título do dia (última linha
    em CAIXA ALTA contendo 'DOMINGO'/'SOLENIDADE'/'FESTA'/etc. antes do
    Canto de Abertura) e o cabeçalho 'CANTO DE ABERTURA'. Levanta
    ValueError se não achar os dois marcadores — o chamador trata isso
    como parsing malsucedido (formato do boletim pode ter mudado)."""
    m_fim = re.search(r"CANTO\s+DE\s+ABERTURA", texto_pdf, flags=re.IGNORECASE)
    if not m_fim:
        raise ValueError("marcador 'CANTO DE ABERTURA' não encontrado")

    antes = texto_pdf[: m_fim.start()]
    m_titulo = None
    for m in re.finditer(
        r"^.*\b(DOMINGO|SOLENIDADE|FESTA|MEM[ÓO]RIA|QUARTA-FEIRA DE CINZAS)\b.*$",
        antes, flags=re.IGNORECASE | re.MULTILINE,
    ):
        m_titulo = m  # fica com a ÚLTIMA ocorrência antes do Canto de Abertura

    if not m_titulo:
        raise ValueError("linha do título do dia não encontrada")

    introducao = antes[m_titulo.end():].strip()
    introducao = re.sub(r"\n{2,}", "\n\n", introducao)
    # As quebras de linha simples que sobram são apenas o "wrap" de linha
    # da coluna estreita do PDF original, não quebras de parágrafo de
    # verdade — se preservadas, viram <br/> forçado no PDF gerado, e o
    # ReportLab não estica (justifica) uma linha terminada em <br/>.
    # Protege as quebras de parágrafo reais (\n\n), troca as simples por
    # espaço, e depois restaura os parágrafos.
    _MARCA_PARAGRAFO = "\x00PARA\x00"
    introducao = introducao.replace("\n\n", _MARCA_PARAGRAFO)
    introducao = introducao.replace("\n", " ")
    introducao = introducao.replace(_MARCA_PARAGRAFO, "\n\n")
    introducao = re.sub(r"[ \t]+", " ", introducao)
    # O boletim numera "1. CANTO DE ABERTURA" — como o corte acima é
    # antes de "CANTO DE ABERTURA", sobra o número/pontuação soltos
    # ("...vinha.\n\n1.") no fim; remove esse resto.
    introducao = re.sub(r"\s*\d{1,2}\s*[.\-–]\s*$", "", introducao).strip()
    if not introducao:
        raise ValueError("introdução veio vazia")
    return introducao


def _extrair_aclamacao(texto_pdf: str) -> dict:
    """{'refrao': str, 'versiculo': str} a partir da seção 'ACLAMAÇÃO
    AO EVANGELHO' do boletim — usada como fallback do Pocket Terço
    (fonte principal). Levanta ValueError se a seção não existir ou
    não tiver o padrão 'Aleluia, Aleluia, Aleluia. <versículo>'.

    BUG REAL corrigido em 21/09/2026 (2ª rodada, boletim real de
    27/09/2026): nesta edição não existe cabeçalho numerado próprio
    para o Evangelho logo depois da Aclamação — o texto emenda direto
    do versículo pro diálogo fixo do Evangelho ('- O Senhor esteja
    convosco! - Ele está no meio de nós. - Proclamação do Evangelho...')
    e daí pro texto integral do Evangelho. Sem um cabeçalho pra cortar,
    _isolar_secao ia até o PRÓXIMO cabeçalho numerado de verdade —
    bem mais adiante — trazendo o Evangelho inteiro junto com o
    versículo. Corrigido: o versículo termina no primeiro parágrafo
    daquele bloco (a fonte separa os parágrafos por linha em branco);
    o que vem depois (diálogo com marcador '-') é sempre outra coisa."""
    bloco = _isolar_secao(texto_pdf, r"ACLAMA[ÇC][ÃA]O\s+AO\s+EVANGELHO")
    if not bloco:
        raise ValueError("seção 'ACLAMAÇÃO AO EVANGELHO' não encontrada")
    m = _PADRAO_ACLAMACAO_SEM_SIMBOLO.search(bloco)
    if not m or not m.group(1).strip():
        raise ValueError("padrão 'Aleluia...' não encontrado no bloco")
    versiculo_bruto = m.group(2)
    m_fim_versiculo = re.search(r"\n\s*-", versiculo_bruto)
    versiculo = versiculo_bruto[: m_fim_versiculo.start()] if m_fim_versiculo else versiculo_bruto
    versiculo = re.sub(r"\s+", " ", versiculo).strip()
    if not versiculo:
        raise ValueError("versículo da Aclamação veio vazio")
    return {"refrao": m.group(1).strip(), "versiculo": versiculo}


def _extrair_oferendas(texto_pdf: str) -> str:
    """Texto da seção de Oferendas do boletim — usada como fallback
    (Seção 15) quando nem o OSM nem o Pocket Terço têm essa oração para
    a data. Levanta ValueError se a seção não existir (o chamador trata
    isso como 'esta fonte também não tem').

    BUG REAL corrigido em 21/09/2026 (relatado pelo usuário, por
    inspeção do texto bruto): o cabeçalho real do boletim não é
    'ORAÇÃO SOBRE AS OFERENDAS' (isso era um chute de uma rodada
    anterior, nunca confirmado contra o PDF de verdade) — é uma
    anotação entre parênteses, '(Sobre as Oferendas)', sem a palavra
    'Oração' na frente. Por isso a seção nunca era encontrada.

    BUG REAL corrigido em 21/09/2026 (2ª rodada, com o boletim de
    verdade de 27/09/2026): nem toda edição usa a anotação entre
    parênteses — algumas trazem só o cabeçalho numerado direto
    ('13. ORAÇÃO SOBRE AS OFERENDAS', sem o '(Sobre as Oferendas)').
    Aceita os dois formatos."""
    m_ini = re.search(
        r"\(\s*Sobre\s+as\s+Ofere[nm]das\s*\)"
        r"|\d{1,2}\s*[.\-–]\s*ORA[ÇC][ÃA]O\s+SOBRE\s+AS\s+OFERE[NM]DAS",
        texto_pdf, flags=re.IGNORECASE,
    )
    if not m_ini:
        raise ValueError("cabeçalho da Oração sobre as Oferendas não encontrado")
    resto = texto_pdf[m_ini.end():]
    m_fim = _PROXIMO_CABECALHO.search(resto)
    bloco = (resto[: m_fim.start()] if m_fim else resto).strip()
    if not bloco:
        raise ValueError("seção 'Sobre as Oferendas' veio vazia")
    return re.sub(r"\s+", " ", bloco).strip()


def _extrair_comunhao(texto_pdf: str) -> str:
    """Texto da seção de Comunhão do boletim — usada como fallback
    (Seção 18) SÓ quando nem o OSM nem o Pocket Terço têm essa oração
    para a data (por decisão do usuário: esta fonte é a menos confiável
    das três, por vir de PDF em duas colunas — ver
    _extrair_texto_pagina_pdf — por isso é sempre a última tentativa).

    Cabeçalho real (mesmo formato de _extrair_oferendas, corrigido em
    21/09/2026): anotação entre parênteses, sem a palavra 'Oração' na
    frente. Delimitado pelo conteúdo em si ('Oremos' ... 'Amém'),
    informado pelo usuário, em vez de só o próximo cabeçalho numerado —
    mais resistente a essa seção vir emendada com a coluna vizinha.

    BUG REAL corrigido em 21/09/2026 (2ª rodada, com o boletim de
    verdade de 27/09/2026): esta edição não tem a anotação entre
    parênteses nenhuma — só o cabeçalho numerado direto ('18. ORAÇÃO
    DEPOIS DA COMUNHÃO'). Aceita os dois formatos."""
    m_ini = re.search(
        r"\(\s*Depois\s+da\s+Comunh[ãa]o\s*\)"
        r"|\d{1,2}\s*[.\-–]\s*ORA[ÇC][ÃA]O\s+DEPOIS\s+DA\s+COMUNH[ÃA]O",
        texto_pdf, flags=re.IGNORECASE,
    )
    if not m_ini:
        raise ValueError("cabeçalho da Oração Depois da Comunhão não encontrado")
    resto = texto_pdf[m_ini.end():]
    m_oremos = re.search(r"\bOremos\b", resto, flags=re.IGNORECASE)
    if not m_oremos:
        raise ValueError("início 'Oremos' da Oração Depois da Comunhão não encontrado")
    resto = resto[m_oremos.start():]
    m_amem = re.search(r"Am[ée]m\.?", resto, flags=re.IGNORECASE)
    bloco = resto[: m_amem.end()] if m_amem else resto
    bloco = bloco.strip()
    if not bloco:
        raise ValueError("seção 'Depois da Comunhão' veio vazia")
    return re.sub(r"\s+", " ", bloco).strip()


def _extrair_prefacio(texto_pdf: str) -> dict:
    """{'nome': str, 'texto': str} a partir da seção 'ORAÇÃO
    EUCARÍSTICA' do boletim — confirmado por inspeção manual em
    20/09/2026: logo após o cabeçalho ('15. ORAÇÃO EUCARÍSTICA II')
    vem uma referência entre parênteses ('(Prefácio dos Domingos do
    Tempo Comum IX – MR, pág. 482)') e, em seguida, o texto do
    Prefácio até 'Santo, Santo, Santo' (o Santo não entra — é a
    resposta da assembleia, já coberta por oracoes_eucaristicas.py).
    Levanta ValueError se algum desses marcadores não for encontrado."""
    m_secao = re.search(
        r"\d{1,2}\s*[.\-–]\s*ORA[ÇC][ÃA]O\s+EUCAR[ÍI]STICA", texto_pdf, flags=re.IGNORECASE
    )
    if not m_secao:
        raise ValueError("seção 'ORAÇÃO EUCARÍSTICA' não encontrada")

    resto = texto_pdf[m_secao.end():]
    m_nome = re.search(r"\(([^)]+)\)", resto)
    if not m_nome:
        raise ValueError("referência entre parênteses do Prefácio não encontrada")

    depois_do_nome = resto[m_nome.end():]
    m_santo = re.search(r"Santo,?\s*Santo,?\s*Santo", depois_do_nome, flags=re.IGNORECASE)
    texto_prefacio = depois_do_nome[: m_santo.start()] if m_santo else depois_do_nome
    texto_prefacio = re.sub(r"\s+", " ", texto_prefacio).strip()
    if not texto_prefacio:
        raise ValueError("texto do Prefácio veio vazio")

    # BUG REAL encontrado em 21/09/2026 (boletim real de 27/09/2026):
    # quando o nome do Prefácio é longo, ele quebra em duas linhas
    # físicas na página (ex.: "(Prefácio dos Domingos do Tempo Comum" /
    # "VII – MR, pág. 480)") — sem normalizar, o "\n" entre as duas
    # linhas ia parar dentro do nome gravado na planilha.
    nome_prefacio = re.sub(r"\s+", " ", m_nome.group(1)).strip()
    return {"nome": nome_prefacio, "texto": texto_prefacio}


def _agrupar_em_linhas(palavras: list, tolerancia: float = 3.0) -> list:
    """Agrupa uma lista de palavras (dicts do pdfplumber, com 'top' e
    'x0') em linhas — palavras cujo topo difere por até `tolerancia`
    pontos entram na mesma linha (nem toda palavra de uma linha tem o
    'top' idêntico bit a bit, por causa de fontes/kerning). Cada linha
    volta ordenada da esquerda pra direita."""
    if not palavras:
        return []
    ordenadas = sorted(palavras, key=lambda p: p["top"])
    linhas, linha_atual, referencia = [], [], None
    for p in ordenadas:
        if referencia is None or abs(p["top"] - referencia) <= tolerancia:
            linha_atual.append(p)
            if referencia is None:
                referencia = p["top"]
        else:
            linhas.append(linha_atual)
            linha_atual, referencia = [p], p["top"]
    if linha_atual:
        linhas.append(linha_atual)
    return [sorted(l, key=lambda p: p["x0"]) for l in linhas]


def _extrair_texto_pagina_pdf(page) -> str:
    """Extrai o texto de UMA página respeitando um possível layout em
    DUAS COLUNAS — comum em boletins paroquiais/diocesanos (a
    'folhinha' impressa, pra economizar papel). O `page.extract_text()`
    padrão do pdfplumber ordena as palavras primeiro pela posição
    vertical e só depois pela horizontal: numa página de duas colunas
    isso INTERCALA o texto das duas colunas linha a linha (frase da
    esquerda, frase da direita, frase da esquerda...), produzindo uma
    bagunça — bug real relatado pelo usuário em 21/09/2026: corrompia a
    Aclamação (fallback deste boletim) e o Prefácio (Seção 16, único
    automatismo, também extraído daqui), misturando o texto litúrgico
    com avisos/orações de outra coluna da página.

    Detecção: separa as palavras pela metade da largura da página: só
    trata como "duas colunas de verdade" quando praticamente todas as
    palavras caem claramente de um lado ou do outro (não espalhadas
    pelo meio, como seria um título centralizado) E existe uma lacuna
    horizontal real entre o fim de uma metade e o início da outra. Sem
    essas duas condições, é mais seguro assumir coluna única e usar o
    texto corrido normal do pdfplumber, sem risco de cortar uma página
    de uma coluna só ao meio."""
    palavras = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not palavras:
        return page.extract_text() or ""

    meio = page.width / 2
    esquerda = [p for p in palavras if p["x1"] <= meio]
    direita = [p for p in palavras if p["x0"] >= meio]

    classificadas = len(esquerda) + len(direita)
    if not esquerda or not direita or classificadas < 0.9 * len(palavras):
        return page.extract_text() or ""

    # BUG REAL encontrado em 21/09/2026 com o boletim de verdade de
    # 27/09/2026 (o próprio arquivo, não mais um exemplo simulado): a
    # lacuna entre colunas era medida pelo par de palavras mais PRÓXIMO
    # da página inteira (min x0 da direita − max x1 da esquerda). Um
    # único par isolado que, por hifenização/pontuação/justificação,
    # ficasse mais perto do meio que o normal já derrubava essa medida
    # — e como o teste de sanidade abaixo exigia pelo menos 3% da
    # largura da página, essa página (cuja lacuna real entre colunas é
    # de ~14pt, menor que os ~18pt exigidos) caía no "não são duas
    # colunas de verdade" e usava page.extract_text() puro — voltando a
    # intercalar o texto das duas colunas linha a linha (exatamente o
    # bug original que essa função existe pra evitar). Corrigido:
    # calcula a lacuna LINHA A LINHA (só nas linhas que realmente têm
    # palavra dos dois lados) e usa a MEDIANA — resistente a esse tipo
    # de outlier isolado — com um limiar bem mais baixo (a lacuna real
    # entre colunas varia de boletim pra boletim; o que importa é ela
    # ser claramente maior que um espaço comum entre palavras, ~3-5pt).
    gaps_por_linha = []
    for linha in _agrupar_em_linhas(palavras):
        esq_da_linha = [p for p in linha if p["x1"] <= meio]
        dir_da_linha = [p for p in linha if p["x0"] >= meio]
        if esq_da_linha and dir_da_linha:
            gaps_por_linha.append(
                min(p["x0"] for p in dir_da_linha) - max(p["x1"] for p in esq_da_linha)
            )
    if not gaps_por_linha:
        return page.extract_text() or ""
    gaps_por_linha.sort()
    lacuna = gaps_por_linha[len(gaps_por_linha) // 2]  # mediana
    if lacuna < page.width * 0.01:
        return page.extract_text() or ""

    # BUG REAL corrigido em 21/09/2026 (relatado pelo usuário): um
    # título/cabeçalho de seção que atravessa a largura inteira da
    # página (ex.: "16. ORAÇÃO EUCARÍSTICA II (Prefácio dos Domingos do
    # Tempo Comum VII)") tem palavras dos dois lados do meio da página
    # — a divisão acima trata essas palavras como se fossem duas
    # colunas de verdade, e a palavra final do título (ex.: "VII") vai
    # parar longe do resto da frase, misturada com o conteúdo real da
    # coluna direita naquela altura da página.
    #
    # Detecção: agrupa TODAS as palavras da página em linhas (por
    # posição vertical) e mede, em cada linha, o MAIOR espaço entre
    # palavras vizinhas. Numa linha de largura inteira esse espaço é um
    # espaço comum entre palavras; numa linha que é, na verdade, DUAS
    # colunas coincidindo na mesma altura, esse espaço bate perto da
    # lacuna real da coluna (bem maior que um espaço comum). Linhas de
    # largura inteira (que cruzam o meio da página) são extraídas à
    # parte e reinseridas na posição vertical correta entre os blocos
    # de coluna — nunca divididas.
    todas_as_linhas = _agrupar_em_linhas(palavras)
    linhas_largura_inteira = []
    ids_palavras_de_titulo = set()
    for linha in todas_as_linhas:
        if len(linha) < 2:
            continue
        cruza_o_meio = linha[0]["x0"] < meio < linha[-1]["x1"]
        if not cruza_o_meio:
            continue
        maior_espaco = max(b["x0"] - a["x1"] for a, b in zip(linha, linha[1:]))
        if maior_espaco < lacuna * 0.6:
            linhas_largura_inteira.append((linha[0]["top"], " ".join(p["text"] for p in linha)))
            ids_palavras_de_titulo.update(id(p) for p in linha)

    def _texto_da_coluna(palavras_coluna):
        linhas = _agrupar_em_linhas(palavras_coluna)
        return "\n".join(" ".join(p["text"] for p in linha) for linha in linhas)

    if not linhas_largura_inteira:
        return _texto_da_coluna(esquerda) + "\n" + _texto_da_coluna(direita)

    esquerda = [p for p in esquerda if id(p) not in ids_palavras_de_titulo]
    direita = [p for p in direita if id(p) not in ids_palavras_de_titulo]
    linhas_largura_inteira.sort(key=lambda par: par[0])

    partes = []
    topo_inicio = 0
    for topo_titulo, texto_titulo in linhas_largura_inteira:
        bloco_esq = [p for p in esquerda if topo_inicio <= p["top"] < topo_titulo]
        bloco_dir = [p for p in direita if topo_inicio <= p["top"] < topo_titulo]
        if bloco_esq or bloco_dir:
            partes.append(_texto_da_coluna(bloco_esq) + "\n" + _texto_da_coluna(bloco_dir))
        partes.append(texto_titulo)
        topo_inicio = topo_titulo
    bloco_esq = [p for p in esquerda if p["top"] >= topo_inicio]
    bloco_dir = [p for p in direita if p["top"] >= topo_inicio]
    if bloco_esq or bloco_dir:
        partes.append(_texto_da_coluna(bloco_esq) + "\n" + _texto_da_coluna(bloco_dir))
    return "\n".join(p for p in partes if p.strip())


def _baixar_texto_pdf(dia: date) -> Optional[str]:
    """Acha e baixa o PDF do domingo pedido, devolvendo o texto já
    extraído (pdfplumber, com detecção de duas colunas — ver
    _extrair_texto_pagina_pdf) — ou None se não achar o PDF ou a
    biblioteca/rede falhar. Isolado para ser baixado UMA VEZ só e
    reaproveitado por todas as extrações (introdução, aclamação,
    prefácio)."""
    if pdfplumber is None:
        return None
    url_pdf = _achar_url_pdf(dia)
    if not url_pdf:
        return None
    try:
        resp = requests.get(url_pdf, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            texto = "\n".join(_extrair_texto_pagina_pdf(p) for p in pdf.pages)
        return texto, url_pdf
    except Exception:
        return None


def obter_conteudo_boletim(dia: date) -> Optional[dict]:
    """Baixa o boletim do domingo pedido UMA VEZ e tenta extrair as 3
    seções (palavras de abertura, aclamação, prefácio) de forma
    independente — a falha de parsing de uma NÃO derruba as outras.
    Retorna None só se o PDF em si não puder ser baixado/encontrado
    (ex.: dia de semana, boletim do mês ainda não publicado). Campos
    não encontrados voltam como string vazia ("")."""
    resultado_download = _baixar_texto_pdf(dia)
    if not resultado_download:
        return None
    texto_pdf, url_pdf = resultado_download

    saida = {
        "url": url_pdf,
        "introducao": "",
        "aclamacao_refrao": "",
        "aclamacao_versiculo": "",
        "prefacio_nome": "",
        "prefacio_texto": "",
        "oferendas_texto": "",
        "comunhao_texto": "",
    }
    try:
        saida["introducao"] = _extrair_introducao(texto_pdf)
    except Exception:
        pass
    try:
        aclamacao = _extrair_aclamacao(texto_pdf)
        saida["aclamacao_refrao"] = aclamacao["refrao"]
        saida["aclamacao_versiculo"] = aclamacao["versiculo"]
    except Exception:
        pass
    try:
        prefacio = _extrair_prefacio(texto_pdf)
        saida["prefacio_nome"] = prefacio["nome"]
        saida["prefacio_texto"] = prefacio["texto"]
    except Exception:
        pass
    try:
        saida["oferendas_texto"] = _extrair_oferendas(texto_pdf)
    except Exception:
        pass
    try:
        saida["comunhao_texto"] = _extrair_comunhao(texto_pdf)
    except Exception:
        pass
    return saida


def obter_palavras_abertura(dia: date) -> Optional[dict]:
    """Retorna {'texto': str, 'url': str} com as palavras de abertura
    extraídas do Semanário Litúrgico da Diocese de SJC para o domingo
    pedido, ou None se: não for um domingo com boletim publicado, a
    fonte não responder, ou essa seção específica não puder ser
    isolada do texto — nunca levanta exceção para quem chamar; a
    Seção 02 simplesmente segue em branco nesse caso.

    Mantida como função própria (além de fazer parte de
    obter_conteudo_boletim) porque já é chamada assim em scraper.py."""
    boletim = obter_conteudo_boletim(dia)
    if not boletim or not boletim["introducao"]:
        return None
    return {"texto": boletim["introducao"], "url": boletim["url"]}


if __name__ == "__main__":
    from datetime import date as _date

    print(obter_conteudo_boletim(_date(2026, 9, 20)))
