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

    soup = BeautifulSoup(resp.text, "html.parser")
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
    não tiver o padrão 'Aleluia, Aleluia, Aleluia. <versículo>'."""
    bloco = _isolar_secao(texto_pdf, r"ACLAMA[ÇC][ÃA]O\s+AO\s+EVANGELHO")
    if not bloco:
        raise ValueError("seção 'ACLAMAÇÃO AO EVANGELHO' não encontrada")
    m = _PADRAO_ACLAMACAO_SEM_SIMBOLO.search(bloco)
    if not m or not m.group(1).strip():
        raise ValueError("padrão 'Aleluia...' não encontrado no bloco")
    return {"refrao": m.group(1).strip(), "versiculo": m.group(2).strip()}


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

    return {"nome": m_nome.group(1).strip(), "texto": texto_prefacio}


def _baixar_texto_pdf(dia: date) -> Optional[str]:
    """Acha e baixa o PDF do domingo pedido, devolvendo o texto já
    extraído (pdfplumber) — ou None se não achar o PDF ou a
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
            texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
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
