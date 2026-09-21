# -*- coding: utf-8 -*-
"""
gcatholic_liturgia.py — Montesenario

Fonte para DATA + COR LITÚRGICA + TEMPO LITÚRGICO + TÍTULO DO DIA,
usada para contornar a "barreira" da API da CNBB (instável/bloqueada em
alguns momentos — ver scraper.py). Usa o feed iCalendar (.ics) público
do gcatholic.org, que publica o calendário litúrgico completo do
Brasil por ano, em português — muito mais fácil e confiável de
interpretar do que a página HTML do calendário (que não expõe a cor em
texto simples, só via emoji dentro do próprio .ics).

Formato de cada evento no .ics (um evento por dia):
    SUMMARY:<emoji de cor> [rank] Título do dia
Ex.: "🟢 Domingo XXV do Tempo Comum" ou
     "⚪ [F] São Mateus, apóstolo e evangelista"

O emoji no início do SUMMARY indica a cor litúrgica do dia:
    ⚪ branco   🟢 verde   🟣 roxo   🔴 vermelho   🌸 rosa   🟡/🟠 dourado
[rank] é opcional: S=Solenidade, F=Festa, M=Memória obrigatória,
m=Memória facultativa.

URL do feed (um arquivo por ano, todos os dias):
    https://gcatholic.org/calendar/ics/{ANO}-pt-BR.ics?v=3

Confirmado por inspeção manual em 20/09/2026 → SUMMARY
"🟢 Domingo XXV do Tempo Comum", que este módulo converte para
"25º Domingo do Tempo Comum" (formato pedido pelo usuário).
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Optional

import requests

URL_ICS = "https://gcatholic.org/calendar/ics/{ano}-pt-BR.ics?v=3"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

EMOJI_COR = {
    "⚪": "branco",
    "🟢": "verde",
    "🟣": "roxo",
    "🔴": "vermelho",
    "🌸": "rosa",
    "🟡": "dourado",
    "🟠": "dourado",
}

_ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _romano_para_arabico(s: str) -> int:
    total, anterior = 0, 0
    for ch in reversed(s.upper()):
        valor = _ROMANOS.get(ch, 0)
        if valor < anterior:
            total -= valor
        else:
            total += valor
            anterior = valor
    return total


# "Domingo XXV do Tempo Comum" / "Domingo II da Quaresma" / "Domingo III do Advento"
_PADRAO_DOMINGO_NUMERADO = re.compile(
    r"^Domingo\s+([IVXLCDM]+)\s+(do|da)\s+(.+)$", re.IGNORECASE
)


_CARACTERES_INVISIVEIS = (
    "︎"  # VARIATION SELECTOR-15 (força apresentação como texto)
    "️"  # VARIATION SELECTOR-16 (força apresentação como emoji)
    "​"  # ZERO WIDTH SPACE
    "‌"  # ZERO WIDTH NON-JOINER
    "‍"  # ZERO WIDTH JOINER
    "﻿"  # ZERO WIDTH NO-BREAK SPACE / BOM
)


def _limpar_invisiveis(texto: str) -> str:
    """Remove caracteres invisíveis de formatação de emoji (ex.:
    VARIATION SELECTOR-16 U+FE0F, que alguns feeds colam logo depois
    do emoji de cor, tipo '⚪️') e outros caracteres de largura zero.
    Sem isso, a regex do título ('^Domingo...') falha porque a string
    não começa visualmente, mas tecnicamente começa, com esse
    caractere invisível — bug real encontrado em produção (conversão
    de romano para ordinal simplesmente não disparava). Remove só esse
    conjunto específico e conhecido — nunca a categoria genérica 'Mn'
    inteira, que incluiria acentos combinantes legítimos do português
    em textos não normalizados (NFD)."""
    for ch in _CARACTERES_INVISIVEIS:
        texto = texto.replace(ch, "")
    return texto


def formatar_titulo_dia(titulo: str) -> str:
    """Converte 'Domingo XXV do Tempo Comum' em '25º Domingo do Tempo
    Comum' (o formato pedido pelo usuário). Qualquer outro título (dia
    de semana, festa, solenidade) volta só limpo, sem alteração."""
    titulo = _limpar_invisiveis((titulo or "").strip()).strip()
    m = _PADRAO_DOMINGO_NUMERADO.match(titulo)
    if m:
        numero = _romano_para_arabico(m.group(1))
        return f"{numero}º Domingo {m.group(2)} {m.group(3)}"
    return titulo


def _tempo_liturgico_de(titulo: str) -> Optional[str]:
    baixo = titulo.lower()
    if "advento" in baixo:
        return "Advento"
    if "natal" in baixo:
        return "Tempo do Natal"
    if "quaresma" in baixo or "cinzas" in baixo:
        return "Quaresma"
    if "páscoa" in baixo or "pascal" in baixo or "pentecostes" in baixo:
        return "Tempo Pascal"
    if "tempo comum" in baixo:
        return "Tempo Comum"
    return None


def _desfazer_quebras_ics(texto_ics: str) -> list[str]:
    """O formato .ics 'dobra' linhas longas com uma quebra de linha
    seguida de um espaço/tab (RFC 5545 — 'line folding'). Desfaz isso
    antes de procurar os campos, senão SUMMARY/DESCRIPTION longos vêm
    cortados no meio."""
    linhas: list[str] = []
    for linha in texto_ics.splitlines():
        if linha.startswith((" ", "\t")) and linhas:
            linhas[-1] += linha[1:]
        else:
            linhas.append(linha)
    return linhas


@lru_cache(maxsize=4)
def _baixar_ics(ano: int) -> Optional[str]:
    """Baixa o .ics do ano inteiro (cacheado em memória por ano — um
    único download serve o ano todo, todas as datas). Retorna None em
    qualquer falha de rede, para o chamador tratar como 'fonte
    indisponível' sem derrubar o pipeline."""
    try:
        resp = requests.get(URL_ICS.format(ano=ano), headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException:
        return None


def _extrair_do_texto(texto_ics: str, dia: date) -> Optional[dict]:
    """Parte pura (sem rede) — separada só para poder ser testada com
    um texto .ics fixo, sem precisar baixar nada."""
    linhas = _desfazer_quebras_ics(texto_ics)
    alvo = f"DTSTART;VALUE=DATE:{dia.strftime('%Y%m%d')}"

    bloco_atual: list[str] = []
    dentro = False
    for linha in linhas:
        if linha == "BEGIN:VEVENT":
            dentro, bloco_atual = True, []
            continue
        if linha == "END:VEVENT":
            if dentro and any(l == alvo for l in bloco_atual):
                summary = next(
                    (l[len("SUMMARY:"):] for l in bloco_atual if l.startswith("SUMMARY:")),
                    "",
                )
                summary = (
                    summary.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").strip()
                )
                summary = _limpar_invisiveis(summary)

                cor = "verde"
                for emoji, nome_cor in EMOJI_COR.items():
                    if summary.startswith(emoji):
                        cor = nome_cor
                        summary = summary[len(emoji):].strip()
                        break

                rank = None
                m_rank = re.match(r"^\[([A-Za-z*]+)\]\s*(.*)$", summary)
                if m_rank:
                    rank, summary = m_rank.group(1), m_rank.group(2).strip()

                titulo = formatar_titulo_dia(summary)
                return {
                    "titulo": titulo,
                    "cor": cor,
                    "tempo_liturgico": _tempo_liturgico_de(titulo),
                    "rank": rank,
                }
            dentro = False
            continue
        if dentro:
            bloco_atual.append(linha)
    return None


def obter_dia_liturgico(dia: date) -> Optional[dict]:
    """Retorna {'titulo': str, 'cor': str, 'tempo_liturgico': str|None,
    'rank': str|None} para a data pedida, consultando o feed .ics do
    gcatholic.org — ou None se a fonte não responder ou a data não
    constar no feed daquele ano (nunca levanta exceção)."""
    texto_ics = _baixar_ics(dia.year)
    if texto_ics is None:
        return None
    try:
        return _extrair_do_texto(texto_ics, dia)
    except Exception:
        return None


if __name__ == "__main__":
    from datetime import date as _date

    print(obter_dia_liturgico(_date(2026, 9, 20)))
