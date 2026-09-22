# -*- coding: utf-8 -*-
"""
app.py — Monte Senário

App Streamlit para consultar os textos litúrgicos (leituras + orações)
já gravados na planilha Google Sheets, e para disparar a atualização
sob demanda a partir do site novaalianca.com.br.

Cada dia pode ter mais de um horário de missa (ex.: domingo 10h e 19h;
dia 4 do mês com 2-3 horários) — os horários válidos para cada tipo de
dia vêm da aba "Horarios_Padrao" da planilha (TIPO_DIA | HORARIO), e
cada combinação DATA+HORARIO tem seu próprio roteiro, editável
separadamente.

Rodar:
    streamlit run app.py
"""

import re
import tempfile
from datetime import date, timedelta

import streamlit as st

from google.oauth2.service_account import Credentials

from sheets_sync import (
    conectar_planilha_com_info,
    sincronizar_intervalo,
    completar_oferendas_comunhao,
    salvar_prefacio_selecionado,
    carregar_overrides_secoes,
    salvar_override_secao,
    obter_horarios_padrao,
    horarios_para_data,
    HORARIO_PADRAO_FALLBACK,
    SCOPES,
)
from prefacios_drive import (
    conectar_drive, listar_prefacios, baixar_texto_prefacio, buscar_arquivo_por_termo,
)
from prefacios import categoria_prefacio_automatica
from gcatholic_liturgia import tempo_liturgico_de
from secoes_roteiro import SECOES
from roteiro_completo import montar_pdf
from roteiro_render import (
    cor_do_tema, limpar_texto_leitura, separar_refrao_estrofes_salmo,
    remover_glifos_invalidos,
)
from roteiro_fixo import intro_leitura, nome_evangelista

st.set_page_config(page_title="Montesenario", page_icon="⛪", layout="centered")


@st.cache_resource
def conectar():
    return conectar_planilha_com_info(
        st.secrets["gcp_service_account"], st.secrets["ID_PLANILHA"]
    )


@st.cache_resource
def conectar_drive_service():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return conectar_drive(creds)


@st.cache_data(ttl=600)
def carregar_lista_prefacios():
    """Lista os prefácios disponíveis na pasta do Drive. Cache de 10 min
    para não bater no Drive toda hora, mas atualiza sozinho quando você
    sobe um arquivo novo."""
    return listar_prefacios(conectar_drive_service())


@st.cache_data(ttl=300)
def carregar_dados():
    aba = conectar()
    return aba.get_all_records()


@st.cache_data(ttl=600)
def carregar_horarios_padrao():
    """{TIPO_DIA: [horarios]} lido da aba Horarios_Padrao. Cache de 10
    min — se você editar a aba, os horários novos aparecem em até esse
    tempo (ou na hora, se recarregar a página logo após editar, já que
    o cache é por sessão)."""
    return obter_horarios_padrao(conectar())


def buscar_por_data_horario(dados: list[dict], data_alvo: date, horario: str) -> dict | None:
    alvo = data_alvo.isoformat()
    for linha in dados:
        if linha.get("DATA") == alvo and linha.get("HORARIO") == horario:
            return linha
    return None


def selecionar_horario(data_escolhida: date, key_prefix: str) -> str:
    """Mostra (quando há mais de um) um seletor de horário de missa para
    a data escolhida, com base na aba Horarios_Padrao. Se só houver um
    horário cadastrado, mostra-o como texto informativo e usa-o direto.
    Se não houver nenhum cadastrado para o tipo de dia, cai no
    HORARIO_PADRAO_FALLBACK com um aviso."""
    horarios_por_tipo = carregar_horarios_padrao()
    horarios_do_dia = horarios_para_data(data_escolhida, horarios_por_tipo)

    if not horarios_do_dia:
        st.caption(
            f"⚠ Nenhum horário cadastrado na aba 'Horarios_Padrao' para este "
            f"tipo de dia — usando {HORARIO_PADRAO_FALLBACK} como padrão."
        )
        return HORARIO_PADRAO_FALLBACK

    if len(horarios_do_dia) == 1:
        st.caption(f"Horário da missa: **{horarios_do_dia[0]}**")
        return horarios_do_dia[0]

    return st.selectbox(
        "Horário da missa", horarios_do_dia, key=f"{key_prefix}_{data_escolhida.isoformat()}"
    )


def sugerir_e_baixar_prefacio_automatico(roteiro: dict, dia: date) -> dict | None:
    """Seção 16 — quando não há Prefácio manual nem sugestão do boletim
    da Diocese de SJC (só domingo), busca automaticamente na pasta do
    Drive ('Orações Eucarísticas', a mesma que o operador já usa para
    escolher manualmente — é o que o usuário chama de pasta
    'Prefácios', já que todo arquivo lá começa com 'PREFÁCIO') qual
    Prefácio corresponde à estação litúrgica do dia (ver
    prefacios.categoria_prefacio_automatica). Retorna {'nome', 'texto'}
    ou None se não há regra confiável para o dia ou se o Drive falhar —
    nesses casos o roteiro cai no aviso 'a critério da escolha
    pastoral', como já era antes deste recurso."""
    tempo = tempo_liturgico_de(roteiro.get("TITULO_DIA", "") or "")
    sugestao = categoria_prefacio_automatica(roteiro.get("TITULO_DIA", ""), tempo, dia)
    if not sugestao:
        return None
    termo_busca, _ad_libitum = sugestao
    try:
        arquivo = buscar_arquivo_por_termo(conectar_drive_service(), termo_busca)
        if not arquivo:
            return None
        texto = baixar_texto_prefacio(conectar_drive_service(), arquivo["id"])
        return {"nome": arquivo["nome"], "texto": texto}
    except Exception:
        return None


def montar_dados_para_pdf(
    linha: dict, horario: str, overrides: dict, sugestao_prefacio: dict | None = None
) -> dict:
    """Converte uma linha da planilha (dict de sheets_sync) no formato de
    dados esperado por roteiro_completo.montar_pdf(). Alguns detalhes
    finos ainda não são capturados automaticamente pelo scraper geral —
    aclamação ao Evangelho com versículo específico, o nome do
    evangelista na 'Proclamação do Evangelho...', e o refrão isolado do
    Salmo — e usam um valor padrão razoável aqui. Se precisar do texto
    exato, o operador pode colar em 'Gerenciar Roteiro' (seções 09, 11 e
    12), que sempre tem prioridade sobre esses padrões."""
    leitura1_ref = linha.get("LEITURA1_REF", "")
    leitura2_ref = linha.get("LEITURA2_REF") or ""
    evangelho_ref = linha.get("EVANGELHO_REF", "")

    # A Nova Aliança/CNBB despejam o bloco inteiro de cada leitura junto
    # com o texto — referência repetida, linha de introdução, números de
    # versículo cada um na sua própria linha e o fechamento ("Palavra do
    # Senhor."/"Graças a Deus.") tudo junto. limpar_texto_leitura() tira
    # tudo isso fora (o roteiro já gera sua própria referência, intro e
    # fechamento) — texto que já vem limpo (Pocket Terço) passa incólume.
    leitura1_texto = limpar_texto_leitura(linha.get("LEITURA1_TEXTO", ""), leitura1_ref)
    # eh_evangelho=True: além da limpeza padrão, corta a saudação/
    # proclamação do celebrante ("O Senhor esteja convosco... /
    # Proclamação do Evangelho... segundo Fulano") quando ela vem
    # duplicada dentro do próprio texto bíblico da fonte — o roteiro já
    # insere essa moldura sozinho, com texto fixo (ver
    # roteiro_fixo.dialogo_abertura_evangelho), logo antes do corpo do
    # Evangelho. `evangelista` (calculado já aqui, não só mais abaixo)
    # ancora o corte no nome real do evangelista do dia — mais confiável
    # que o símbolo (†/✠/nenhum) que a fonte usa antes do nome, e
    # tolerante a quebra de linha entre "Jesus Cristo" e o nome.
    evangelista = nome_evangelista(evangelho_ref)
    evangelho_texto = limpar_texto_leitura(
        linha.get("EVANGELHO_TEXTO", ""), evangelho_ref, eh_evangelho=True, evangelista=evangelista
    )

    leitura2 = None
    if linha.get("LEITURA2_TEXTO"):
        leitura2 = {
            "texto_corrido": limpar_texto_leitura(linha.get("LEITURA2_TEXTO", ""), leitura2_ref),
            "intro": intro_leitura(leitura2_ref),
        }

    evangelho_proclamacao = (
        f"Proclamação do Evangelho de Jesus Cristo † segundo {evangelista}."
        if evangelista
        else "Proclamação do Evangelho de Jesus Cristo."
    )

    resumo_oracao = linha.get("ORACAO_EUCARISTICA_SUGERIDA") or ""
    if " — " in resumo_oracao:
        nome_oracao, motivo_oracao = resumo_oracao.split(" — ", 1)
    else:
        nome_oracao, motivo_oracao = (resumo_oracao or "Oração Eucarística"), ""

    # O refrão automático do Salmo (Pocket Terço) vem embutido como a
    # primeira linha de SALMO_TEXTO, marcada com "R: " (ver
    # sheets_sync._linha_de — evita precisar de mais uma coluna na
    # planilha).
    salmo_ref = linha.get("SALMO_REF", "")
    salmo_texto_bruto = linha.get("SALMO_TEXTO", "")
    salmo_refrao_auto = ""
    if salmo_texto_bruto.startswith("R:"):
        primeira_linha, _, resto = salmo_texto_bruto.partition("\n\n")
        salmo_refrao_auto = primeira_linha[2:].strip()
    else:
        resto = salmo_texto_bruto

    # BUG REAL encontrado em 21/09/2026 (resincronização de 27/09/2026):
    # o marcador "R:" acima só prova que extrair_salmo_pocketterco()
    # conseguiu isolar o REFRÃO (símbolo '℟.') — não garante que também
    # conseguiu separar as ESTROFES (linhas com '-'). Quando o refrão
    # bate mas a extração das estrofes falha (site sem os '-' naquele
    # dia, mudança de layout etc.), `resto` fica sendo o despejo BRUTO
    # da Nova Aliança/CNBB (fallback dentro do scraper) — com a
    # referência solta no início (às vezes sem os números que viravam
    # sobrescrito no HTML, tipo "Sl 24, bc-5..." em vez de "Sl 24,
    # 4bc-5...") e o refrão REPETIDO dentro do próprio texto corrido.
    # Sem tratar isso, esse lixo ia direto pro PDF (era exatamente o
    # texto duplicado/com a referência quebrada que apareceu de novo).
    # Se `resto` já vier em estrofes limpas (uma por linha, começando
    # com '-' — o formato que o próprio Pocket Terço/scraper produz
    # quando funciona), não mexe; senão, limpa e detecta o refrão pela
    # repetição, do mesmo jeito que já era feito no fallback sem "R:".
    if not re.match(r"^-\s", resto.strip()):
        resto_sem_ref_solta = re.sub(r"(?im)^\s*Sl\.?\s*\d+.*$\n?", "", resto, count=1)
        salmo_limpo = limpar_texto_leitura(resto_sem_ref_solta, salmo_ref, preservar_quebras=True)
        refrao_detectado, estrofes = separar_refrao_estrofes_salmo(salmo_limpo)
        salmo_refrao_auto = salmo_refrao_auto or refrao_detectado
        resto = "\n\n".join(f"- {e}" for e in estrofes)
    salmo_texto_bruto = resto

    # Prefácio (Seção 16): manual (tela dedicada) > sugestão automática
    # do boletim da Diocese de SJC (só domingo, já vem em
    # PREFACIO_NOME/TEXTO) > sugestão automática pela estação litúrgica
    # a partir da pasta do Drive (`sugestao_prefacio`, calculada por
    # quem chama esta função — ver sugerir_e_baixar_prefacio_automatico)
    # > aviso "a critério da escolha pastoral", se nada bateu.
    prefacio_nome = linha.get("PREFACIO_NOME", "")
    prefacio_texto = linha.get("PREFACIO_TEXTO", "")
    fonte_prefacio = "Google Drive — Orações Eucarísticas" if prefacio_nome else ""
    if not prefacio_nome and sugestao_prefacio:
        prefacio_nome = sugestao_prefacio.get("nome", "")
        prefacio_texto = sugestao_prefacio.get("texto", "")
        fonte_prefacio = "Google Drive — Prefácios (sugestão automática pela liturgia)"

    return {
        "data_iso": linha["DATA"],
        "titulo_dia": linha.get("TITULO_DIA", ""),
        "horario_missa": horario,
        "cor_tema": cor_do_tema(linha.get("COR_LITURGICA", "")),
        "antifona_entrada": remover_glifos_invalidos(linha.get("ANTIFONA_ENTRADA", "")),
        "coleta": linha.get("COLETA", ""),
        "leitura1_ref": leitura1_ref,
        "leitura1": {
            "texto_corrido": leitura1_texto,
            "intro": intro_leitura(leitura1_ref),
        },
        "salmo_ref": salmo_ref,
        "salmo_refrao": overrides.get("09_refrao") or salmo_refrao_auto,
        "salmo": {"texto_corrido": salmo_texto_bruto},
        "leitura2_ref": leitura2_ref or None,
        "leitura2": leitura2,
        "aclamacao_refrao": linha.get("ACLAMACAO_REFRAO") or None,
        "aclamacao_versiculo": linha.get("ACLAMACAO_VERSICULO") or None,
        "evangelho_ref": evangelho_ref,
        "evangelho_proclamacao": evangelho_proclamacao,
        "evangelho": {"texto_corrido": evangelho_texto},
        "palavras_abertura": remover_glifos_invalidos(linha.get("PALAVRAS_ABERTURA", "")),
        # Sem isso, uma data sem nenhuma fonte automática (OSM, Pocket
        # Terço nem boletim de SJC) ficava com a Seção 15/18 em branco,
        # sem explicação nenhuma — parecendo um bug ("seção não
        # capturada") em vez do que realmente é (nenhuma fonte tinha
        # essa oração pra esse dia específico). Mesmo padrão já usado
        # no Prefácio ("a critério da escolha pastoral").
        "oferendas_texto": remover_glifos_invalidos(linha.get("OFERENDAS_TEXTO", "")) or (
            "(nenhuma fonte automática encontrou esta oração para esta "
            "data — preencha em 'Completar Oferendas/Comunhão' ou em "
            "'Gerenciar Roteiro', Seção 15)"
        ),
        "comunhao_texto": remover_glifos_invalidos(linha.get("COMUNHAO_TEXTO", "")) or (
            "(nenhuma fonte automática encontrou esta oração para esta "
            "data — preencha em 'Completar Oferendas/Comunhão' ou em "
            "'Gerenciar Roteiro', Seção 18)"
        ),
        "prefacio_nome": prefacio_nome or "a critério da escolha pastoral",
        "prefacio_texto": remover_glifos_invalidos(prefacio_texto),
        "oracao_euc": {
            "nome": nome_oracao,
            "motivo": motivo_oracao,
            "texto": linha.get("ORACAO_EUCARISTICA_TEXTO", ""),
        },
        "fontes": {
            "Fonte das leituras": linha.get("FONTE", ""),
            "Fonte de Oferendas/Comunhão": linha.get("FONTE_OFERENDAS_COMUNHAO", ""),
            "Fonte do Prefácio": fonte_prefacio,
            "URL da fonte principal": linha.get("URL_FONTE", ""),
        },
    }


st.title("⛪ Montesenario")
st.caption("Consulta de leituras e orações da missa do dia")

aba_consulta, aba_admin, aba_gerenciar = st.tabs(
    ["Consultar", "Atualizar base (ADM)", "Gerenciar Roteiro"]
)

with aba_consulta:
    data_escolhida = st.date_input("Data da missa", value=date.today(), format="DD/MM/YYYY")
    horario_escolhido = selecionar_horario(data_escolhida, "consulta_horario")

    dados = carregar_dados()
    roteiro = buscar_por_data_horario(dados, data_escolhida, horario_escolhido)

    if not roteiro:
        st.warning(
            "Ainda não há roteiro gravado para essa data/horário. "
            "Peça a um ADM para atualizar a base na aba ao lado."
        )
    elif roteiro.get("LEITURAS_CONFIRMADAS") == "NÃO":
        st.error(
            "⚠ A fonte automática ainda não publicou esta data — "
            f"{roteiro.get('AVISO_FONTE', '')}"
        )
    else:
        st.subheader(f"{roteiro.get('TITULO_DIA', '')} — {horario_escolhido}")
        if roteiro.get("AVISO_FONTE"):
            st.warning(f"⚠ {roteiro['AVISO_FONTE']}")

        if roteiro.get("ANTIFONA_ENTRADA"):
            with st.expander("Antífona de entrada"):
                st.write(roteiro["ANTIFONA_ENTRADA"])

        if roteiro.get("COLETA"):
            with st.expander("Coleta"):
                st.write(roteiro["COLETA"])

        if roteiro.get("LEITURA1_TEXTO"):
            with st.expander(f"1ª Leitura — {roteiro.get('LEITURA1_REF', '')}", expanded=True):
                st.write(roteiro["LEITURA1_TEXTO"])

        if roteiro.get("SALMO_TEXTO"):
            with st.expander(f"Salmo — {roteiro.get('SALMO_REF', '')}", expanded=True):
                st.write(roteiro["SALMO_TEXTO"])

        if roteiro.get("LEITURA2_TEXTO"):
            with st.expander(f"2ª Leitura — {roteiro.get('LEITURA2_REF', '')}"):
                st.write(roteiro["LEITURA2_TEXTO"])

        if roteiro.get("EVANGELHO_TEXTO"):
            with st.expander(f"Evangelho — {roteiro.get('EVANGELHO_REF', '')}", expanded=True):
                st.write(roteiro["EVANGELHO_TEXTO"])

        if roteiro.get("OFERENDAS_TEXTO"):
            with st.expander("Sobre as Oferendas"):
                st.write(roteiro["OFERENDAS_TEXTO"])
        if roteiro.get("COMUNHAO_TEXTO"):
            with st.expander("Depois da Comunhão"):
                st.write(roteiro["COMUNHAO_TEXTO"])
        if roteiro.get("FONTE_OFERENDAS_COMUNHAO"):
            st.caption(f"Oferendas/Comunhão — fonte: {roteiro['FONTE_OFERENDAS_COMUNHAO']}")

        if roteiro.get("PREFACIO_NOME"):
            st.success(f"Prefácio selecionado: {roteiro['PREFACIO_NOME']}")
            with st.expander("Ver texto do Prefácio"):
                st.write(roteiro.get("PREFACIO_TEXTO", ""))

        if roteiro.get("ORACAO_EUCARISTICA_SUGERIDA"):
            st.info(f"Oração Eucarística sugerida: {roteiro['ORACAO_EUCARISTICA_SUGERIDA']}")
            if roteiro.get("ORACAO_EUCARISTICA_TEXTO"):
                with st.expander("Ver texto completo da Oração Eucarística"):
                    st.write(roteiro["ORACAO_EUCARISTICA_TEXTO"])

        st.caption(
            f"Fonte: {roteiro.get('FONTE', '')} — {roteiro.get('URL_FONTE', '')}"
        )

        st.divider()
        if st.button("📄 Gerar PDF do roteiro completo (20 seções)"):
            with st.spinner("Montando o PDF..."):
                overrides = carregar_overrides_secoes(conectar(), data_escolhida, horario_escolhido)
                sugestao_prefacio = None
                if not roteiro.get("PREFACIO_NOME"):
                    sugestao_prefacio = sugerir_e_baixar_prefacio_automatico(roteiro, data_escolhida)
                dados_pdf = montar_dados_para_pdf(roteiro, horario_escolhido, overrides, sugestao_prefacio)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    montar_pdf(tmp.name, dados_pdf, overrides=overrides)
                    caminho_pdf = tmp.name
            with open(caminho_pdf, "rb") as f:
                st.download_button(
                    "⬇️ Baixar PDF",
                    data=f.read(),
                    file_name=f"roteiro_{data_escolhida.isoformat()}_{horario_escolhido.replace(':', 'h')}.pdf",
                    mime="application/pdf",
                )
            st.caption(
                "Seções 02 (Palavras de Abertura), 11 (Aclamação) e 16 "
                "(Prefácio sugerido) já vêm preenchidas automaticamente "
                "quando a fonte publicou — confira antes de imprimir e "
                "ajuste em 'Gerenciar Roteiro' se precisar de outra "
                "redação."
            )

with aba_admin:
    st.write(
        "Busca no site e grava os dias que ainda não estão na planilha — "
        "cria automaticamente uma linha para CADA horário de missa "
        "cadastrado na aba 'Horarios_Padrao' (ver essa aba na planilha "
        "para configurar/ajustar os horários por tipo de dia)."
    )
    col1, col2 = st.columns(2)
    with col1:
        data_ini = st.date_input("De", value=date.today(), key="ini")
    with col2:
        data_fim = st.date_input("Até", value=date.today() + timedelta(days=6), key="fim")

    forcar_nova_busca = st.checkbox(
        "Forçar nova busca (sobrescreve linhas já confirmadas neste intervalo)",
        key="forcar_nova_busca",
        help=(
            "Por padrão, datas já confirmadas (LEITURAS_CONFIRMADAS = SIM) "
            "são puladas — é o que evita gastar tempo refazendo o que já "
            "está certo. Mas isso também significa que uma linha "
            "confirmada ANTES de uma melhoria no pipeline (ex.: Palavras "
            "de Abertura, Aclamação ou Prefácio automáticos) nunca é "
            "atualizada sozinha. Marque esta opção para reprocessar do "
            "zero as datas do intervalo acima com as fontes mais "
            "recentes, sem precisar apagar a aba inteira."
        ),
    )

    if st.button("Atualizar base agora"):
        with st.spinner("Buscando no site..."):
            resumo = sincronizar_intervalo(
                conectar(),
                data_inicio=data_ini,
                data_fim=data_fim,
                sobrescrever=forcar_nova_busca,
            )
        st.success(
            f"{resumo['novas']} linha(s) nova(s) — "
            f"{resumo['confirmadas_agora']} confirmada(s) agora — "
            f"{resumo['sobrescritas']} sobrescrita(s) — "
            f"{resumo['ainda_pendentes']} ainda pendente(s) (fonte não "
            f"publicada)."
        )
        st.cache_data.clear()

    st.divider()
    st.subheader("Completar Oferendas/Comunhão")
    st.caption(
        "Para dias sem formulário próprio da OSM, cole aqui o texto "
        "copiado do app iLiturgia (a data/horário já precisa ter sido "
        "sincronizada acima)."
    )
    data_completar = st.date_input(
        "Data a completar", value=date.today(), key="data_completar"
    )
    horario_completar = selecionar_horario(data_completar, "completar_horario")
    texto_oferendas = st.text_area("Oração sobre as Oferendas", key="txt_oferendas")
    texto_comunhao = st.text_area("Oração depois da Comunhão", key="txt_comunhao")

    if st.button("Salvar Oferendas/Comunhão"):
        ok = completar_oferendas_comunhao(
            conectar(),
            dia=data_completar,
            horario=horario_completar,
            oferendas_texto=texto_oferendas,
            comunhao_texto=texto_comunhao,
        )
        if ok:
            st.success("Orações salvas para essa data/horário.")
            st.cache_data.clear()
        else:
            st.error(
                "Essa data/horário ainda não está na planilha — "
                "sincronize primeiro em 'Atualizar base agora'."
            )

    st.divider()
    st.subheader("Prefácio antes da Oração Eucarística")
    st.caption(
        "Escolha, entre os prefácios já enviados pra pasta 'Orações "
        "Eucarísticas' no Drive, qual entra no roteiro deste dia/horário."
    )
    data_prefacio = st.date_input(
        "Data do roteiro", value=date.today(), key="data_prefacio"
    )
    horario_prefacio = selecionar_horario(data_prefacio, "prefacio_horario")

    try:
        prefacios_disponiveis = carregar_lista_prefacios()
    except Exception as e:
        prefacios_disponiveis = []
        st.error(f"Não consegui listar os prefácios do Drive: {e}")

    if not prefacios_disponiveis:
        st.info(
            "Nenhum prefácio encontrado na pasta ainda (ou a lista não "
            "carregou) — suba arquivos .txt começando com 'PREFÁCIO' em "
            "002_Liturgia São Peregrino / Orações Eucarísticas."
        )
    else:
        nomes = [p["nome"] for p in prefacios_disponiveis]
        nome_escolhido = st.selectbox("Prefácio", nomes, key="select_prefacio")
        prefacio_escolhido = next(
            p for p in prefacios_disponiveis if p["nome"] == nome_escolhido
        )

        if st.button("Ver prévia"):
            with st.spinner("Baixando do Drive..."):
                texto_previa = baixar_texto_prefacio(
                    conectar_drive_service(), prefacio_escolhido["id"]
                )
            st.text_area("Prévia", texto_previa, height=250, key="previa_prefacio")

        if st.button("Salvar este prefácio no roteiro"):
            with st.spinner("Baixando do Drive e salvando na planilha..."):
                texto_prefacio = baixar_texto_prefacio(
                    conectar_drive_service(), prefacio_escolhido["id"]
                )
                ok = salvar_prefacio_selecionado(
                    conectar(),
                    dia=data_prefacio,
                    horario=horario_prefacio,
                    nome_prefacio=nome_escolhido,
                    texto_prefacio=texto_prefacio,
                )
            if ok:
                st.success(
                    f"'{nome_escolhido}' salvo no roteiro de "
                    f"{data_prefacio.strftime('%d/%m/%Y')} às {horario_prefacio}."
                )
                st.cache_data.clear()
            else:
                st.error(
                    "Essa data/horário ainda não está na planilha — "
                    "sincronize primeiro em 'Atualizar base agora'."
                )

def _construir_previas_por_secao(dados_pdf: dict) -> dict:
    """Prévia do texto EXATO que vai para o PDF em cada seção — depois
    de toda a limpeza automática (números de versículo removidos,
    saudação duplicada do Evangelho cortada, refrão do Salmo isolado,
    caracteres quebrados removidos etc.), não o valor bruto da
    planilha. Mostrar o valor bruto era exatamente o que causava a
    sensação de 'nada foi corrigido' em rodadas anteriores — o operador
    via o texto cru (com numeração, duplicidade etc.) na prévia, mesmo
    quando o PDF gerado já saía limpo."""
    previas = {}
    if dados_pdf.get("palavras_abertura"):
        previas["02"] = dados_pdf["palavras_abertura"]
    if dados_pdf.get("antifona_entrada"):
        previas["03"] = f"Antífona de Entrada:\n{dados_pdf['antifona_entrada']}"
    if dados_pdf.get("coleta"):
        previas["06"] = dados_pdf["coleta"]
    if dados_pdf.get("leitura1", {}).get("texto_corrido"):
        previas["08"] = dados_pdf["leitura1"]["texto_corrido"]
    if dados_pdf.get("salmo_refrao") or dados_pdf.get("salmo", {}).get("texto_corrido"):
        previas["09"] = (
            f"R: {dados_pdf.get('salmo_refrao', '')}\n\n"
            f"{dados_pdf.get('salmo', {}).get('texto_corrido', '')}"
        )
    if dados_pdf.get("leitura2", {}) and dados_pdf["leitura2"].get("texto_corrido"):
        previas["10"] = dados_pdf["leitura2"]["texto_corrido"]
    if dados_pdf.get("aclamacao_refrao") or dados_pdf.get("aclamacao_versiculo"):
        previas["11"] = (
            f"R: {dados_pdf.get('aclamacao_refrao') or 'Aleluia, Aleluia, Aleluia.'}\n"
            f"V: {dados_pdf.get('aclamacao_versiculo') or ''}"
        )
    if dados_pdf.get("evangelho", {}).get("texto_corrido"):
        previas["12"] = (
            f"{dados_pdf.get('evangelho_proclamacao', '')}\n\n"
            f"{dados_pdf['evangelho']['texto_corrido']}"
        )
    if dados_pdf.get("oferendas_texto"):
        previas["15"] = dados_pdf["oferendas_texto"]
    if dados_pdf.get("prefacio_texto"):
        previas["16"] = f"{dados_pdf.get('prefacio_nome', '')}\n\n{dados_pdf['prefacio_texto']}"
    if dados_pdf.get("comunhao_texto"):
        previas["18"] = dados_pdf["comunhao_texto"]
    return previas

with aba_gerenciar:
    st.write(
        "Ajuste o roteiro seção por seção para uma data e horário "
        "específicos. Cada seção mostra (quando existir) o conteúdo "
        "automático já gravado na planilha e uma caixa para você "
        "colar/digitar um texto próprio no lugar dele — só para esta "
        "missa. Deixe a caixa em branco para manter o conteúdo automático "
        "(ou, na seção 02 e na 19, para deixá-la vazia mesmo, como é o "
        "padrão)."
    )
    data_gerenciar = st.date_input(
        "Data da missa a ajustar", value=date.today(), key="data_gerenciar"
    )
    horario_gerenciar = selecionar_horario(data_gerenciar, "gerenciar_horario")

    linha_gerenciar = buscar_por_data_horario(carregar_dados(), data_gerenciar, horario_gerenciar)
    if not linha_gerenciar:
        st.warning(
            "Essa data/horário ainda não está na planilha — sincronize "
            "primeiro na aba 'Atualizar base (ADM)' antes de personalizar "
            "seções."
        )
    else:
        overrides_atuais = carregar_overrides_secoes(conectar(), data_gerenciar, horario_gerenciar)
        chave_widget = f"{data_gerenciar.isoformat()}_{horario_gerenciar}"

        with st.spinner("Calculando prévia do que o sistema capturou para cada seção..."):
            sugestao_prefacio_previa = None
            if not linha_gerenciar.get("PREFACIO_NOME"):
                sugestao_prefacio_previa = sugerir_e_baixar_prefacio_automatico(
                    linha_gerenciar, data_gerenciar
                )
            dados_previa = montar_dados_para_pdf(
                linha_gerenciar, horario_gerenciar, overrides_atuais, sugestao_prefacio_previa
            )
        previas_por_secao = _construir_previas_por_secao(dados_previa)

        for secao in SECOES:
            numero, nome = secao["numero"], secao["nome"]
            personalizada = bool(overrides_atuais.get(numero))
            titulo_expander = f"{numero} — {nome}" + (" ✏️ personalizada" if personalizada else "")

            with st.expander(titulo_expander):
                if secao.get("e_prefacio"):
                    st.info(
                        "O Prefácio tem tela própria, ligada ao Google Drive — "
                        "veja 'Prefácio antes da Oração Eucarística' na aba "
                        "'Atualizar base (ADM)'. Prefácio já selecionado: "
                        f"**{linha_gerenciar.get('PREFACIO_NOME') or '(nenhum ainda)'}**. "
                        "Oração Eucarística sugerida: "
                        f"**{linha_gerenciar.get('ORACAO_EUCARISTICA_SUGERIDA') or '(não calculada)'}**.\n\n"
                        "Se quiser, pode colar abaixo um texto livre que "
                        "substitui TODO o bloco (Prefácio + Oração "
                        "Eucarística) no roteiro final."
                    )
                else:
                    conteudo_auto = previas_por_secao.get(numero, "")
                    if conteudo_auto:
                        st.caption(
                            "Conteúdo automático atual — exatamente como vai para o "
                            "PDF (já limpo/formatado), se você não personalizar:"
                        )
                        st.text_area(
                            "Prévia (somente leitura)",
                            value=conteudo_auto,
                            height=180,
                            disabled=True,
                            key=f"previa_{numero}_{chave_widget}",
                            label_visibility="collapsed",
                        )
                    elif numero in ("01", "04", "05", "07", "13", "14", "17", "20"):
                        st.caption(
                            "Esta seção usa texto fixo do Ordinário da Missa "
                            "(diálogos padrão) — personalize aqui só se quiser "
                            "trocar a redação para esta missa específica."
                        )
                    elif numero == "02":
                        st.caption("Em branco por padrão — escreva aqui as palavras de abertura desta missa.")
                    elif numero == "19":
                        st.caption("Em branco por padrão — cole aqui novenas/reflexões específicas desta data, se houver.")

                texto_override = st.text_area(
                    "Texto personalizado para esta seção (deixe em branco para usar o padrão)",
                    value=overrides_atuais.get(numero, ""),
                    height=140,
                    key=f"override_{numero}_{chave_widget}",
                )

                if st.button("Salvar esta seção", key=f"salvar_secao_{numero}_{chave_widget}"):
                    ok = salvar_override_secao(
                        conectar(), data_gerenciar, horario_gerenciar, numero, texto_override
                    )
                    if ok:
                        st.success(
                            f"Seção {numero} salva para "
                            f"{data_gerenciar.strftime('%d/%m/%Y')} às {horario_gerenciar}."
                        )
                        st.cache_data.clear()
                    else:
                        st.error("Não foi possível salvar — verifique se a data/horário já está sincronizado.")
