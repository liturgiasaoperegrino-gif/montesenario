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
MARCADORES_NOVAALIANCA = [
    ("antifona_entrada", r"Ant[ií]fona de entrada"),
    ("gloria", r"^Gl[óo]ria$"),
    ("coleta", r"^Coleta$"),
    ("leitura1", r"Primeira Leitura\s*[—-]\s*"),
    ("salmo", r"Salmo Responsorial\s*[—-]\s*"),
    ("leitura2", r"Segunda Leitura\s*[—-]\s*"),
    ("aclamacao", r"Aleluia,? Aleluia,? Aleluia"),
    ("evangelho", r"^Evangelho\s*[—-]\s*"),
    ("fim", r"PALAVRA DE VIDA|Compartilhe nas m[íi]dias"),
]

# Rótulos que marcam o início de cada bloco no texto do campo "body" da
# API da CNBB. IMPORTANTE: o marcador de "evangelho" precisa ser
# case-sensitive (só o cabeçalho "EVANGELHO" em maiúsculas) — do
# contrário ele bate sem querer dentro de "Aclamação ao Evangelho" e
# some com esse bloco (bug real encontrado e corrigido durante os testes).
MARCADORES_CNBB = [
    ("leitura1", r"PRIMEIRA LEITURA"),
    ("leitura2", r"SEGUNDA LEITURA"),
    ("salmo", r"Salmo responsorial"),
    ("aclamacao", r"Aclama[çc][ãa]o ao Evangelho"),
    ("evangelho", r"\bEVANGELHO\b"),
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
    leitura2_ref: str = ""
    leitura2_texto: str = ""
    evangelho_ref: str = ""
    evangelho_texto: str = ""
    leituras_confirmadas: bool = True
    aviso_fonte: str = ""


def _fatiar_por_marcadores(texto: str, marcadores: list, case_sensitive_fim: bool = False) -> dict[str, str]:
    """Corta o texto corrido em blocos, usando `marcadores` (lista de
    (nome, padrao_regex)) como pontos de corte. IGNORECASE se aplica a
    todos os padrões — se algum precisar ser exato (ver aviso acima do
    MARCADORES_CNBB), escreva o próprio padrão para não depender de
    minúsculas/maiúsculas (ex.: \\bEVANGELHO\\b já é maiúsculo por si)."""
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
    m_ini = re.search(r"^" + re.escape(inicio) + r"\s*$", texto, flags=re.MULTILINE)
    if not m_ini:
        return ""
    resto = texto[m_ini.end():]
    fim = len(resto)
    for f in fins:
        m_fim = re.search(r"^" + re.escape(f), resto, flags=re.MULTILINE)
        if m_fim:
            fim = min(fim, m_fim.start())
    return resto[:fim].strip()


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
        ref1 = re.search(r"Primeira Leitura\s*[—-]\s*([^\n]+)", texto)
        ref_salmo = re.search(r"Salmo Responsorial\s*[—-]\s*([^\n]+)", texto)
        ref2 = re.search(r"Segunda Leitura\s*[—-]\s*([^\n]+)", texto)
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
    aviso_fonte sem bloquear o resto."""
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
