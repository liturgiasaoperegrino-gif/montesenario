# -*- coding: utf-8 -*-
"""
palavras_abertura_sjc.py — Montesenario

Extrai as "palavras de abertura" (a breve introdução ao tema da missa
que aparece antes do Canto de Abertura) do boletim dominical
"Semanário Litúrgico" da Diocese de São José dos Campos, publicado
mensalmente em PDF na categoria "Nova Aliança" do site da diocese:
    https://diocese-sjc.org.br/categoria/nova-alianca/

Só cobre domingos — é um boletim dominical. Em dia de semana,
obter_palavras_abertura() retorna None e a Seção 02 do roteiro segue
em branco, para preenchimento manual (como já era antes).

Fluxo:
1. Página do mês (uma por mês, reúne os PDFs de todos os domingos):
       https://diocese-sjc.org.br/nova-alianca-{mes}-{ano}/
2. Nessa página, acha o link cujo texto visível começa com
   "{DD} de {mes}" (ex.: "20 de setembro - 25º Domingo do Tempo
   Comum") e pega a URL do .pdf correspondente.
3. Baixa o PDF e extrai o texto com pdfplumber.
4. A introdução fica entre a linha do título do dia (em CAIXA ALTA,
   ex. "25º DOMINGO DO TEMPO COMUM – MÊS DA BÍBLIA") e o cabeçalho
   "CANTO DE ABERTURA", que sempre vem logo em seguida no boletim.

Confirmado por inspeção manual em 20/09/2026: o PDF
".../20-de-setembro-de-2026-25o-Domingo-do-Tempo-Comum.pdf" começa com
"Semanário Litúrgico – Ano XXXII – Nº 53 – 20 de setembro de 2026 –
Diocese de São José dos Campos - SP", depois "25º DOMINGO DO TEMPO
COMUM – MÊS DA BÍBLIA", depois a introdução ("Na liturgia de hoje nos
encontraremos com a bondade de Deus...") e só então "CANTO DE
ABERTURA" (seção 1 da ordem da missa do boletim).

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

    soup = BeautifulSoup(resp.text, "html.parser")
    alvo = _sem_acento(f"{dia.day:02d} de {MESES[dia.month]}").lower()

    for link in soup.find_all("a", href=True):
        texto = _sem_acento(link.get_text(" ", strip=True)).lower()
        if texto.startswith(alvo) and link["href"].lower().endswith(".pdf"):
            href = link["href"]
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    return None


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
    introducao = re.sub(r"[ \t]+", " ", introducao)
    if not introducao:
        raise ValueError("introdução veio vazia")
    return introducao


def obter_palavras_abertura(dia: date) -> Optional[dict]:
    """Retorna {'texto': str, 'url': str} com as palavras de abertura
    extraídas do Semanário Litúrgico da Diocese de SJC para o domingo
    pedido, ou None se: não for um domingo com boletim publicado, a
    fonte não responder, ou o parsing falhar por qualquer motivo
    (formato do PDF mudou etc.) — nunca levanta exceção para quem
    chamar; a Seção 02 simplesmente segue em branco nesse caso."""
    if pdfplumber is None:
        return None
    try:
        url_pdf = _achar_url_pdf(dia)
        if not url_pdf:
            return None

        resp = requests.get(url_pdf, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            texto = "\n".join((p.extract_text() or "") for p in pdf.pages)

        introducao = _extrair_introducao(texto)
        return {"texto": introducao, "url": url_pdf}
    except Exception:
        return None


if __name__ == "__main__":
    from datetime import date as _date

    print(obter_palavras_abertura(_date(2026, 9, 20)))
