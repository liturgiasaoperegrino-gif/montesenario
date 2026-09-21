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
from collections import Counter

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
            fontSize=10, textColor="#555555", spaceAfter=8, italic=True,
            alignment=TA_JUSTIFY),
        "corpo": ParagraphStyle("Corpo", parent=base["Normal"],
            fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=6),
        "refrao": ParagraphStyle("RefraoSalmo", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=8, textColor=COR_REFRAO,
            alignment=TA_JUSTIFY),
        "destaque": ParagraphStyle("Destaque", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=8, textColor="#1b6b3a",
            alignment=TA_JUSTIFY),
        "faltante": ParagraphStyle("Faltante", parent=base["Normal"],
            fontSize=9.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=8,
            textColor="#a15c00", italic=True),
        "rodape": ParagraphStyle("Rodape", parent=base["Normal"],
            fontSize=8, textColor="#999999", spaceBefore=16, alignment=TA_JUSTIFY),
        "rubrica": ParagraphStyle("Rubrica", parent=base["Normal"],
            fontSize=9.5, leading=14, alignment=TA_CENTER, spaceBefore=6,
            spaceAfter=6, textColor="#777777", italic=True),
        # Celebrante: rótulo em negrito (aplicado no texto com <b>),
        # texto justificado como o resto do relatório.
        "falante_padre": ParagraphStyle("FalantePadre", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=6, alignment=TA_JUSTIFY),
        # Todos: resposta da assembleia logo após a invocação do
        # celebrante — rótulo e texto em vermelho, também justificado.
        "falante_todos": ParagraphStyle("FalanteTodos", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=8, leftIndent=14,
            textColor=COR_RESPOSTA_ASSEMBLEIA, alignment=TA_JUSTIFY),
        "resposta_assembleia": ParagraphStyle("RespostaAssembleia", parent=base["Normal"],
            fontSize=10.5, leading=15, spaceAfter=6, leftIndent=14,
            textColor=COR_RESPOSTA_ASSEMBLEIA, alignment=TA_JUSTIFY),
    }


_PADRAO_VERSICULO_INLINE = re.compile(r"(?<!\w)(\d{1,3})(?=[A-ZÀ-ÖØ-Ýa-zà-öø-ÿ])")


def estilizar_versiculos_inline(texto: str) -> str:
    """SUPRIME (não apenas estiliza) números de versículo já colados ao
    início da palavra seguinte, sem espaço — o padrão usual do texto
    bíblico impresso (ex.: '6Buscai o Senhor... 7Abandone o ímpio...').
    Pedido explícito do usuário: a numeração de versículo não deve
    aparecer no layout das leituras/Evangelho — nem destacada, nem lisa
    — então o número é removido, não recolorido (nome da função mantido
    por compatibilidade com quem já importa daqui). Não mexe em números
    seguidos de espaço, pontuação ou outro dígito (não são marcação de
    versículo)."""
    return _PADRAO_VERSICULO_INLINE.sub("", texto)


# ============================================================
# Limpeza do texto bruto de leituras/salmo (Nova Aliança / CNBB)
# ============================================================
#
# BUG REAL encontrado em 21/09/2026 por captura de tela do usuário: o
# texto que a Nova Aliança/CNBB devolvem para cada leitura/salmo NÃO é
# só o corpo do texto — vem com a referência bíblica repetida, a linha
# de introdução ('Leitura da/do/de ...'), os números de versículo cada
# um em sua PRÓPRIA LINHA (não colados à palavra seguinte, como
# '_PADRAO_VERSICULO_INLINE' pressupunha) e o fechamento ('Palavra do
# Senhor.'/'Graças a Deus.') tudo dentro do mesmo bloco de texto. Como o
# roteiro já gera por conta própria o título da seção (com a
# referência), a linha de introdução (via roteiro_fixo.intro_leitura) e
# o fechamento (via o diálogo fixo), sem limpeza esse conteúdo aparece
# DUPLICADO — e pior: números de versículo soltos em linha própria não
# batem com o padrão inline, então passavam batido, e alguns (ex.: o
# '4' de '4bc-5' ou o '6' de '(R. 6a)' dentro da própria referência do
# Salmo) acabavam sendo cortados por engano pela função de supressão
# acima, mutilando a citação.
_PADRAO_LINHA_NUMERO_VERSICULO = re.compile(r"^\d{1,3}[a-zà-ÿ]{0,3}\.?$", re.IGNORECASE)
# BUG REAL encontrado em 21/09/2026 (2ª rodada), no Evangelho de um
# Domingo com passagem longa (Mt 21,33-43): a CNBB às vezes não separa
# o número do versículo em linha própria (caso já coberto acima) nem o
# cola direto na palavra seguinte sem espaço (caso já coberto por
# '_PADRAO_VERSICULO_INLINE', abaixo) — em vez disso, o número abre a
# própria linha seguido de um espaço e do texto do versículo na
# sequência (ex.: '33 Havia um homem, proprietário de terras...').
# Sem isso, esse número sobrevivia sozinho ao início da linha. Só é
# aplicado ao INÍCIO da linha (nunca no meio do texto) para não confundir
# com números que fazem parte do conteúdo bíblico de verdade (idades,
# quantidades etc.), que nunca abrem a linha sozinhos assim.
_PADRAO_PREFIXO_VERSICULO_LINHA = re.compile(r"^\d{1,3}[a-zà-ÿ]{0,3}\.?\s+(?=\S)", re.IGNORECASE)
_PADRAO_LINHA_INTRO_LEITURA = re.compile(r"^Leitura\s+(da|do|de)\b", re.IGNORECASE)
_PADRAO_LINHA_FECHAMENTO = re.compile(
    r"^(Palavra do Senhor\.?|Gra[çc]as a Deus\.?|Palavra da Salva[çc][ãa]o\.?|"
    r"Gl[óo]ria a [Vv][óo]s,?\s*Senhor\.?|O Senhor esteja convosco\.?|"
    r"Ele est[áa] no meio de n[óo]s\.?|Proclama[çc][ãa]o do Evangelho\b.*)$",
    re.IGNORECASE,
)
_PADRAO_OU_MAIS_BREVE = re.compile(r"^ou\s+mais\s+breve$", re.IGNORECASE)


def limpar_texto_leitura(texto_bruto: str, ref: str = "", preservar_quebras: bool = False) -> str:
    """Limpa o texto corrido de uma leitura/salmo/evangelho vindo de uma
    fonte que despeja o bloco inteiro (referência + introdução + forma
    breve alternativa + números de versículo em linhas soltas +
    fechamento) junto com o corpo do texto — é o caso da Nova Aliança e
    da CNBB. Remove:
      - a linha da própria referência bíblica (já mostrada no título da
        seção, ex.: 'Ez 18, 25-28');
      - a linha 'ou mais breve' e a referência curta alternativa que a
        segue (ex.: '2, 1-5') — sem apagar o resto do texto, que vem
        DEPOIS dessas duas linhas, não a partir delas;
      - a linha de introdução ('Leitura da/do/de ...' — o roteiro já
        gera a sua própria, com o nome completo do livro, via
        roteiro_fixo.intro_leitura);
      - linhas que são só o número do versículo, sozinho na própria
        linha (opcionalmente com sufixo de letra, ex.: '27', '16a');
      - o fechamento ('Palavra do Senhor.', 'Graças a Deus.', o diálogo
        de abertura do Evangelho etc. — já são adicionados pelo próprio
        roteiro).
    Texto que já vem limpo (ex.: do Pocket Terço) passa incólume — os
    padrões acima só batem com essas linhas específicas, não com o
    corpo real do texto.

    `preservar_quebras=True` junta as linhas restantes com '\\n' em vez
    de ' ' — usado pelo Salmo (ver separar_refrao_estrofes_salmo), que
    precisa das quebras de linha originais pra detectar o refrão
    repetido linha a linha; para leitura corrida (padrão), junta com
    espaço, que é o certo para um texto em prosa contínua."""
    texto = (texto_bruto or "").strip()
    if not texto:
        return texto

    linhas_brutas = texto.split("\n")
    sem_forma_breve = []
    i = 0
    while i < len(linhas_brutas):
        linha = linhas_brutas[i].strip()
        if _PADRAO_OU_MAIS_BREVE.match(linha):
            i += 1
            # Descarta também a referência curta alternativa da forma
            # breve, se vier logo em seguida (linha começando com
            # dígito e que NÃO é a intro 'Leitura da/do/de...').
            if i < len(linhas_brutas):
                proxima = linhas_brutas[i].strip()
                if proxima and re.match(r"^\d", proxima) and not _PADRAO_LINHA_INTRO_LEITURA.match(proxima):
                    i += 1
            continue
        sem_forma_breve.append(linhas_brutas[i])
        i += 1

    ref_normalizada = re.sub(r"\s+", "", ref or "").lower()
    linhas_limpas = []
    for linha in sem_forma_breve:
        linha = linha.strip()
        if not linha:
            continue
        if ref_normalizada and re.sub(r"\s+", "", linha).lower() == ref_normalizada:
            continue
        if _PADRAO_LINHA_INTRO_LEITURA.match(linha):
            continue
        if _PADRAO_LINHA_NUMERO_VERSICULO.match(linha):
            continue
        if _PADRAO_LINHA_FECHAMENTO.match(linha):
            continue
        linha = _PADRAO_PREFIXO_VERSICULO_LINHA.sub("", linha, count=1)
        linhas_limpas.append(linha)
    separador = "\n" if preservar_quebras else " "
    return separador.join(linhas_limpas).strip()


def separar_refrao_estrofes_salmo(texto_limpo: str) -> tuple[str, list[str]]:
    """A partir do texto do Salmo já limpo (ver limpar_texto_leitura,
    sem referência/números/fechamento), detecta o refrão PELA REPETIÇÃO:
    numa fonte que despeja o texto sem o marcador '-' do Pocket Terço
    (CNBB/Nova Aliança, usadas aqui só como fallback), a linha do refrão
    aparece IDÊNTICA várias vezes, intercalada com cada estrofe (formato
    tradicional do saltério: refrão, estrofe, refrão, estrofe...).
    Acha a linha mais repetida, remove todas as ocorrências e devolve
    as estrofes restantes, na ordem em que aparecem. Se nada se repetir
    (não dá pra distinguir refrão de estrofe), devolve refrão vazio e
    todo o texto como uma estrofe só — comportamento antigo, sem
    negrito automático."""
    linhas = [l.strip() for l in texto_limpo.split("\n") if l.strip()]
    if not linhas:
        return "", []

    contagem = Counter(linhas)
    linha_mais_comum, vezes = contagem.most_common(1)[0]
    if vezes < 2:
        return "", linhas

    estrofes = [l for l in linhas if l != linha_mais_comum]
    return linha_mais_comum, estrofes


def paragrafo_versiculo(numero: str, texto: str, estilos: dict, cor_r: bool = False) -> Paragraph:
    """Renderiza um verso/estrofe no estilo 'corpo' (justificado). O
    número do versículo (parâmetro `numero`, vindo do formato estruturado
    da CNBB) NÃO é mais exibido — pedido explícito do usuário para
    suprimir toda numeração de versículo do layout — só é usado
    internamente (`cor_r`) para localizar o fim do refrão do Salmo."""
    texto_html = texto.replace("\n", "<br/>")
    if cor_r:
        texto_html = re.sub(
            r"(<br/>)?\s*R[:.]\s*$",
            f' <font color="{COR_REFRAO}">R:</font>',
            texto_html,
        )
    return Paragraph(texto_html, estilos["corpo"])


def paragrafo_dialogo(falante: str, texto: str, estilos: dict) -> Paragraph:
    if not falante:
        return Paragraph(texto, estilos["rubrica"])
    if falante == "Todos":
        # Resposta da assembleia logo após a invocação do celebrante (ou
        # comentarista): rótulo e texto em vermelho (estilo já com essa
        # cor).
        return Paragraph(f"<b>{falante}:</b> {texto}", estilos["falante_todos"])
    # Qualquer outro falante (Celebrante, Comentarista, etc.) — rótulo em
    # negrito, texto preto e justificado, igual ao resto do relatório.
    return Paragraph(f"<b>{falante}:</b> {texto}", estilos["falante_padre"])


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
