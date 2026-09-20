# -*- coding: utf-8 -*-
"""
sheets_sync.py — Monte Senário

Grava/atualiza os dados extraídos pelo scraper.py numa planilha do
Google Sheets, usando uma Service Account (mesmo padrão já usado no
projeto Leitores Peregrinos).

Estrutura da aba "Liturgia_Diaria" (linha 1 = cabeçalho, ver CABECALHO
abaixo). As colunas OFERENDAS_TEXTO / COMUNHAO_TEXTO / ORACAO_EUCARISTICA
_SUGERIDA cobrem o que novaalianca.com.br não publica:
  - Se a data cair no Próprio dos Santos da OSM (osm_proprio.py), são
    preenchidas automaticamente a partir do PDF público da Ordem.
  - Caso contrário, ficam em branco até alguém completar manualmente
    (ex.: copiando do app iLiturgia) pela tela "Completar Oferendas/
    Comunhão" do app.py.
A Oração Eucarística sugerida segue a regra do n. 365 da IGMR.

Requisitos:
    pip install gspread google-auth pdfplumber requests
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import date, timedelta
from typing import Optional

import gspread
from gspread.utils import rowcol_to_a1
import requests
from google.oauth2.service_account import Credentials

from scraper import LiturgiaDoDia, extrair_intervalo, extrair_oferendas_comunhao_pocketterco
from osm_proprio import buscar_formulario_osm
from oracoes_eucaristicas import obter_oracao
from secoes_roteiro import NUMEROS_VALIDOS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ABA = "Liturgia_Diaria"
CABECALHO = [
    "DATA", "HORARIO", "TITULO_DIA", "FONTE", "ANTIFONA_ENTRADA", "COLETA",
    "LEITURA1_REF", "LEITURA1_TEXTO",
    "SALMO_REF", "SALMO_TEXTO",
    "LEITURA2_REF", "LEITURA2_TEXTO",
    "EVANGELHO_REF", "EVANGELHO_TEXTO",
    "OFERENDAS_TEXTO", "COMUNHAO_TEXTO", "FONTE_OFERENDAS_COMUNHAO",
    "ORACAO_EUCARISTICA_SUGERIDA", "ORACAO_EUCARISTICA_TEXTO",
    "PREFACIO_NOME", "PREFACIO_TEXTO",
    "LEITURAS_CONFIRMADAS", "AVISO_FONTE",
    "URL_FONTE",
    "SECOES_OVERRIDE",
]

# Aba auxiliar "Horarios_Padrao" (TIPO_DIA | HORARIO) — define quais
# horários de missa existem para cada tipo de dia (mesmo padrão já usado
# no projeto Leitores Peregrinos). Tipos esperados:
#   DOMINGO, SABADO, DIA_SEMANA, DIA4_SEMANA, DIA4_FDS
# (DIA4_* cobre o dia 4 do mês — Missa da Saúde — que tem horários
# próprios diferentes do resto da semana/fim de semana).
ABA_HORARIOS = "Horarios_Padrao"
CABECALHO_HORARIOS = ["TIPO_DIA", "HORARIO"]

# Usado quando uma data cai num tipo de dia sem nenhum horário cadastrado
# ainda na aba Horarios_Padrao — evita que a data simplesmente suma da
# sincronização por falta de configuração.
HORARIO_PADRAO_FALLBACK = "19:00"

# Índices de coluna (1-based, como o gspread espera) para atualização pontual
COL_DATA = 1
COL_HORARIO = CABECALHO.index("HORARIO") + 1
COL_OFERENDAS_TEXTO = CABECALHO.index("OFERENDAS_TEXTO") + 1
COL_COMUNHAO_TEXTO = CABECALHO.index("COMUNHAO_TEXTO") + 1
COL_FONTE_OFERENDAS_COMUNHAO = CABECALHO.index("FONTE_OFERENDAS_COMUNHAO") + 1
COL_PREFACIO_NOME = CABECALHO.index("PREFACIO_NOME") + 1
COL_PREFACIO_TEXTO = CABECALHO.index("PREFACIO_TEXTO") + 1
COL_SECOES_OVERRIDE = CABECALHO.index("SECOES_OVERRIDE") + 1


def _abrir_aba(cliente: gspread.Client, id_planilha: str) -> gspread.Worksheet:
    planilha = cliente.open_by_key(id_planilha)
    try:
        aba = planilha.worksheet(ABA)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA, rows=1000, cols=len(CABECALHO))
        aba.append_row(CABECALHO)
    return aba


def _abrir_aba_horarios(aba_liturgia: gspread.Worksheet) -> gspread.Worksheet:
    """Reaproveita a mesma planilha já aberta (aba_liturgia.spreadsheet)
    para abrir/criar a aba Horarios_Padrao, sem precisar de uma nova
    autenticação."""
    planilha = aba_liturgia.spreadsheet
    try:
        return planilha.worksheet(ABA_HORARIOS)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=ABA_HORARIOS, rows=100, cols=len(CABECALHO_HORARIOS))
        aba.append_row(CABECALHO_HORARIOS)
        return aba


def obter_horarios_padrao(aba_liturgia: gspread.Worksheet) -> dict[str, list[str]]:
    """Lê a aba Horarios_Padrao e agrupa os horários cadastrados por tipo
    de dia. Retorna {} (sem quebrar nada) se a aba estiver vazia ou algo
    der errado na leitura."""
    try:
        aba_h = _abrir_aba_horarios(aba_liturgia)
        dados = aba_h.get_all_records()
    except Exception:
        return {}
    horarios_por_tipo: dict[str, list[str]] = {}
    for r in dados:
        tipo = str(r.get("TIPO_DIA", "")).strip().upper()
        horario = str(r.get("HORARIO", "")).strip()
        if tipo and horario:
            horarios_por_tipo.setdefault(tipo, []).append(horario)
    for tipo in horarios_por_tipo:
        horarios_por_tipo[tipo] = sorted(set(horarios_por_tipo[tipo]))
    return horarios_por_tipo


def tipo_dia_de(dia: date) -> str:
    """DOMINGO / SABADO / DIA_SEMANA, com os casos especiais do dia 4 do
    mês (Missa da Saúde): DIA4_SEMANA (dia 4 cai de segunda a sexta) ou
    DIA4_FDS (dia 4 cai em sábado ou domingo)."""
    dia_semana = dia.weekday()  # segunda=0 ... domingo=6
    eh_fds = dia_semana in (5, 6)
    if dia.day == 4:
        return "DIA4_FDS" if eh_fds else "DIA4_SEMANA"
    if dia_semana == 6:
        return "DOMINGO"
    if dia_semana == 5:
        return "SABADO"
    return "DIA_SEMANA"


def horarios_para_data(dia: date, horarios_por_tipo: dict[str, list[str]]) -> list[str]:
    """Lista (ordenada) dos horários de missa cadastrados para essa data.
    Devolve [] se o tipo de dia correspondente não tiver nada cadastrado
    ainda na aba Horarios_Padrao — quem chamar decide o fallback."""
    tipo = tipo_dia_de(dia)
    return horarios_por_tipo.get(tipo, [])


def conectar_planilha_com_arquivo(caminho_credenciais: str, id_planilha: str) -> gspread.Worksheet:
    """Autentica usando um arquivo JSON de Service Account (uso em script/CLI)."""
    creds = Credentials.from_service_account_file(caminho_credenciais, scopes=SCOPES)
    cliente = gspread.authorize(creds)
    return _abrir_aba(cliente, id_planilha)


def conectar_planilha_com_info(info_credenciais: dict, id_planilha: str) -> gspread.Worksheet:
    """Autentica usando um dict de credenciais (uso no Streamlit, via st.secrets)."""
    creds = Credentials.from_service_account_info(info_credenciais, scopes=SCOPES)
    cliente = gspread.authorize(creds)
    return _abrir_aba(cliente, id_planilha)


# --- Oração Eucarística sugerida (IGMR n. 365) -----------------------------

def sugerir_oracao_eucaristica(titulo_dia: str, tem_prefacio_proprio: bool = False) -> str:
    """Sugestão simples com base no n. 365 da IGMR. É um ponto de partida
    pastoral, não uma regra rígida — o celebrante sempre pode escolher outra."""
    titulo = (titulo_dia or "").lower()
    if "domingo" in titulo:
        if not tem_prefacio_proprio:
            return "IV"
        return "III"
    if "solenidade" in titulo or "festa" in titulo:
        return "I"
    return "II"


def sugerir_oracao_eucaristica_completa(titulo_dia: str, tem_prefacio_proprio: bool = False) -> dict:
    """Como sugerir_oracao_eucaristica(), mas já retorna o texto integral
    junto com o motivo da escolha, pronto para ir no roteiro. Desde que
    a IV foi encontrada (pocketterco.com.br), as quatro orações do n.
    365 da IGMR têm texto completo — não há mais lacuna aqui."""
    numeral = sugerir_oracao_eucaristica(titulo_dia, tem_prefacio_proprio)
    dados = obter_oracao(numeral)
    if dados:
        return {
            "numeral": numeral,
            "nome": dados["nome"],
            "motivo": dados["quando_usar"],
            "texto": dados["texto"],
        }
    # Só cai aqui se obter_oracao() não reconhecer o numeral (não deveria
    # acontecer com I-IV, mas evita quebrar o roteiro em vez de travar).
    return {
        "numeral": numeral,
        "nome": f"Oração Eucarística {numeral}",
        "motivo": f"numeral '{numeral}' não encontrado em oracoes_eucaristicas.py",
        "texto": "",
    }


# --- Preenchimento automático a partir do Próprio da OSM --------------------

_HEADERS_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; LiturgiaPeregrina/1.0)"}
_RUIDO_RODAPE = re.compile(
    r"Copyright ©\s*CURIA GENERALIZIA OSM,?\s*Piazza San Marcello,?\s*5\s*[–-]\s*Roma",
    re.IGNORECASE,
)


def _limpar_ruido(texto: str) -> str:
    """Remove o rodapé de copyright que o PDF repete em toda página,
    e normaliza espaços em branco excedentes."""
    texto = _RUIDO_RODAPE.sub("", texto)
    return re.sub(r"\n{2,}", "\n", texto).strip()


def _preferir_variante_fora_da_basilica(texto: str) -> str:
    """Algumas celebrações (ex.: dedicação de um templo) trazem duas
    versões — '[Na basílica ...]' e '[Fora da basílica ...]'. Como o uso
    típico numa paróquia comum é fora da basílica de referência, essa é
    a variante preferida quando ambas aparecem; a versão completa (com
    as duas) fica disponível separadamente para quem precisar da outra."""
    m = re.search(r"\[Fora da basílica[^\]]*\]:?", texto, flags=re.IGNORECASE)
    if m:
        return texto[m.end():].strip()
    return texto


def _extrair_secao(texto: str, inicio_regex: str, fim_regexes: list[str]) -> str:
    m_inicio = re.search(inicio_regex, texto, flags=re.IGNORECASE)
    if not m_inicio:
        return ""
    resto = texto[m_inicio.end():]
    fim = len(resto)
    for padrao in fim_regexes:
        m_fim = re.search(padrao, resto, flags=re.IGNORECASE)
        if m_fim:
            fim = min(fim, m_fim.start())
    return resto[:fim].strip()


def buscar_oferendas_comunhao_osm(dia: date) -> Optional[dict]:
    """Se a data tiver formulário próprio da OSM, baixa o PDF e extrai
    'Sobre as oferendas' e 'Depois da comunhão'. Retorna None se a data
    não tiver formulário próprio."""
    encontrado = buscar_formulario_osm(dia)
    if not encontrado:
        return None
    nome_celebracao, url_pdf = encontrado

    import pdfplumber
    from io import BytesIO

    resp = requests.get(url_pdf, headers=_HEADERS_HTTP, timeout=20)
    resp.raise_for_status()

    texto_completo = ""
    with pdfplumber.open(BytesIO(resp.content)) as pdf:
        for pagina in pdf.pages:
            texto_completo += (pagina.extract_text() or "") + "\n"

    oferendas = _extrair_secao(
        texto_completo, r"Sobre as oferendas",
        [r"Prefácio", r"Antífona da comunhão"],
    )
    comunhao = _extrair_secao(
        texto_completo, r"Depois da comunhão",
        [r"Bênção solene", r"Oração sobre o povo"],
    )

    return {
        "celebracao": nome_celebracao,
        "url_pdf": url_pdf,
        "oferendas_texto": _preferir_variante_fora_da_basilica(_limpar_ruido(oferendas)),
        "oferendas_texto_completo": _limpar_ruido(oferendas),
        "comunhao_texto": _preferir_variante_fora_da_basilica(_limpar_ruido(comunhao)),
        "comunhao_texto_completo": _limpar_ruido(comunhao),
    }


# --- Escrita na planilha ------------------------------------------------

def _linha_de(item: LiturgiaDoDia, horario: str) -> list[str]:
    d = asdict(item)
    dia = date.fromisoformat(d["data"])

    if not d["leituras_confirmadas"]:
        # Página ainda não publicada pela fonte — grava o aviso e deixa
        # o resto em branco, em vez de inventar conteúdo ou sumir com o dia.
        return [
            d["data"], horario, d["titulo_dia"], "", "", "",
            "", "", "", "", "", "", "", "",
            "", "", "",
            "não aplicável (fonte não confirmada)", "",
            "", "",
            "NÃO", d["aviso_fonte"],
            d["url_fonte"],
            "{}",
        ]

    oferendas_texto, comunhao_texto, fonte_extra = "", "", ""
    dados_osm = buscar_oferendas_comunhao_osm(dia)
    if dados_osm:
        oferendas_texto = dados_osm["oferendas_texto"]
        comunhao_texto = dados_osm["comunhao_texto"]
        fonte_extra = f"OSM — {dados_osm['celebracao']} ({dados_osm['url_pdf']})"
    else:
        # OSM só cobre datas fixas da Ordem; para o resto do ano, o
        # Pocket Terço é a fonte dessas duas orações (decisão do usuário:
        # só para Oferendas/Comunhão, o resto do pipeline não muda).
        dados_pocketterco = extrair_oferendas_comunhao_pocketterco(dia)
        if dados_pocketterco:
            oferendas_texto = dados_pocketterco["oferendas"]
            comunhao_texto = dados_pocketterco["comunhao"]
            fonte_extra = f"Pocket Terço ({dados_pocketterco['url']})"

    oracao_euc = sugerir_oracao_eucaristica_completa(d["titulo_dia"])
    oracao_euc_resumo = f"{oracao_euc['nome']} — {oracao_euc['motivo']}"

    fonte_combinada = d["fonte_leituras"]
    if d["fonte_propers"]:
        fonte_combinada += f" (leituras) + {d['fonte_propers']} (antífona/coleta)"

    return [
        d["data"], horario, d["titulo_dia"], fonte_combinada, d["antifona_entrada"], d["coleta"],
        d["leitura1_ref"], d["leitura1_texto"],
        d["salmo_ref"], d["salmo_texto"],
        d["leitura2_ref"], d["leitura2_texto"],
        d["evangelho_ref"], d["evangelho_texto"],
        oferendas_texto, comunhao_texto, fonte_extra,
        oracao_euc_resumo, oracao_euc["texto"],
        "", "",
        "SIM", d["aviso_fonte"],
        d["url_fonte"],
        "{}",
    ]


def chaves_ja_gravadas(aba: gspread.Worksheet) -> set[tuple[str, str]]:
    """Pares (data, horário) cujas leituras já foram confirmadas pela
    fonte — esses são pulados em sincronizações futuras."""
    valores = aba.get_all_values()
    if not valores:
        return set()
    cabecalho = valores[0]
    idx_data = cabecalho.index("DATA")
    idx_horario = cabecalho.index("HORARIO")
    idx_confirmadas = cabecalho.index("LEITURAS_CONFIRMADAS")
    return {
        (linha[idx_data], linha[idx_horario])
        for linha in valores[1:]
        if len(linha) > idx_confirmadas and linha[idx_confirmadas] == "SIM"
    }


def chaves_pendentes(aba: gspread.Worksheet) -> dict[tuple[str, str], int]:
    """Pares (data, horário) já gravados mas ainda sem confirmação (fonte
    não publicada na última tentativa) — mapeia (data, horário) -> número
    da linha na planilha, para serem sobrescritos assim que a fonte
    publicar."""
    valores = aba.get_all_values()
    if not valores:
        return {}
    cabecalho = valores[0]
    idx_data = cabecalho.index("DATA")
    idx_horario = cabecalho.index("HORARIO")
    idx_confirmadas = cabecalho.index("LEITURAS_CONFIRMADAS")
    pendentes = {}
    for i, linha in enumerate(valores[1:], start=2):  # linha 1 = cabeçalho
        if len(linha) > idx_confirmadas and linha[idx_confirmadas] == "NÃO":
            pendentes[(linha[idx_data], linha[idx_horario])] = i
    return pendentes


def sincronizar_intervalo(
    aba: gspread.Worksheet,
    data_inicio: date,
    data_fim: date,
    sobrescrever: bool = False,
) -> dict:
    """Extrai o intervalo de datas do site e grava na planilha (recebe a
    aba já autenticada — ver conectar_planilha_com_arquivo/_com_info).

    Para cada data, cria uma linha PARA CADA horário de missa cadastrado
    na aba Horarios_Padrao (ver obter_horarios_padrao/horarios_para_data)
    — assim domingos com 10h e 19h, ou o dia 4 com seus 2-3 horários,
    ganham roteiros independentes, editáveis separadamente em "Gerenciar
    Roteiro". Se o tipo de dia não tiver nenhum horário cadastrado ainda,
    usa HORARIO_PADRAO_FALLBACK para não perder a data.

    Datas/horários com LEITURAS_CONFIRMADAS=SIM são pulados (já
    resolvidos). Pendentes (fonte não publicada numa tentativa anterior)
    são RETENTADOS: se a fonte já publicou, a linha existente é
    atualizada no lugar; se continuar sem publicar, a linha pendente não
    é duplicada. Combinações novas são adicionadas normalmente,
    confirmadas ou não.

    Retorna um resumo: {"novas": N, "confirmadas_agora": N, "ainda_pendentes": N}.
    """
    horarios_por_tipo = obter_horarios_padrao(aba)
    chaves_gravadas = set() if sobrescrever else chaves_ja_gravadas(aba)
    pendentes = {} if sobrescrever else chaves_pendentes(aba)

    novas_linhas = []
    resumo = {"novas": 0, "confirmadas_agora": 0, "ainda_pendentes": 0}

    for item in extrair_intervalo(data_inicio, data_fim):
        dia = date.fromisoformat(item.data)
        horarios = horarios_para_data(dia, horarios_por_tipo) or [HORARIO_PADRAO_FALLBACK]

        for horario in horarios:
            chave = (item.data, horario)
            if chave in chaves_gravadas:
                continue

            linha = _linha_de(item, horario)

            if chave in pendentes:
                if item.leituras_confirmadas:
                    num_linha = pendentes[chave]
                    ultima_coluna = rowcol_to_a1(num_linha, len(CABECALHO))
                    primeira_coluna = rowcol_to_a1(num_linha, 1)
                    aba.update(
                        f"{primeira_coluna}:{ultima_coluna}",
                        [linha], value_input_option="USER_ENTERED",
                    )
                    resumo["confirmadas_agora"] += 1
                else:
                    resumo["ainda_pendentes"] += 1
                continue

            novas_linhas.append(linha)
            resumo["novas"] += 1

    if novas_linhas:
        aba.append_rows(novas_linhas, value_input_option="USER_ENTERED")

    return resumo


def completar_oferendas_comunhao(
    aba: gspread.Worksheet,
    dia: date,
    horario: str,
    oferendas_texto: str,
    comunhao_texto: str,
    fonte: str = "iLiturgia (colado manualmente)",
) -> bool:
    """Atualiza, numa linha já existente (dessa data E horário), os campos
    de Oferendas/Comunhão — uso típico: colar o texto copiado do app
    iLiturgia. Retorna False se a combinação ainda não tiver linha na
    planilha (rode a sincronização normal primeiro)."""
    linha = _linha_da_data_horario(aba, dia, horario)
    if linha is None:
        return False

    aba.update_cell(linha, COL_OFERENDAS_TEXTO, oferendas_texto)
    aba.update_cell(linha, COL_COMUNHAO_TEXTO, comunhao_texto)
    aba.update_cell(linha, COL_FONTE_OFERENDAS_COMUNHAO, fonte)
    return True


def salvar_prefacio_selecionado(
    aba: gspread.Worksheet,
    dia: date,
    horario: str,
    nome_prefacio: str,
    texto_prefacio: str,
) -> bool:
    """Grava, numa linha já existente (dessa data E horário), qual
    Prefácio foi escolhido pra entrar antes da Oração Eucarística no
    roteiro — uso típico: seleção feita na tela do app a partir dos
    arquivos da pasta Orações Eucarísticas no Drive (ver
    prefacios_drive.py). Retorna False se a combinação ainda não tiver
    linha na planilha."""
    linha = _linha_da_data_horario(aba, dia, horario)
    if linha is None:
        return False

    aba.update_cell(linha, COL_PREFACIO_NOME, nome_prefacio)
    aba.update_cell(linha, COL_PREFACIO_TEXTO, texto_prefacio)
    return True


# --- Gestão do roteiro por seção (interface do operador) -------------------
#
# Cada linha guarda, na coluna SECOES_OVERRIDE, um JSON {"02": "texto...",
# "19": "texto..."} com o conteúdo que o operador digitou/colou para
# substituir o que o pipeline geraria automaticamente para aquela seção
# (ver secoes_roteiro.py para a lista de seções válidas). Uma seção sem
# chave no dicionário usa o conteúdo automático normalmente — isto é um
# mecanismo de EXCEÇÃO pontual, não uma reescrita do roteiro inteiro.

def _linha_da_data_horario(aba: gspread.Worksheet, dia: date, horario: str) -> Optional[int]:
    """Número da linha (1-based) cuja DATA e HORARIO batem com os
    informados, ou None se essa combinação ainda não existir na
    planilha."""
    valores = aba.get_all_values()
    if not valores:
        return None
    cabecalho = valores[0]
    idx_data = cabecalho.index("DATA")
    idx_horario = cabecalho.index("HORARIO")
    alvo_data = dia.isoformat()
    for i, linha in enumerate(valores[1:], start=2):
        if (
            len(linha) > idx_horario
            and linha[idx_data] == alvo_data
            and linha[idx_horario] == horario
        ):
            return i
    return None


def carregar_overrides_secoes(aba: gspread.Worksheet, dia: date, horario: str) -> dict[str, str]:
    """Lê o dicionário de overrides por seção salvo para essa data+horário.
    Retorna {} se a combinação não tiver linha ainda, se a coluna estiver
    vazia, ou se o JSON estiver corrompido (nunca derruba a tela por isso)."""
    linha = _linha_da_data_horario(aba, dia, horario)
    if linha is None:
        return {}
    valores = aba.row_values(linha)
    if len(valores) < COL_SECOES_OVERRIDE:
        return {}
    bruto = valores[COL_SECOES_OVERRIDE - 1].strip()
    if not bruto:
        return {}
    try:
        dados = json.loads(bruto)
        return dados if isinstance(dados, dict) else {}
    except json.JSONDecodeError:
        return {}


def salvar_override_secao(
    aba: gspread.Worksheet, dia: date, horario: str, numero_secao: str, texto: str
) -> bool:
    """Grava (ou remove, se texto vazio) o override de UMA seção para essa
    data+horário, sem afetar as demais seções já salvas. Retorna False se
    a combinação ainda não tiver linha na planilha ou se numero_secao não
    for uma das seções válidas (ver secoes_roteiro.SECOES)."""
    if numero_secao not in NUMEROS_VALIDOS:
        return False
    linha = _linha_da_data_horario(aba, dia, horario)
    if linha is None:
        return False

    overrides = carregar_overrides_secoes(aba, dia, horario)
    texto = (texto or "").strip()
    if texto:
        overrides[numero_secao] = texto
    else:
        overrides.pop(numero_secao, None)

    aba.update_cell(linha, COL_SECOES_OVERRIDE, json.dumps(overrides, ensure_ascii=False))
    return True


if __name__ == "__main__":
    # Exemplo de uso — ajuste caminho das credenciais e ID da planilha
    CAMINHO_CREDENCIAIS = "credenciais_service_account.json"
    ID_PLANILHA = "COLOQUE_AQUI_O_ID_DA_PLANILHA"

    hoje = date.today()
    aba = conectar_planilha_com_arquivo(CAMINHO_CREDENCIAIS, ID_PLANILHA)
    resumo = sincronizar_intervalo(
        aba,
        data_inicio=hoje,
        data_fim=hoje + timedelta(days=6),  # sincroniza a semana atual
    )
    print(
        f"{resumo['novas']} dia(s) novo(s), "
        f"{resumo['confirmadas_agora']} confirmado(s) nesta passada, "
        f"{resumo['ainda_pendentes']} ainda pendente(s) (fonte não publicada)."
    )
