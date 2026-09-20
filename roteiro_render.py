# -*- coding: utf-8 -*-
"""
roteiro_render.py — Monte Senário

Helpers de renderização compartilhados por todos os geradores de
roteiro: parse estruturado do HTML bruto da CNBB (numeração de
versículos, refrão do salmo), mapeamento de cor litúrgica e os estilos
ReportLab padronizados do projeto. Promovido para módulo próprio depois
de duplicado em gerar_pdf_20-09-2026.py — qualquer roteiro novo importa
daqui em vez de reescrever.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Paragraph

CORES_LITURGICAS = {
    "verde": "#2e7d32",
    "roxo": "#6a1b9a",
    "vermelho": "#c62828",
    "branco": "#b8860b",
    "dourado": "#b8860b",
    "rosa": "#d81b60",
}
COR_TEMA_PADRAO = "#5b2a86"
COR_VERSICULO = "#c62828"
COR_REFRAO = "#c62828"
COR_RESPOSTA_ASSEMBLEIA = "#c62828"

# Marcador usado dentro dos textos de oracoes_eucaristicas.py para sinalizar
# uma fala da assembleia (ex.: "AS: Amém."). "AS" = "Assembleia".
MARCADOR_RESPOSTA_ASSEMBLEIA = "AS:"


def cor_do_tema(cor_liturgica: str) -> str:
    return CORES_LITURGICAS.get((cor_liturgica or "").lower(), COR_TEMA_PADRAO)


def inferir_cor_liturgica(titulo_dia: str) -> str:
    """Deduz a cor litúrgica pelo título do dia, para quando a fonte não
    informa a cor diretamente (a CNBB informa; Nova Aliança/Pocket Terço
    não) — evita que o roteiro saia sem cor de tema só porque a fonte
    principal não respondeu. Regra simplificada (não cobre exceções como
    Domingo Gaudete/Laetare em rosa, ou memórias facultativas específicas
    de mártires) — dá conta do caso comum do calendário litúrgico."""
    t = (titulo_dia or "").lower()
    if "quaresma" in t or "advento" in t:
        return "roxo"
    if "ramos" in t or "paixão" in t or "sexta-feira santa" in t or "pentecostes" in t or "mártir" in t:
        return "vermelho"
    if "páscoa" in t or "pascal" in t or "natal" in t or "solenidade" in t:
        return "branco"
    return "verde"  # Tempo Comum — o caso mais frequente do calendário


def _remover_ocultos(soup: BeautifulSoup) -> BeautifulSoup:
    for oculto in soup.find_all(style=re.compile(r"display:\s*none")):
        oculto.decompose()
    return soup


def cortar_secoes_cnbb(body_html: str) -> dict:
    soup = _remover_ocultos(BeautifulSoup(body_html, "html.parser"))
    texto_html = str(soup)
    marcadores = [
        ("leitura1", "PRIMEIRA LEITURA"),
        ("leitura2", "SEGUNDA LEITURA"),
        ("salmo", "Salmo responsorial"),
        ("aclamacao", "Aclamação ao Evangelho"),
        ("evangelho", "EVANGELHO"),
    ]
    posicoes = sorted(
        (texto_html.find(m), n) for n, m in marcadores if texto_html.find(m) != -1
    )
    chunks = {}
    for i, (ini, nome) in enumerate(posicoes):
        fim = posicoes[i + 1][0] if i + 1 < len(posicoes) else len(texto_html)
        chunks[nome] = texto_html[ini:fim]
    return chunks


def extrair_intro_secao(chunk_html: str, rotulo_secao: str) -> str:
    soup = BeautifulSoup(chunk_html, "html.parser")
    for p in soup.find_all("p"):
        p.decompose()
    partes = []
    for el in soup.contents:
        if getattr(el, "name", None) == "div":
            break
        texto = el.get_text(strip=True) if hasattr(el, "get_text") else str(el).strip()
        if texto:
            partes.append(texto)
    intro = " ".join(partes)
    return intro.replace(rotulo_secao, "", 1).strip()


def extrair_versiculos(chunk_html: str) -> list:
    soup = BeautifulSoup(chunk_html, "html.parser")
    versos = []
    for flex_div in soup.find_all("div", style=re.compile(r"display:\s*flex")):
        filhos = flex_div.find_all("div", recursive=False)
        if len(filhos) < 2:
            continue
        numero = filhos[0].get_text(strip=True)
        texto = filhos[1].get_text("\n", strip=True)
        if texto:
            versos.append((numero, texto))
    return versos


def extrair_refrao_salmo(body_html: str) -> str:
    m = re.search(r'<font color="red">R\.</font>\s*([^<]+)', body_html)
    return m.group(1).strip() if m else ""


def extrair_aclamacao_evangelho(chunk_html: str) -> dict:
    """Extrai o refrão (R.) e o versículo (V.) da Aclamação ao Evangelho
    a partir do chunk isolado por cortar_secoes_cnbb (chave 'aclamacao').
    A CNBB traz isso como texto corrido com quebras <br>, sem a mesma
    estrutura de divs em flex usada nas leituras/salmo, então o parse é
    por regex sobre o texto já sem tags (preservando as quebras de linha
    dos <br> como '\\n' antes de extrair)."""
    soup = BeautifulSoup(chunk_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    texto = soup.get_text()
    texto = re.sub(r"\n[ \t\xa0]*\n+", "\n", texto).strip()

    m_refrao = re.search(r"R\.\s*([^\n]+)", texto)
    m_versiculo = re.search(r"V\.\s*(.+)", texto, flags=re.DOTALL)

    refrao = m_refrao.group(1).strip() if m_refrao else ""
    versiculo = ""
    if m_versiculo:
        linhas = [l.strip(" \xa0") for l in m_versiculo.group(1).splitlines()]
        versiculo = " ".join(l for l in linhas if l)

    return {"refrao": refrao, "versiculo": versiculo}


def montar_estilos(cor_tema: str) -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("TituloProjeto", parent=base["Title"],
            fontSize=18, spaceAfter=2, textColor=cor_tema),
        "subtitulo_data": ParagraphStyle("SubtituloData", parent=base["Normal"],
            fontSize=11, alignment=TA_CENTER, textColor="#666666", spaceAfter=10),
        "dia_liturgico": ParagraphStyle("DiaLiturgico", parent=base["Heading2"],
            fontSize=13, alignment=TA_CENTER, spaceAfter=14),
        "secao": ParagraphStyle("Secao", parent=base["Heading3"],
            fontSize=12, spaceBefore=14, spaceAfter=4, textColor=cor_tema),
        "ref_secao": ParagraphStyle("RefSecao", parent=base["Normal"],
            fontSize=10, textColor="#555555", spaceAfter=8, italic=True),
        "corpo": ParagraphStyle("Corpo", parent=base["Normal"],
            fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=6),
        "refrao": ParagraphStyle("RefraoSalmo", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=8, textColor=COR_REFRAO),
        "destaque": ParagraphStyle("Destaque", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=8, textColor="#1b6b3a"),
        "faltante": ParagraphStyle("Faltante", parent=base["Normal"],
            fontSize=9.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=8,
            textColor="#a15c00", italic=True),
        "rodape": ParagraphStyle("Rodape", parent=base["Normal"],
            fontSize=8, textColor="#999999", spaceBefore=16),
        "rubrica": ParagraphStyle("Rubrica", parent=base["Normal"],
            fontSize=9.5, leading=14, alignment=TA_CENTER, spaceBefore=6,
            spaceAfter=6, textColor="#777777", italic=True),
        "falante_padre": ParagraphStyle("FalantePadre", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=6),
        "falante_todos": ParagraphStyle("FalanteTodos", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=8, leftIndent=14),
        "resposta_assembleia": ParagraphStyle("RespostaAssembleia", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=6, leftIndent=14,
            textColor=COR_RESPOSTA_ASSEMBLEIA),
    }


_PADRAO_VERSICULO_INLINE = re.compile(r"(?<!\w)(\d{1,3})(?=[A-ZÀ-ÖØ-Ýa-zà-öø-ÿ])")


def estilizar_versiculos_inline(texto: str) -> str:
    """Destaca (cor + fonte menor, sem quebrar a leitura contínua) números
    de versículo já colados ao início da palavra seguinte, sem espaço —
    o padrão usual do texto bíblico impresso (ex.: '6Buscai o Senhor...
    7Abandone o ímpio...'). Não mexe em números seguidos de espaço,
    pontuação ou outro dígito (não são marcação de versículo)."""
    return _PADRAO_VERSICULO_INLINE.sub(
        lambda m: f'<font color="{COR_VERSICULO}" size="7">{m.group(1)}</font>',
        texto,
    )


def paragrafo_versiculo(numero: str, texto: str, estilos: dict, cor_r: bool = False) -> Paragraph:
    texto_html = texto.replace("\n", "<br/>")
    if cor_r:
        texto_html = re.sub(
            r"(<br/>)?\s*R\.\s*$",
            f' <font color="{COR_REFRAO}">R.</font>',
            texto_html,
        )
    prefixo = (
        f'<font color="{COR_VERSICULO}" size="8">{numero}</font>&nbsp;&nbsp;'
        if numero else ""
    )
    return Paragraph(prefixo + texto_html, estilos["corpo"])


def paragrafo_dialogo(falante: str, texto: str, estilos: dict) -> Paragraph:
    if not falante:
        return Paragraph(texto, estilos["rubrica"])
    if falante == "Padre":
        return Paragraph(f"<b>Padre:</b> {texto}", estilos["falante_padre"])
    return Paragraph(f"<b>{falante}:</b> {texto}", estilos["falante_todos"])


def paragrafos_com_respostas_assembleia(texto: str, estilos: dict) -> list:
    """Divide um texto de oração (Prefácio, Oração Eucarística) em
    parágrafos, destacando em vermelho — como resposta da assembleia —
    qualquer linha que:
      a) comece com o marcador 'AS:' (convenção usada em
         oracoes_eucaristicas.py para as respostas do povo dentro do
         Cânon), ou
      b) seja o refrão do Santo ('Santo, Santo, Santo, Senhor...'), que
         aparece no fim do Prefácio sem o marcador AS: porque é cantado
         por todos, padre incluso, mas ainda assim é a aclamação da
         assembleia.
    Cada parágrafo de origem (separado por linha em branco no texto) vira
    um ou mais Paragraph — um por linha 'AS:' encontrada, e o restante do
    parágrafo (se houver) num Paragraph normal antes dela."""
    flowables = []
    for bloco in texto.split("\n\n"):
        bloco = bloco.strip()
        if not bloco:
            continue
        linhas = bloco.split("\n")
        texto_normal_acumulado = []

        def _despeja_normal():
            if texto_normal_acumulado:
                trecho = "<br/>".join(texto_normal_acumulado)
                flowables.append(Paragraph(trecho, estilos["corpo"]))
                texto_normal_acumulado.clear()

        for linha in linhas:
            linha_strip = linha.strip()
            eh_resposta = linha_strip.startswith(MARCADOR_RESPOSTA_ASSEMBLEIA) or (
                linha_strip.startswith("Santo, Santo, Santo")
            )
            if eh_resposta:
                _despeja_normal()
                texto_resposta = linha_strip
                if texto_resposta.startswith(MARCADOR_RESPOSTA_ASSEMBLEIA):
                    texto_resposta = texto_resposta[len(MARCADOR_RESPOSTA_ASSEMBLEIA):].strip()
                flowables.append(Paragraph(
                    f"<b>Todos:</b> {texto_resposta}", estilos["resposta_assembleia"]
                ))
            else:
                texto_normal_acumulado.append(linha)
        _despeja_normal()
    return flowables
