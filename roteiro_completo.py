# -*- coding: utf-8 -*-
"""
roteiro_completo.py — Monte Senário

Monta o roteiro completo da missa (20 seções, ver secoes_roteiro.py) para
uma data específica. Módulo genérico e reaproveitável — não amarrado a
nenhuma data — usado tanto pelos scripts de uma data específica quanto
(no futuro) por um botão "Gerar roteiro" dentro do app.py.

Duas coisas que valem destacar:

1. Overrides por seção: `overrides` é um dict {"NN": "texto livre"} (ver
   sheets_sync.carregar_overrides_secoes). Quando uma seção tem override,
   o texto do operador substitui o conteúdo automático inteiro daquela
   seção — usado sobretudo para a 02 (Palavras de Abertura, que fica em
   branco por padrão: é o usuário quem escreve) e a 19 (Novenas/Reflexões),
   mas vale para qualquer seção em caso de ajuste pontual.

2. Leituras/Salmo/Evangelho aceitam DOIS formatos de dado, porque nem
   toda fonte dá a mesma estrutura:
   - {"versos": [(numero, texto), ...], "intro": "..."} — quando se tem o
     HTML bruto da CNBB (cortar_secoes_cnbb + extrair_versiculos), com
     numeração de versículo individual.
   - {"texto_corrido": "..."} — texto já pronto, verbatim, sem numeração
     por versículo (usado quando só se tem o texto de outra fonte, como
     Pocket Terço/Nova Aliança via WebFetch, sem o JSON estruturado da
     CNBB). Renderizado como parágrafo corrido, sem números vermelhos.
"""

from __future__ import annotations

import os

from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image, Table, TableStyle,
)

import roteiro_fixo as fixo
from roteiro_render import (
    montar_estilos, paragrafo_versiculo, paragrafo_dialogo,
    paragrafos_com_respostas_assembleia, estilizar_versiculos_inline,
    remover_glifos_invalidos, extrair_texto_proprio_prefacio,
    COR_REFRAO,
)


def _imagem_proporcional(caminho: str, largura_alvo: float):
    """Abre um arquivo de imagem LOCAL e devolve um reportlab.platypus.
    Image com essa `largura_alvo` e a altura calculada proporcionalmente
    ao tamanho real do arquivo (nunca estica/comprime — bug real
    corrigido em 22/09/2026, quando largura e altura fixas e iguais
    distorciam qualquer logo que não fosse quadrado). Retorna None se o
    arquivo não existir ou não puder ser lido como imagem — o cabeçalho
    do PDF é montado sem esse logo nesse caso, em vez de quebrar a
    geração inteira por causa de uma imagem."""
    if not caminho or not os.path.isfile(caminho):
        return None
    try:
        with PILImage.open(caminho) as img:
            largura_px, altura_px = img.size
        altura_alvo = largura_alvo * (altura_px / largura_px)
        return Image(caminho, width=largura_alvo, height=altura_alvo)
    except Exception:
        return None


def _override_ou(overrides: dict, numero: str, padrao):
    """Retorna o texto de override da seção `numero`, se houver, senão
    `padrao` (que pode ser string, lista de tuplas de diálogo, etc. —
    quem chama decide o que fazer com cada tipo)."""
    if overrides and overrides.get(numero):
        return overrides[numero]
    return padrao


def _renderizar_leitura(story, E, dados_leitura: dict, rotulo_ref_style="ref_secao"):
    """Renderiza uma leitura/evangelho a partir do dict de dados (ver
    docstring do módulo para os dois formatos aceitos)."""
    if dados_leitura.get("intro"):
        story.append(Paragraph(dados_leitura["intro"], E[rotulo_ref_style]))
    if "versos" in dados_leitura:
        for numero, texto in dados_leitura["versos"]:
            story.append(paragrafo_versiculo(numero, texto, E))
    elif dados_leitura.get("texto_corrido"):
        for par in dados_leitura["texto_corrido"].split("\n\n"):
            par_html = estilizar_versiculos_inline(par.replace("\n", "<br/>"))
            story.append(Paragraph(par_html, E["corpo"]))


def montar_pdf(caminho_saida: str, dados: dict, overrides: dict | None = None):
    """dados: dict com todo o conteúdo do roteiro para uma data —
    ver os scripts roteiro_20-09-2026.py / roteiro_27-09-2026.py para
    exemplos completos de como montar esse dict a partir das fontes.

    Chaves esperadas em `dados`:
      data_iso, titulo_dia, horario_missa, cor_tema,
      antifona_entrada, coleta,
      leitura1_ref, leitura1 (dict — ver _renderizar_leitura),
      salmo_ref, salmo_refrao, salmo (dict),
      leitura2_ref, leitura2 (dict, opcional — omitir se não houver),
      aclamacao_refrao, aclamacao_versiculo,
      evangelho_ref, evangelho (dict), evangelho_proclamacao (texto da
        linha "Proclamação do Evangelho ... segundo <Evangelista>"),
      oferendas_texto, comunhao_texto,
      prefacio_nome, prefacio_texto,
      oracao_euc (dict {nome, motivo, texto}),
      fontes (dict de strings para o rodapé — ver chaves usadas abaixo).
    """
    overrides = overrides or {}

    doc = SimpleDocTemplate(
        caminho_saida, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
    )
    E = montar_estilos(dados["cor_tema"])
    story = []

    def secao_titulo(numero, nome):
        story.append(Paragraph(f"{numero} — {nome}", E["secao"]))

    def dialogo(lista):
        for falante, texto in lista:
            story.append(paragrafo_dialogo(falante, texto, E))

    def paragrafos_livres(texto):
        for par in texto.split("\n\n"):
            story.append(Paragraph(par.replace("\n", "<br/>"), E["corpo"]))

    data_fmt = f"{dados['data_iso'][8:10]}/{dados['data_iso'][5:7]}/{dados['data_iso'][0:4]}"
    horario = _override_ou(overrides, "00", dados.get("horario_missa", ""))

    # Dois logos no cabeçalho (pedido do usuário em 22/09/2026): o da
    # Igreja São Peregrino à ESQUERDA, o brasão da Ordem dos Servos de
    # Maria (Província São Peregrino do Brasil) à DIREITA — os dois
    # como arquivo local (ver comentário de LOGO_IGREJA_PATH/
    # LOGO_OSM_PATH em roteiro_fixo.py) e sem distorcer a proporção
    # original de nenhum dos dois (_imagem_proporcional).
    largura_logo = 2.5 * cm
    logo_igreja = _imagem_proporcional(fixo.LOGO_IGREJA_PATH, largura_logo)
    logo_osm = _imagem_proporcional(fixo.LOGO_OSM_PATH, largura_logo)
    if logo_igreja or logo_osm:
        # BUG REAL corrigido em 22/09/2026 (relatado pelo usuário: alinhar
        # os logos à linha horizontal/ao texto): o Frame padrão do
        # SimpleDocTemplate tem 6pt de padding interno de cada lado, que
        # o Paragraph e o HRFlowable (a linha verde) já respeitam
        # automaticamente — mas eu tinha dado ao Table a largura CHEIA
        # (doc.width, margem a margem), sem descontar esse padding. O
        # Table ficava então 6pt mais largo de cada lado que o resto do
        # conteúdo, e os logos saíam ligeiramente PRA FORA do alinhamento
        # do título/linha. Descontando os 2×6pt, a tabela ocupa
        # exatamente a mesma largura útil que tudo mais no documento.
        largura_util = doc.width - 12
        largura_coluna = largura_util / 2
        linha_logos = [[logo_igreja or "", logo_osm or ""]]
        tabela_logos = Table(linha_logos, colWidths=[largura_coluna, largura_coluna])
        tabela_logos.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(tabela_logos)
        story.append(Spacer(1, 6))

    story.append(Paragraph("Montesenario", E["titulo"]))
    story.append(Paragraph("Semanário Litúrgico da Igreja São Peregrino - São José dos Campos", E["subtitulo_data"]))
    story.append(Paragraph(
        f"{data_fmt}" + (f" — {horario}" if horario else ""),
        E["subtitulo_data"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=dados["cor_tema"], spaceAfter=10))
    # O título do dia litúrgico NÃO se repete aqui — aparece só uma vez,
    # na Seção 02 (ver abaixo), já na versão corrigida/convertida.

    # 01 — Saudação
    secao_titulo("01", "Saudação")
    over_01 = overrides.get("01")
    if over_01:
        paragrafos_livres(over_01)
    else:
        dialogo(fixo.SAUDACAO_INICIAL)

    # 02 — o título da seção É a própria Data Litúrgica (ex.: "25º
    # Domingo do Tempo Comum", vindo do gcatholic.org — ver
    # gcatholic_liturgia.py); sem rótulo genérico "Título da Solenidade /
    # Palavras de Abertura" (suprimido a pedido do usuário). As palavras
    # de abertura em si vêm automaticamente para domingo (extraídas do
    # Semanário Litúrgico da Diocese de SJC — ver palavras_abertura_sjc.py);
    # em dia de semana, ou se a fonte ainda não publicou, ficam em branco
    # — o operador escreve via interface. Um override manual sempre tem
    # prioridade sobre as duas fontes.
    secao_titulo("02", dados["titulo_dia"].strip())
    over_02 = overrides.get("02")
    palavras_abertura_auto = dados.get("palavras_abertura", "")
    if over_02:
        paragrafos_livres(over_02)
    elif palavras_abertura_auto:
        paragrafos_livres(palavras_abertura_auto)
    else:
        story.append(Paragraph(
            "(a preencher — use a tela \"Gerenciar Roteiro\" para inserir "
            "as palavras de abertura desta missa)", E["faltante"]
        ))

    # 03 — Ritos Iniciais: quando há Antífona de Entrada, ela abre a
    # seção, ANTES da saudação do celebrante ("Em nome do Pai...") —
    # pedido explícito do usuário.
    secao_titulo("03", "Ritos Iniciais")
    over_03 = overrides.get("03")
    if over_03:
        paragrafos_livres(over_03)
    else:
        antifona_entrada = dados.get("antifona_entrada")
        if antifona_entrada:
            story.append(Paragraph("Antífona de Entrada", E["ref_secao"]))
            paragrafos_livres(antifona_entrada)
        dialogo(fixo.RITOS_INICIAIS)

    # 04 — Ato Penitencial
    secao_titulo("04", "Ato Penitencial")
    over_04 = overrides.get("04")
    if over_04:
        paragrafos_livres(over_04)
    else:
        dialogo(fixo.ATO_PENITENCIAL)

    # 05 — Glória: só o título da seção (texto da oração suprimido a
    # pedido do usuário — o celebrante/assembleia já sabem de cor).
    # Um override manual continua funcionando normalmente, se algum dia
    # precisar mostrar um texto específico aqui.
    over_05 = overrides.get("05")
    if over_05:
        secao_titulo("05", "Glória")
        paragrafos_livres(over_05)
    elif fixo.gloria_e_dita(dados["titulo_dia"]):
        secao_titulo("05", "Glória")

    # 06 — Coleta
    secao_titulo("06", "Oração da Coleta")
    paragrafos_livres(_override_ou(overrides, "06", dados["coleta"]))

    # 07 — Liturgia da Palavra (cabeçalho only, salvo override)
    secao_titulo("07", "Liturgia da Palavra")
    if overrides.get("07"):
        paragrafos_livres(overrides["07"])

    # 08 — Primeira Leitura. Encerra com o diálogo fixo "Palavra do
    # Senhor. / Todos: Graças a Deus." — só no conteúdo automático; um
    # override livre assume que o operador já incluiu tudo que quer.
    secao_titulo("08", f"Primeira Leitura {dados['leitura1_ref']}")
    if overrides.get("08"):
        paragrafos_livres(overrides["08"])
    else:
        _renderizar_leitura(story, E, dados["leitura1"])
        dialogo([("", "Palavra do Senhor."), ("Todos", "Graças a Deus.")])

    # 09 — Salmo Responsorial: formato-padrão dos boletins/missalinhas —
    # refrão primeiro (cantor/todos), depois CADA estrofe numerada
    # (1., 2., 3. — não mais com travessão) seguida da REPETIÇÃO do
    # refrão, terminando sempre no refrão (não na última estrofe).
    # Correção pedida explicitamente pelo usuário ("acerte a forma de
    # apresentar o Salmo").
    secao_titulo("09", f"Salmo Responsorial {dados['salmo_ref']}")
    if overrides.get("09"):
        paragrafos_livres(overrides["09"])
    else:
        refrao_html = f'<b><font color="{COR_REFRAO}">R:</font> {dados["salmo_refrao"]}</b>'
        if "versos" in dados["salmo"]:
            story.append(Paragraph(refrao_html, E["refrao"]))
            for numero, texto in dados["salmo"]["versos"]:
                story.append(paragrafo_versiculo(numero, texto, E))
                story.append(Paragraph(refrao_html, E["refrao"]))
        elif dados["salmo"].get("texto_corrido"):
            estrofes = [
                e.strip().lstrip("-").strip()
                for e in dados["salmo"]["texto_corrido"].split("\n\n")
                if e.strip()
            ]
            story.append(Paragraph(refrao_html, E["refrao"]))
            for i, estrofe in enumerate(estrofes, start=1):
                estrofe_html = estilizar_versiculos_inline(estrofe.replace("\n", "<br/>"))
                story.append(Paragraph(f"{i}. {estrofe_html}", E["corpo"]))
                story.append(Paragraph(refrao_html, E["refrao"]))

    # 10 — Segunda Leitura (só se houver) — mesmo fechamento da 1ª Leitura
    if overrides.get("10"):
        secao_titulo("10", f"Segunda Leitura {dados.get('leitura2_ref', '')}")
        paragrafos_livres(overrides["10"])
    elif dados.get("leitura2"):
        secao_titulo("10", f"Segunda Leitura {dados['leitura2_ref']}")
        _renderizar_leitura(story, E, dados["leitura2"])
        dialogo([("", "Palavra do Senhor."), ("Todos", "Graças a Deus.")])

    # 11 — Aclamação ao Evangelho: precedida do convite do comentarista e
    # de uma subseção "Canto de Aclamação do Evangelho" (padrão pedido
    # pelo usuário).
    secao_titulo("11", "Aclamação ao Evangelho")
    if overrides.get("11"):
        paragrafos_livres(overrides["11"])
    else:
        dialogo([("Comentarista", fixo.CONVITE_ACLAMACAO)])
        story.append(Paragraph("Canto de Aclamação do Evangelho", E["ref_secao"]))
        # Estilo espelhando a fonte (Pocket Terço: "℟." = refrão, "℣." =
        # versículo) — usando "R:"/"V:" em vez dos símbolos litúrgicos
        # ℟/℣ porque a fonte padrão do PDF (Helvetica, sem glifos
        # especiais registrados) não os desenha, e viravam quadradinhos
        # pretos no lugar (bug pego em teste visual antes de entregar).
        # Mesmo padrão "R:" em negrito já usado no Salmo (Seção 09).
        refrao_aclamacao = dados.get("aclamacao_refrao") or "Aleluia, Aleluia, Aleluia."
        story.append(Paragraph(
            f'<b><font color="{COR_REFRAO}">R:</font> {refrao_aclamacao}</b>', E["corpo"]
        ))
        if dados.get("aclamacao_versiculo"):
            story.append(Paragraph(
                f'<b>V:</b> {dados["aclamacao_versiculo"]}', E["corpo"]
            ))

    # 12 — Evangelho
    secao_titulo("12", f"Evangelho {dados['evangelho_ref']}")
    if overrides.get("12"):
        paragrafos_livres(overrides["12"])
    else:
        dialogo(fixo.dialogo_abertura_evangelho(dados["evangelho_proclamacao"]))
        _renderizar_leitura(story, E, dados["evangelho"])
        dialogo(fixo.EVANGELHO_FECHAMENTO)

    # 13 — Profissão de Fé
    secao_titulo("13", "Profissão de Fé")
    paragrafos_livres(_override_ou(overrides, "13", fixo.PROFISSAO_DE_FE))

    # 14 — Liturgia Eucarística (apresentação das oferendas)
    secao_titulo("14", "Liturgia Eucarística")
    over_14 = overrides.get("14")
    if over_14:
        paragrafos_livres(over_14)
    else:
        dialogo(fixo.APRESENTACAO_DAS_OFERENDAS)

    # 15 — Oração sobre as Oferendas
    secao_titulo("15", "Oração sobre as Oferendas")
    paragrafos_livres(_override_ou(overrides, "15", dados["oferendas_texto"]))

    # 16 — Prefácio + Oração Eucarística (respostas da assembleia em vermelho)
    secao_titulo("16", f"Prefácio — {dados['prefacio_nome']}")
    if overrides.get("16"):
        paragrafos_livres(overrides["16"])
    else:
        # Diálogo Introdutório do Prefácio: sempre o texto fixo do
        # Missal (ver roteiro_fixo.DIALOGO_PREFACIO) — não depende mais
        # de o arquivo/boletim trazer esse trecho intacto (era a parte
        # mais sujeita a caracteres quebrados/duplicação do nome do
        # Prefácio, já mostrado no título da seção acima).
        dialogo(fixo.DIALOGO_PREFACIO)
        texto_prefacio_limpo = remover_glifos_invalidos(
            extrair_texto_proprio_prefacio(dados["prefacio_texto"])
        )
        for flowable in paragrafos_com_respostas_assembleia(texto_prefacio_limpo, E):
            story.append(flowable)
        story.append(Spacer(1, 6))
        story.append(Paragraph(dados["oracao_euc"]["nome"], E["secao"]))
        story.append(Paragraph(dados["oracao_euc"]["motivo"], E["destaque"]))
        for flowable in paragrafos_com_respostas_assembleia(dados["oracao_euc"]["texto"], E):
            story.append(flowable)

    # 17 — Ritos da Comunhão
    secao_titulo("17", "Ritos da Comunhão")
    over_17 = overrides.get("17")
    if over_17:
        paragrafos_livres(over_17)
    else:
        dialogo(fixo.RITOS_DA_COMUNHAO)

    # 18 — Oração após a Comunhão
    secao_titulo("18", "Oração após a Comunhão")
    paragrafos_livres(_override_ou(overrides, "18", dados["comunhao_texto"]))

    # 19 — Novenas e Reflexões Especiais (em branco por padrão)
    secao_titulo("19", "Novenas e Reflexões Especiais")
    over_19 = overrides.get("19")
    if over_19:
        paragrafos_livres(over_19)
    else:
        story.append(Paragraph("Nenhuma inserida para esta data.", E["faltante"]))

    # 20 — Ritos Finais e Bênção Final
    secao_titulo("20", "Ritos Finais e Bênção Final")
    over_20 = overrides.get("20")
    if over_20:
        paragrafos_livres(over_20)
    else:
        dialogo(fixo.RITOS_FINAIS)

    # Rodapé de fontes
    fontes = dados.get("fontes", {})
    linhas_fonte = [f"{rotulo}: {valor}" for rotulo, valor in fontes.items() if valor]
    linhas_fonte.append("Documento gerado pelo pipeline Monte Senário — roteiro padronizado em 20 seções.")
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color="#cccccc"))
    story.append(Paragraph("<br/>".join(linhas_fonte), E["rodape"]))

    doc.build(story)
