# -*- coding: utf-8 -*-
"""
scraper.py — Monte Senário

Busca e extrai os textos da liturgia diária (leituras + orações) para o
Google Sheets, com DUAS fontes:

  1. CNBB — fonte PRINCIPAL (leituras). Testada e funcionando com um
     exemplo real (18/09/2026). Descoberta por inspeção manual do
     DevTools (aba Network): a página `liturgiadiaria.edicoescnbb.com.br`
     é só a casca (Next.js); os dados de verdade vêm de uma API JSON
     separada, sem precisar de navegador/JavaScript:
         https://api-liturgia.edicoescnbb.com.br/contents/in/date/{AAAA-MM-DD}
     Essa API só cobre a Liturgia da Palavra (1ª/2ª leitura, salmo,
     aclamação, evangelho) — SEM Antífona de Entrada nem Coleta.

  2. Nova Aliança (novaalianca.com.br) — única fonte de Antífona de
     Entrada e Coleta, então é consultada SEMPRE (não é só um
     "fallback" no sentido antigo — ver extrair_liturgia_do_dia).
     Também serve de fallback das leituras se a CNBB falhar.

URL de cada dia na Nova Aliança segue o padrão:
    https://novaalianca.com.br/liturgia-de-{DD}-de-{MES}-de-{AAAA}/

Uso rápido:
    from scraper import extrair_liturgia_do_dia
    dados = extrair_liturgia_do_dia(date(2026, 9, 27))

Requisitos:
    pip install requests beautifulsoup4
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

from gcatholic_liturgia import obter_dia_liturgico
from palavras_abertura_sjc import obter_conteudo_boletim

BASE_URL_NOVAALIANCA = "https://novaalianca.com.br"
BASE_URL_CNBB_API = "https://api-liturgia.edicoescnbb.com.br/contents/in/date"
BASE_URL_POCKETTERCO = "https://pocketterco.com.br/liturgia"

MESES = {
    1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril", 5: "maio",
    6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
    11: "novembro", 12: "dezembro",
}
# obs: o site Nova Aliança usa "março" sem acento na URL na maioria dos
# casos (marco); se algum mês vier com acento na prática, ajuste aqui.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Rótulos que marcam o início de cada bloco no texto da página do Nova
# Aliança. A ordem importa: é usada para fatiar o texto bloco a bloco.
#
# IMPORTANTE: _texto_principal() usa soup.get_text("\n", strip=True), que
# quebra em uma linha NOVA a cada nó de texto do HTML — então "Aleluia,
# Aleluia, Aleluia." pode vir com cada palavra (ou cada "Aleluia,") em sua
# própria linha, dependendo de como a página do Nova Aliança marca esse
# trecho em tags separadas. O padrão antigo usava espaço LITERAL entre as
# palavras (não bate com quebra de linha) e era case-sensitive — se a
# marcação da página variasse (maiúscula, "!" em vez de ",", ou quebra de
# linha), o marcador "aclamacao" simplesmente não era encontrado, e a
# seção inteira da Aclamação (refrão + versículo) ficava GRUDADA no final
# da Segunda Leitura até o próximo marcador ("evangelho") — mesma classe
# de bug relatada pelo usuário em 21/09/2026 para a fonte CNBB, agora
# encontrada também aqui em 27/09/2026 ("seção 10 misturada com a
# antífona do evangelho"). Corrigido com (?i) e \s+ (que também casa
# quebra de linha) no lugar do espaço literal.
MARCADORES_NOVAALIANCA = [
    ("antifona_entrada", r"(?i)Ant[ií]fona de entrada"),
    ("gloria", r"(?i)^Gl[óo]ria$"),
    ("coleta", r"(?i)^Coleta$"),
    ("leitura1", r"(?i)Primeira\s+Leitura\s*[—-]\s*"),
    ("salmo", r"(?i)Salmo\s+Responsorial\s*[—-]\s*"),
    ("leitura2", r"(?i)Segunda\s+Leitura\s*[—-]\s*"),
    ("aclamacao", r"(?i)Aleluia[!,.]?\s*Aleluia[!,.]?\s*Aleluia"),
    ("evangelho", r"(?i)^Evangelho\s*[—-]\s*"),
    ("fim", r"(?i)PALAVRA DE VIDA|Compartilhe nas m[íi]dias"),
]

# Rótulos que marcam o início de cada bloco no texto do campo "body" da
# API da CNBB.
#
# Os marcadores usam (?i) (case-insensitive só NAQUELE padrão, via
# re.search) porque a CNBB às vezes publica o cabeçalho da Aclamação em
# CAIXA ALTA ("ACLAMAÇÃO AO EVANGELHO", igual "PRIMEIRA LEITURA"/
# "SEGUNDA LEITURA"), em vez do formato misto "Aclamação ao Evangelho".
# Sem o (?i), esse cabeçalho não batia com o padrão antigo, o corte da
# Seção 10 (Segunda Leitura) nunca encontrava o início da Aclamação, e
# o bloco inteiro da Aclamação (rubrica + refrão + versículo) ficava
# GRUDADO no final do texto da Segunda Leitura até o próximo marcador
# que batesse — bug real relatado pelo usuário em 21/09/2026 (comparar
# as duas últimas linhas da 2ª Leitura com a Aclamação).
#
# IMPORTANTE (2º bug, encontrado testando o primeiro): o marcador de
# "evangelho" precisa casar SÓ com o cabeçalho da própria seção
# Evangelho, âncorado no início da linha (^EVANGELHO\b) — não basta
# ser case-sensitive, porque quando a Aclamação vem em CAIXA ALTA
# ("ACLAMAÇÃO AO EVANGELHO"), a palavra "EVANGELHO" no FIM dessa linha
# já bate maiúscula com \bEVANGELHO\b sem âncora, fazendo o corte cair
# ali dentro e sumir com o bloco da Aclamação inteiro (e ainda grudar o
# começo do Evangelho real dentro dele). Âncorado em início de linha,
# só o cabeçalho de verdade (que ocupa a linha inteira sozinho) bate.
MARCADORES_CNBB = [
    ("leitura1", r"(?i)PRIMEIRA LEITURA"),
    ("leitura2", r"(?i)SEGUNDA LEITURA"),
    ("salmo", r"(?i)Salmo responsorial"),
    ("aclamacao", r"(?i)Aclama[çc][ãa]o ao Evangelho"),
    ("evangelho", r"^EVANGELHO\b"),
]


@dataclass
class LiturgiaDoDia:
    data: str  # AAAA-MM-DD
    titulo_dia: str
    url_fonte: str
    fonte_leituras: str = ""  # "CNBB" ou "Nova Aliança"
    fonte_propers: str = ""  # sempre "Nova Aliança" quando disponível — CNBB não tem antífona/coleta
    cor_liturgica: str = ""  # só a CNBB fornece isso (ex.: "verde", "roxo")
    antifona_entrada: str = ""
    coleta: str = ""
    leitura1_ref: str = ""
    leitura1_texto: str = ""
    salmo_ref: str = ""
    salmo_texto: str = ""
    salmo_refrao_auto: str = ""  # Seção 09 — Pocket Terço (refrão isolado do '℟.'; ver extrair_salmo_pocketterco)
    leitura2_ref: str = ""
    leitura2_texto: str = ""
    evangelho_ref: str = ""
    evangelho_texto: str = ""
    leituras_confirmadas: bool = True
    aviso_fonte: str = ""
    palavras_abertura: str = ""  # só domingo — ver palavras_abertura_sjc.py
    fonte_palavras_abertura: str = ""  # URL do boletim usado, se achou
    aclamacao_refrao: str = ""  # Seção 11 — Pocket Terço (principal) ou Diocese de SJC (fallback)
    aclamacao_versiculo: str = ""
    fonte_aclamacao: str = ""
    prefacio_nome_auto: str = ""  # Seção 16 — sugestão automática (Diocese de SJC, só domingo)
    prefacio_texto_auto: str = ""


def _cortar_vazamento_aclamacao(leitura2_texto: str, pistas: list) -> str:
    """Corta `leitura2_texto` a partir de onde qualquer uma das `pistas`
    (refrão e/ou versículo da Aclamação, já extraídos com sucesso de
    outra fonte) aparecer dentro dele — usado como defesa final contra
    o refrão/versículo da Aclamação ficando grudado ao final da 2ª
    Leitura, não importa a fonte nem o motivo exato do vazamento (ver
    comentário no ponto de chamada, em extrair_liturgia_do_dia).

    Cada pista é comparada só pelos primeiros ~40 caracteres, com \\s+
    no lugar dos espaços originais (tolerante a diferença de quebra de
    linha entre as duas extrações) e sem diferenciar maiúsculas."""
    posicoes = []
    for pista in pistas:
        pista = (pista or "").strip()
        if len(pista) < 8:
            continue
        palavras = pista[:40].split()
        if not palavras:
            continue
        padrao = r"\s+".join(re.escape(p) for p in palavras)
        m = re.search(padrao, leitura2_texto, flags=re.IGNORECASE)
        if m:
            posicoes.append(m.start())
    if not posicoes:
        return leitura2_texto
    return leitura2_texto[: min(posicoes)].strip()


def _fatiar_por_marcadores(texto: str, marcadores: list, case_sensitive_fim: bool = False) -> dict[str, str]:
    """Corta o texto corrido em blocos, usando `marcadores` (lista de
    (nome, padrao_regex)) como pontos de corte. Só passa re.MULTILINE —
    NÃO aplica IGNORECASE global (apesar do que uma versão antiga deste
    comentário dizia); cada padrão precisa trazer seu próprio (?i) quando
    a capitalização da fonte variar (ver MARCADORES_CNBB e
    MARCADORES_NOVAALIANCA para exemplos), e omitir o (?i) só quando o
    padrão precisar ser exato (ex.: \\bEVANGELHO\\b maiúsculo por si)."""
    posicoes = []
    for nome, padrao in marcadores:
        m = re.search(padrao, texto, flags=re.MULTILINE)
        if m:
            posicoes.append((m.start(), m.end(), nome))

    posicoes.sort(key=lambda t: t[0])

    blocos: dict[str, str] = {}
    for i, (ini, fim_marcador, nome) in enumerate(posicoes):
        fim_bloco = posicoes[i + 1][0] if i + 1 < len(posicoes) else len(texto)
        conteudo = texto[fim_marcador:fim_bloco].strip()
        blocos[nome] = conteudo
    return blocos


# ============================================================
# FONTE PRINCIPAL (leituras): CNBB — testada com exemplo real
# ============================================================

def montar_url_cnbb(dia: date) -> str:
    return f"{BASE_URL_CNBB_API}/{dia.isoformat()}"


def _refs_da_cnbb(html_leituras: str) -> list[str]:
    """O campo 'leituras' da API já vem com as referências bíblicas
    separadas por <div>, na ordem: 1ª leitura, salmo, 2ª leitura (vazio
    se não houver), evangelho. O primeiro <div> é só o rótulo
    'Leituras:' e é descartado."""
    soup = BeautifulSoup(html_leituras, "html.parser")
    divs = soup.find_all("div")
    return [d.get_text(strip=True) for d in divs[1:]]


def extrair_liturgia_cnbb(dia: date) -> Optional[LiturgiaDoDia]:
    """Busca a Liturgia da Palavra do dia na API da CNBB. Retorna None
    em qualquer falha (404, rede, JSON inesperado), para que o chamador
    trate como "esta fonte não respondeu" e recorra ao Nova Aliança."""
    url = montar_url_cnbb(dia)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        dados = resp.json().get("content")
        if not dados:
            return None

        soup_details = BeautifulSoup(dados.get("details", ""), "html.parser")
        titulo_div = soup_details.find("div", style=re.compile(r"font-size:\s*26px"))
        titulo_dia = (
            titulo_div.get_text(" ", strip=True) if titulo_div
            else dados.get("title", "")
        )
        # O campo genérico "title" da API da CNBB é o nome da série de
        # conteúdo ("Liturgia Diária"), não o dia litúrgico específico —
        # nunca deve aparecer no roteiro. Tratado como "sem título" para
        # cair no Nova Aliança (fonte alternativa) ou, o mais comum, ser
        # sobrescrito pelo gcatholic.org logo abaixo em
        # extrair_liturgia_do_dia.
        if titulo_dia.strip().lower() == "liturgia diária":
            titulo_dia = ""

        refs = _refs_da_cnbb(dados.get("leituras", ""))
        leitura1_ref = refs[0] if len(refs) > 0 else ""
        salmo_ref = refs[1] if len(refs) > 1 else ""
        leitura2_ref = refs[2] if len(refs) > 2 else ""
        evangelho_ref = refs[3] if len(refs) > 3 else ""

        texto_body_soup = BeautifulSoup(dados.get("body", ""), "html.parser")
        # A CNBB embute divs ocultas (style="display: none") com metadados
        # internos (ex.: <div style="display: none;"><h3 class="title-leitura">
        # 2ª Leitura - Fl 1,20c</h3></div>) que o BeautifulSoup não sabe que
        # estão escondidas — sem remover isso, o texto vaza pro final do
        # bloco anterior (bug real encontrado testando 20/09/2026: contaminava
        # o fim do salmo_texto). Removidas antes de extrair o texto corrido.
        for oculto in texto_body_soup.find_all(style=re.compile(r"display:\s*none")):
            oculto.decompose()
        texto_body = texto_body_soup.get_text("\n", strip=True)
        blocos = _fatiar_por_marcadores(texto_body, MARCADORES_CNBB)

        if not blocos.get("evangelho") and not blocos.get("leitura1"):
            # Nada reconhecível veio — a estrutura pode ter mudado.
            return None

        return LiturgiaDoDia(
            data=dia.isoformat(),
            titulo_dia=titulo_dia,
            url_fonte=url,
            fonte_leituras="CNBB",
            cor_liturgica=dados.get("color", ""),
            leitura1_ref=leitura1_ref,
            leitura1_texto=blocos.get("leitura1", ""),
            salmo_ref=salmo_ref,
            salmo_texto=blocos.get("salmo", ""),
            leitura2_ref=leitura2_ref,
            leitura2_texto=blocos.get("leitura2", ""),
            evangelho_ref=evangelho_ref,
            evangelho_texto=blocos.get("evangelho", ""),
        )
    except Exception:
        return None


# ============================================================
# FONTE de Oferendas/Comunhão: Pocket Terço — testada com exemplo real
# ============================================================
#
# https://pocketterco.com.br/liturgia/{DD}/{MM}/{AAAA} é uma página
# server-rendered (sem JS) que traz o Ordinário completo do dia,
# incluindo Sobre as Oferendas e Depois da Comunhão — as duas orações
# que nem a CNBB nem o Nova Aliança publicam. Usada só para essas duas,
# por decisão do usuário (o resto do pipeline continua como estava).

def montar_url_pocketterco(dia: date) -> str:
    return f"{BASE_URL_POCKETTERCO}/{dia.day:02d}/{dia.month:02d}/{dia.year}"


def _extrair_secao_pocketterco(texto: str, inicio: str, fins: list[str]) -> str:
    # IGNORECASE por segurança — a capitalização exata do cabeçalho na
    # página pode variar ("Sobre as Oferendas" vs. "Sobre as oferendas").
    # Ancorado só no INÍCIO da linha (sem exigir que a linha termine
    # exatamente ali) — um "$" estrito demais deixava de bater sempre
    # que o cabeçalho viesse com algum caractere a mais colado (":",
    # espaço não-usual etc.), fazendo a seção inteira sumir sem motivo
    # aparente (bug relatado pelo usuário em 21/09/2026 para a Seção 18).
    m_ini = re.search(
        r"^" + re.escape(inicio), texto, flags=re.MULTILINE | re.IGNORECASE
    )
    if not m_ini:
        return ""
    resto = texto[m_ini.end():]
    fim = len(resto)
    for f in fins:
        m_fim = re.search(r"^" + re.escape(f), resto, flags=re.MULTILINE | re.IGNORECASE)
        if m_fim:
            fim = min(fim, m_fim.start())
    # Tira também um eventual ":" (ou "—"/"-") colado logo após o
    # cabeçalho, que o "^" sem "$" estrito (ver acima) deixa de fora do
    # próprio cabeçalho — não faz parte do texto da oração.
    return re.sub(r"^\s*[:—-]\s*", "", resto[:fim]).strip()


def extrair_oferendas_comunhao_pocketterco(dia: date) -> Optional[dict]:
    """Retorna {'oferendas': str, 'comunhao': str, 'url': str} ou None se
    a fonte não responder ou não trouxer as seções esperadas."""
    url = montar_url_pocketterco(dia)
    try:
        html = _baixar_html(url)
        if html is None:
            return None
        texto = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

        oferendas = _extrair_secao_pocketterco(
            texto, "Sobre as Oferendas",
            ["Orações Eucarísticas", "Antífona da Comunhão"],
        )
        comunhao = _extrair_secao_pocketterco(
            texto, "Depois da Comunhão",
            ["Homilia do dia", "Santo do dia"],
        )
        if not oferendas and not comunhao:
            return None
        return {"oferendas": oferendas, "comunhao": comunhao, "url": url}
    except Exception:
        return None


_PADRAO_ACLAMACAO = re.compile(r"℟\.?\s*(.+?)\s*℣\.?\s*(.+)", re.DOTALL)
_PADRAO_ACLAMACAO_SEM_SIMBOLO = re.compile(
    r"(Aleluia,?\s*Aleluia,?\s*Aleluia\.?)\s*(.*)", re.IGNORECASE | re.DOTALL
)


def extrair_aclamacao_pocketterco(dia: date) -> Optional[dict]:
    """Retorna {'refrao': str, 'versiculo': str, 'url': str} com a
    Aclamação ao Evangelho (Seção 11) do dia, ou None se a fonte não
    responder ou não trouxer essa seção.

    IMPORTANTE (bug real corrigido em 20/09/2026, achado por inspeção
    estrutural do HTML): a página NÃO tem nenhum cabeçalho "Aclamação ao
    Evangelho" — o texto salta direto da Segunda (ou Primeira) Leitura
    para o refrão/versículo soltos, marcados só pelos símbolos ℟./℣.,
    antes do "Evangelho —".

    SEGUNDO BUG REAL corrigido em 21/09/2026, relatado pelo usuário: a
    primeira versão desta função procurava o ℣ a partir do INÍCIO da
    página inteira. Só que a página traz o Ordinário da Missa completo,
    não só a Liturgia da Palavra — e a saudação "℣. O Senhor esteja
    convosco. / ℟. ..." também aparece MAIS DE UMA VEZ na página (na
    abertura da Missa, de novo antes do Evangelho etc.), quase sempre
    ANTES da própria Primeira Leitura. Buscar "o primeiro ℣ da página"
    pegava essa saudação de abertura, não o versículo da aclamação — e
    o texto extraído virava um bloco enorme (arrastando as leituras
    inteiras no meio), que aparecia deslocado no roteiro logo depois do
    "Graças a Deus" da 2ª Leitura.

    Correção: (1) a janela de busca começa DEPOIS da última leitura
    antes do Evangelho (Segunda Leitura, ou Primeira Leitura se não
    houver Segunda) — nunca do topo da página; (2) a âncora principal
    passa a ser o texto literal "Aleluia, Aleluia, Aleluia" (pedido
    explícito do usuário), muito mais específico que os símbolos ℟/℣
    sozinhos, que se repetem em várias saudações do Ordinário. O trecho
    devolvido vai exatamente do "Aleluia" até (sem incluir) o
    "Evangelho —", como pedido."""
    url = montar_url_pocketterco(dia)
    try:
        html = _baixar_html(url)
        if html is None:
            return None
        texto = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

        m_evangelho = re.search(r"^Evangelho\s*[—-]", texto, flags=re.MULTILINE | re.IGNORECASE)
        fim = m_evangelho.start() if m_evangelho else len(texto)

        m_leitura2 = re.search(r"^Segunda\s+Leitura\s*[—-]", texto, flags=re.MULTILINE | re.IGNORECASE)
        m_leitura1 = re.search(r"^Primeira\s+Leitura\s*[—-]", texto, flags=re.MULTILINE | re.IGNORECASE)
        m_ref_anterior = m_leitura2 or m_leitura1
        inicio_janela = m_ref_anterior.end() if m_ref_anterior else 0

        janela = texto[inicio_janela:fim]

        m_aleluia = re.search(r"Aleluia,?\s*Aleluia,?\s*Aleluia\.?", janela, flags=re.IGNORECASE)
        if not m_aleluia:
            # Fallback (raro — ex.: aclamação própria da Quaresma, sem
            # "Aleluia"): tenta ainda assim pelos símbolos, dentro da
            # MESMA janela já restrita (pós-leitura, pré-Evangelho).
            m_versiculo = re.search(r"℣\.?", janela)
            if not m_versiculo:
                return None
            pos_refrao_ini = janela.rfind("℟", 0, m_versiculo.start())
            if pos_refrao_ini == -1:
                return None
            refrao = re.sub(r"^℟\.?\s*", "", janela[pos_refrao_ini:m_versiculo.start()]).strip()
            versiculo = janela[m_versiculo.end():].strip()
            versiculo = re.sub(r"\s*℟\.?\s*$", "", versiculo).strip()
            if not refrao:
                return None
            return {"refrao": refrao, "versiculo": versiculo, "url": url}

        pos_refrao_ini = janela.rfind("℟", 0, m_aleluia.start())
        inicio_refrao = pos_refrao_ini if pos_refrao_ini != -1 else m_aleluia.start()
        refrao = re.sub(r"^℟\.?\s*", "", janela[inicio_refrao:m_aleluia.end()]).strip()

        resto = janela[m_aleluia.end():]
        m_versiculo = re.search(r"℣\.?\s*", resto)
        versiculo = resto[m_versiculo.end():].strip() if m_versiculo else resto.strip()
        # Remove eventual "℟." residual no fim (repetição do refrão,
        # confirmada na página — ex.: "...℣. <verso> ℟.").
        versiculo = re.sub(r"\s*℟\.?\s*$", "", versiculo).strip()

        if not refrao:
            return None
        return {"refrao": refrao, "versiculo": versiculo, "url": url}
    except Exception:
        return None


# ============================================================
# FONTE alternativa da Segunda Leitura (Seção 10): Pocket Terço
# ============================================================
#
# Pedido do usuário em 21/09/2026 (3ª rodada de bugs do dia): mesmo
# depois de tornar os marcadores de CNBB e Nova Aliança tolerantes a
# variação de maiúscula e quebra de linha, o versículo da Aclamação ao
# Evangelho ainda apareceu colado ao final da 2ª Leitura em pelo menos
# um dia real, ANTES do "Palavra do Senhor." — um jeito de vazar que
# não bate com nenhum dos dois bugs já corrigidos nessas duas fontes, e
# que não dá pra confirmar sem a página publicada daquele dia (rede
# bloqueada neste ambiente). Em vez de caçar mais um caso, a 2ª Leitura
# passa a usar o Pocket Terço como fonte alternativa (substitui
# CNBB/Nova Aliança quando responder) — a mesma página, com a mesma
# técnica de janela entre marcadores, já usada com sucesso para isolar
# a Aclamação (Seção 11).

def extrair_leitura2_pocketterco(dia: date) -> Optional[dict]:
    """Retorna {'ref': str, 'texto': str, 'url': str} com a Segunda
    Leitura (Seção 10) do dia, ou None se a fonte não responder ou não
    tiver Segunda Leitura nesse dia (nem todo dia tem)."""
    url = montar_url_pocketterco(dia)
    try:
        html = _baixar_html(url)
        if html is None:
            return None
        texto = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

        m_ini = re.search(
            r"^Segunda\s+Leitura\s*[—-]\s*([^\n]*)", texto, flags=re.MULTILINE | re.IGNORECASE
        )
        if not m_ini:
            return None
        ref = m_ini.group(1).strip()
        resto = texto[m_ini.end():]

        # Fim do bloco: o que vier primeiro entre o refrão da Aclamação
        # ("Aleluia..."), o símbolo "℣." solto (aclamação própria, sem
        # "Aleluia" — ex.: Quaresma) ou o cabeçalho do Evangelho — igual
        # à janela já usada em extrair_aclamacao_pocketterco, só que
        # aqui é o LIMITE, não o início.
        candidatos_fim = []
        m_aleluia = re.search(r"Aleluia,?\s*Aleluia,?\s*Aleluia\.?", resto, flags=re.IGNORECASE)
        if m_aleluia:
            candidatos_fim.append(m_aleluia.start())
        m_refrao_simbolo = re.search(r"℟\.?", resto)
        if m_refrao_simbolo:
            candidatos_fim.append(m_refrao_simbolo.start())
        m_versiculo_simbolo = re.search(r"℣\.?", resto)
        if m_versiculo_simbolo:
            candidatos_fim.append(m_versiculo_simbolo.start())
        m_evangelho = re.search(r"^Evangelho\s*[—-]", resto, flags=re.MULTILINE | re.IGNORECASE)
        if m_evangelho:
            candidatos_fim.append(m_evangelho.start())

        fim = min(candidatos_fim) if candidatos_fim else len(resto)
        conteudo = resto[:fim].strip()
        if not conteudo:
            return None
        return {"ref": ref, "texto": conteudo, "url": url}
    except Exception:
        return None


# ============================================================
# FONTE do Salmo Responsorial (Seção 09): Pocket Terço
# ============================================================
#
# Pedido explícito do usuário: localizar o cabeçalho "Salmo
# Responsorial" na página, depois o símbolo '℟.' — o texto que vem
# depois dele é o refrão — e cada linha iniciada por '-' é uma
# estrofe. O refrão não é repetido no meio das estrofes na saída (só
# uma vez, em destaque, no início — ver roteiro_completo.py Seção 09),
# mesmo que a fonte o repita entre elas.

_PADRAO_SALMO_HEADING = re.compile(r"^Salmo\s+Responsorial\b.*$", re.MULTILINE | re.IGNORECASE)
_PADRAO_PROXIMA_SECAO_APOS_SALMO = re.compile(
    r"^(Segunda\s+Leitura|Evangelho)\s*[—-]", re.MULTILINE | re.IGNORECASE
)


def extrair_salmo_pocketterco(dia: date) -> Optional[dict]:
    """Retorna {'refrao': str, 'estrofes': list[str], 'url': str} com o
    Salmo Responsorial (Seção 09) do dia, ou None se a fonte não
    responder ou não trouxer essa seção."""
    url = montar_url_pocketterco(dia)
    try:
        html = _baixar_html(url)
        if html is None:
            return None
        texto = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

        m_inicio = _PADRAO_SALMO_HEADING.search(texto)
        if not m_inicio:
            return None
        resto = texto[m_inicio.end():]

        m_fim = _PADRAO_PROXIMA_SECAO_APOS_SALMO.search(resto)
        janela = resto[: m_fim.start()] if m_fim else resto

        m_refrao = re.search(r"℟\.?\s*(.+)", janela)
        if not m_refrao:
            return None
        refrao = m_refrao.group(1).strip()
        if not refrao:
            return None

        estrofes = [
            e.strip() for e in re.findall(r"^-\s*(.+)$", janela, flags=re.MULTILINE)
            if e.strip()
        ]

        return {"refrao": refrao, "estrofes": estrofes, "url": url}
    except Exception:
        return None


# ============================================================
# FONTE ALTERNATIVA: Nova Aliança (requests — testada e funcionando)
# ============================================================

def montar_url_novaalianca(dia: date) -> str:
    mes_nome = MESES[dia.month]
    return f"{BASE_URL_NOVAALIANCA}/liturgia-de-{dia.day:02d}-de-{mes_nome}-de-{dia.year}/"


def _baixar_html(url: str) -> Optional[str]:
    """Baixa o HTML da página. Retorna None tanto para 404 (página não
    existe/ainda não publicada) quanto para qualquer outro erro de rede
    ou HTTP (403, 500, timeout, DNS, conexão recusada etc.) — nenhum
    desses deve derrubar o pipeline inteiro; o chamador trata None como
    "esta fonte não respondeu" e segue para o fallback."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException:
        return None


def _texto_principal(html: str) -> tuple[str, str]:
    """Retorna (titulo_do_dia, texto_corrido_do_conteudo_principal)."""
    soup = BeautifulSoup(html, "html.parser")

    # O conteúdo principal do post costuma ficar no <article> ou na div
    # de conteúdo do Elementor. Tentamos algumas estratégias, da mais
    # específica para a mais genérica.
    container = (
        soup.find("article")
        or soup.find("div", class_=re.compile("elementor-widget-theme-post-content"))
        or soup.find("main")
        or soup.body
    )

    titulo_tag = soup.find(["h1", "h2"])
    titulo_dia = titulo_tag.get_text(strip=True) if titulo_tag else ""

    texto = container.get_text("\n", strip=True) if container else ""
    return titulo_dia, texto


def _extrair_referencia(bloco_com_titulo: str, padrao_titulo: str) -> tuple[str, str]:
    """Separa 'Ez 18, 25-28' (referência) do resto do texto, quando o
    marcador de corte incluiu a referência no próprio cabeçalho."""
    m = re.search(padrao_titulo + r"([^\n]+)", bloco_com_titulo)
    return (m.group(1).strip() if m else ""), bloco_com_titulo


def extrair_liturgia_novaalianca(dia: date) -> Optional[LiturgiaDoDia]:
    """Baixa e faz o parse da liturgia de uma data específica no site do
    Nova Aliança. Retorna None se a página não existir, se a fonte não
    responder (rede, HTTP, timeout) ou se o parsing falhar por qualquer
    motivo — nada aqui deve derrubar o pipeline; o chamador trata None
    como "esta fonte não respondeu" e marca a data como pendente."""
    url = montar_url_novaalianca(dia)
    try:
        html = _baixar_html(url)
        if html is None:
            return None

        titulo_dia, texto = _texto_principal(html)
        blocos = _fatiar_por_marcadores(texto, MARCADORES_NOVAALIANCA)

        # Referências vêm coladas no próprio marcador (ex.: "Primeira Leitura — Ez 18, 25-28")
        ref1 = re.search(r"Primeira\s+Leitura\s*[—-]\s*([^\n]+)", texto)
        ref_salmo = re.search(r"Salmo\s+Responsorial\s*[—-]\s*([^\n]+)", texto)
        ref2 = re.search(r"Segunda\s+Leitura\s*[—-]\s*([^\n]+)", texto)
        ref_ev = re.search(r"Evangelho\s*[—-]\s*([^\n]+)", texto)

        return LiturgiaDoDia(
            data=dia.isoformat(),
            titulo_dia=titulo_dia,
            url_fonte=url,
            fonte_leituras="Nova Aliança",
            fonte_propers="Nova Aliança",
            antifona_entrada=blocos.get("antifona_entrada", ""),
            coleta=blocos.get("coleta", ""),
            leitura1_ref=ref1.group(1).strip() if ref1 else "",
            leitura1_texto=blocos.get("leitura1", ""),
            salmo_ref=ref_salmo.group(1).strip() if ref_salmo else "",
            salmo_texto=blocos.get("salmo", ""),
            leitura2_ref=ref2.group(1).strip() if ref2 else "",
            leitura2_texto=blocos.get("leitura2", ""),
            evangelho_ref=ref_ev.group(1).strip() if ref_ev else "",
            evangelho_texto=blocos.get("evangelho", ""),
        )
    except Exception:
        return None


# ============================================================
# Orquestrador: combina as duas fontes
# ============================================================
#
# A CNBB só cobre a Liturgia da Palavra (leituras/salmo/evangelho) —
# confirmado por inspeção manual em 18/09/2026, a página não tem
# Antífona de Entrada nem Coleta. Por isso o Nova Aliança continua
# sendo consultado SEMPRE, mesmo quando a CNBB responde: é a única
# fonte das duas orações presidenciais que o scraper cobre.

def extrair_liturgia_do_dia(dia: date) -> LiturgiaDoDia:
    """Busca a Liturgia da Palavra na CNBB (principal) — ou no Nova
    Aliança, se a CNBB falhar — e SEMPRE busca Antífona/Coleta no Nova
    Aliança (única fonte que as tem). Combina os dois resultados numa
    linha só.

    Se nenhuma fonte responder, NÃO retorna None: devolve um registro
    com leituras_confirmadas=False e um aviso explicando o motivo, para
    que esse estado siga visível em toda a cadeia (planilha, app, PDF)
    em vez de o dia simplesmente sumir. Se a CNBB responder mas o Nova
    Aliança não (comum: CNBB parece não depender de "publicação" por
    dia, enquanto o Nova Aliança sim), as leituras ficam confirmadas
    mesmo assim — só a Antífona/Coleta ficam pendentes, registrado em
    aviso_fonte sem bloquear o resto.

    TÍTULO DO DIA e COR LITÚRGICA: a CNBB às vezes fica indisponível
    ("barreira CNBB") e o Nova Aliança nem sempre traz o título no
    formato padronizado nem a cor. Por isso, depois de montar `base`
    com as leituras, o gcatholic.org (gcatholic_liturgia.py) é SEMPRE
    consultado e, quando responde, tem prioridade sobre CNBB/Nova
    Aliança para titulo_dia e cor_liturgica — é a fonte mais confiável
    e no formato exato pedido (ex.: "25º Domingo do Tempo Comum").

    PALAVRAS DE ABERTURA: só existem para domingo, extraídas do
    Semanário Litúrgico da Diocese de SJC (palavras_abertura_sjc.py).
    Em dia de semana, ou se a fonte não tiver publicado ainda, fica
    vazio — a Seção 02 do roteiro continua em branco pra preencher à
    mão nesse caso, como já era."""
    cnbb = extrair_liturgia_cnbb(dia)
    novaalianca = extrair_liturgia_novaalianca(dia)  # sempre tentado: única fonte de antífona/coleta

    if cnbb is None and novaalianca is None:
        url_novaalianca = montar_url_novaalianca(dia)
        return LiturgiaDoDia(
            data=dia.isoformat(),
            titulo_dia="(fonte ainda não publicada)",
            url_fonte=url_novaalianca,
            leituras_confirmadas=False,
            aviso_fonte=(
                f"Nem a CNBB (fonte principal das leituras) nem o Nova "
                f"Aliança ({url_novaalianca}, única fonte de Antífona/"
                f"Coleta) têm esta data disponível ainda. Provável "
                f"causa: data muito no futuro. Sincronize novamente "
                f"mais perto da data, ou preencha manualmente com a "
                f"atribuição fixa do Lecionário se for domingo ou "
                f"solenidade."
            ),
        )

    base = cnbb if cnbb is not None else novaalianca

    if novaalianca is not None:
        base.antifona_entrada = novaalianca.antifona_entrada
        base.coleta = novaalianca.coleta
        base.fonte_propers = "Nova Aliança"
        if base.titulo_dia in ("", None) or (cnbb is not None and not cnbb.titulo_dia):
            base.titulo_dia = novaalianca.titulo_dia
    else:
        base.fonte_propers = ""
        base.aviso_fonte = (
            "Leituras confirmadas, mas Antífona de Entrada e Coleta "
            "ainda não disponíveis: o Nova Aliança (única fonte dessas "
            "duas orações) não publicou esta data ainda."
        )

    dia_gcatholic = obter_dia_liturgico(dia)
    if dia_gcatholic:
        base.titulo_dia = dia_gcatholic["titulo"]
        base.cor_liturgica = dia_gcatholic["cor"]

    # Segunda Leitura (Seção 10): CNBB/Nova Aliança continuam sendo a
    # fonte principal, mas o Pocket Terço SUBSTITUI o texto quando
    # responder (ver comentário de extrair_leitura2_pocketterco acima —
    # bug real de 21/09/2026 em que o versículo da Aclamação vinha
    # colado ao final da 2ª Leitura antes mesmo do "Palavra do
    # Senhor.").
    leitura2_pt = extrair_leitura2_pocketterco(dia)
    if leitura2_pt and leitura2_pt["texto"]:
        base.leitura2_texto = leitura2_pt["texto"]
        if leitura2_pt["ref"]:
            base.leitura2_ref = leitura2_pt["ref"]

    # Aclamação ao Evangelho (Seção 11): Pocket Terço é a fonte
    # principal (testada e funcionando — ver
    # extrair_aclamacao_pocketterco). A Diocese de SJC (boletim
    # dominical) entra só como fallback, e só cobre domingo.
    aclamacao = extrair_aclamacao_pocketterco(dia)
    if aclamacao:
        base.aclamacao_refrao = aclamacao["refrao"]
        base.aclamacao_versiculo = aclamacao["versiculo"]
        base.fonte_aclamacao = f"Pocket Terço ({aclamacao['url']})"

    # Defesa final (Seção 10 x Seção 11): não importa qual fonte gerou
    # leitura2_texto (CNBB, Nova Aliança ou o próprio Pocket Terço
    # acima) nem o motivo exato do vazamento — bug real de 21/09/2026
    # em que o refrão/versículo da Aclamação continuaram grudados ao
    # final da 2ª Leitura mesmo depois de duas rodadas de correção nos
    # marcadores. Como o refrão e o versículo da Aclamação já foram
    # isolados com sucesso alguns passos acima (Pocket Terço, testado),
    # usa-se esse resultado como verdade e corta-se do leitura2_texto
    # qualquer coisa a partir de onde ele aparecer — não depende de
    # entender POR QUE a fonte da 2ª Leitura grudou o texto.
    if base.leitura2_texto and (base.aclamacao_refrao or base.aclamacao_versiculo):
        base.leitura2_texto = _cortar_vazamento_aclamacao(
            base.leitura2_texto, [base.aclamacao_refrao, base.aclamacao_versiculo]
        )

    # Salmo Responsorial (Seção 09): Pocket Terço é a ÚNICA fonte do
    # refrão isolado (nem CNBB nem Nova Aliança separam refrão de
    # estrofe) — pedido explícito do usuário. Quando encontrado,
    # SUBSTITUI o salmo_texto (CNBB/Nova Aliança) pelo formato
    # "refrão + estrofes com '-'" já esperado por roteiro_completo.py;
    # se não encontrado, mantém o que já veio de CNBB/Nova Aliança
    # (texto corrido, sem refrão isolado — como já era).
    salmo = extrair_salmo_pocketterco(dia)
    if salmo:
        base.salmo_refrao_auto = salmo["refrao"]
        if salmo["estrofes"]:
            base.salmo_texto = "\n\n".join(f"- {e}" for e in salmo["estrofes"])

    # Boletim da Diocese de SJC: baixado UMA VEZ, e usado para 3 coisas
    # — palavras de abertura (Seção 02, única fonte), fallback da
    # Aclamação (Seção 11, se o Pocket Terço não respondeu) e sugestão
    # automática de Prefácio (Seção 16, única fonte automática — a
    # seleção manual pela pasta do Drive continua disponível e tem
    # prioridade se o operador escolher outra). Só cobre domingo.
    boletim = obter_conteudo_boletim(dia)
    if boletim:
        if boletim["introducao"]:
            base.palavras_abertura = boletim["introducao"]
            base.fonte_palavras_abertura = boletim["url"]
        if not base.aclamacao_refrao and boletim["aclamacao_refrao"]:
            base.aclamacao_refrao = boletim["aclamacao_refrao"]
            base.aclamacao_versiculo = boletim["aclamacao_versiculo"]
            base.fonte_aclamacao = f"Diocese de SJC ({boletim['url']})"
        if boletim["prefacio_nome"]:
            base.prefacio_nome_auto = boletim["prefacio_nome"]
            base.prefacio_texto_auto = boletim["prefacio_texto"]

    return base


def extrair_intervalo(data_inicio: date, data_fim: date, pausa_seg: float = 1.0):
    """Gera LiturgiaDoDia para cada dia do intervalo [data_inicio, data_fim] —
    inclusive os dias sem página ainda (leituras_confirmadas=False), para
    que a lacuna fique registrada em vez de simplesmente desaparecer."""
    dia = data_inicio
    while dia <= data_fim:
        item = extrair_liturgia_do_dia(dia)
        yield item
        time.sleep(pausa_seg)
        dia += timedelta(days=1)


if __name__ == "__main__":
    # Teste rápido: extrai o dia de hoje e imprime em formato legível
    hoje = date.today()
    resultado = extrair_liturgia_do_dia(hoje)
    if resultado.leituras_confirmadas:
        print(f"[leituras: {resultado.fonte_leituras} | antífona/coleta: {resultado.fonte_propers or 'pendente'}]")
        for campo, valor in asdict(resultado).items():
            print(f"--- {campo} ---")
            print(str(valor)[:300], "\n")
    else:
        print(resultado.aviso_fonte)
