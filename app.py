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
from prefacios_drive import conectar_drive, listar_prefacios, baixar_texto_prefacio
from secoes_roteiro import SECOES
from roteiro_completo import montar_pdf
from roteiro_render import cor_do_tema

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


def montar_dados_para_pdf(linha: dict, horario: str, overrides: dict) -> dict:
    """Converte uma linha da planilha (dict de sheets_sync) no formato de
    dados esperado por roteiro_completo.montar_pdf(). Alguns detalhes
    finos ainda não são capturados automaticamente pelo scraper geral —
    aclamação ao Evangelho com versículo específico, o nome do
    evangelista na 'Proclamação do Evangelho...', e o refrão isolado do
    Salmo — e usam um valor padrão razoável aqui. Se precisar do texto
    exato, o operador pode colar em 'Gerenciar Roteiro' (seções 09, 11 e
    12), que sempre tem prioridade sobre esses padrões."""
    leitura2 = None
    if linha.get("LEITURA2_TEXTO"):
        leitura2 = {"texto_corrido": linha.get("LEITURA2_TEXTO", "")}

    resumo_oracao = linha.get("ORACAO_EUCARISTICA_SUGERIDA") or ""
    if " — " in resumo_oracao:
        nome_oracao, motivo_oracao = resumo_oracao.split(" — ", 1)
    else:
        nome_oracao, motivo_oracao = (resumo_oracao or "Oração Eucarística"), ""

    return {
        "data_iso": linha["DATA"],
        "titulo_dia": linha.get("TITULO_DIA", ""),
        "horario_missa": horario,
        "cor_tema": cor_do_tema(linha.get("COR_LITURGICA", "")),
        "antifona_entrada": linha.get("ANTIFONA_ENTRADA", ""),
        "coleta": linha.get("COLETA", ""),
        "leitura1_ref": linha.get("LEITURA1_REF", ""),
        "leitura1": {"texto_corrido": linha.get("LEITURA1_TEXTO", "")},
        "salmo_ref": linha.get("SALMO_REF", ""),
        "salmo_refrao": overrides.get("09_refrao", ""),
        "salmo": {"texto_corrido": linha.get("SALMO_TEXTO", "")},
        "leitura2_ref": linha.get("LEITURA2_REF") or None,
        "leitura2": leitura2,
        "aclamacao_refrao": None,
        "aclamacao_versiculo": None,
        "evangelho_ref": linha.get("EVANGELHO_REF", ""),
        "evangelho_proclamacao": "Proclamação do Evangelho de Jesus Cristo",
        "evangelho": {"texto_corrido": linha.get("EVANGELHO_TEXTO", "")},
        "palavras_abertura": linha.get("PALAVRAS_ABERTURA", ""),
        "oferendas_texto": linha.get("OFERENDAS_TEXTO", ""),
        "comunhao_texto": linha.get("COMUNHAO_TEXTO", ""),
        "prefacio_nome": linha.get("PREFACIO_NOME", "") or "(nenhum selecionado ainda)",
        "prefacio_texto": linha.get("PREFACIO_TEXTO", ""),
        "oracao_euc": {
            "nome": nome_oracao,
            "motivo": motivo_oracao,
            "texto": linha.get("ORACAO_EUCARISTICA_TEXTO", ""),
        },
        "fontes": {
            "Fonte das leituras": linha.get("FONTE", ""),
            "Fonte de Oferendas/Comunhão": linha.get("FONTE_OFERENDAS_COMUNHAO", ""),
            "Fonte do Prefácio": "Google Drive — Orações Eucarísticas" if linha.get("PREFACIO_NOME") else "",
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
                dados_pdf = montar_dados_para_pdf(roteiro, horario_escolhido, overrides)
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
                "Confira a Aclamação ao Evangelho (seção 11) antes de "
                "imprimir — ainda não vem preenchida automaticamente. Aos "
                "domingos, a seção 02 (Palavras de Abertura) já vem "
                "preenchida a partir do Semanário da Diocese de SJC; em "
                "dia de semana, ou se ainda não vier, ajuste em "
                "'Gerenciar Roteiro'."
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

    if st.button("Atualizar base agora"):
        with st.spinner("Buscando no site..."):
            resumo = sincronizar_intervalo(
                conectar(),
                data_inicio=data_ini,
                data_fim=data_fim,
            )
        st.success(
            f"{resumo['novas']} linha(s) nova(s) — "
            f"{resumo['confirmadas_agora']} confirmada(s) agora — "
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

# Para as seções que já têm conteúdo automático gravado na planilha, mostra
# uma prévia dele acima da caixa de override — assim o operador vê o que
# vai acontecer se deixar a seção sem personalização.
_COLUNA_AUTO_POR_SECAO = {
    "02": "PALAVRAS_ABERTURA",
    "06": "COLETA",
    "08": "LEITURA1_TEXTO",
    "09": "SALMO_TEXTO",
    "10": "LEITURA2_TEXTO",
    "12": "EVANGELHO_TEXTO",
    "15": "OFERENDAS_TEXTO",
    "18": "COMUNHAO_TEXTO",
}

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
                    coluna_auto = _COLUNA_AUTO_POR_SECAO.get(numero)
                    conteudo_auto = (linha_gerenciar.get(coluna_auto) or "") if coluna_auto else ""
                    if conteudo_auto:
                        st.caption("Conteúdo automático atual (o que entra no roteiro se você não personalizar):")
                        st.text(conteudo_auto[:500] + ("…" if len(conteudo_auto) > 500 else ""))
                    elif numero in ("01", "03", "04", "05", "07", "11", "13", "14", "17", "20"):
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
