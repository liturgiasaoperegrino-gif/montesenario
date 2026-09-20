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
    "DATA", "TITULO_DIA", "FONTE", "ANTIFONA_ENTRADA", "COLETA",
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

# Índices de coluna (1-based, como o gspread espera) para atualização pontual
COL_DATA = 1
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

def _linha_de(item: LiturgiaDoDia) -> list[str]:
    d = asdict(item)
    dia = date.fromisoformat(d["data"])

    if not d["leituras_confirmadas"]:
        # Página ainda não publicada pela fonte — grava o aviso e deixa
        # o resto em branco, em vez de inventar conteúdo ou sumir com o dia.
        return [
            d["data"], d["titulo_dia"], "", "", "",
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
        d["data"], d["titulo_dia"], fonte_combinada, d["antifona_entrada"], d["coleta"],
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


def datas_ja_gravadas(aba: gspread.Worksheet) -> set[str]:
    """Datas cujas leituras já foram confirmadas pela fonte — essas são
    puladas em sincronizações futuras."""
    valores = aba.get_all_values()
    if not valores:
        return set()
    cabecalho = valores[0]
    idx_data = cabecalho.index("DATA")
    idx_confirmadas = cabecalho.index("LEITURAS_CONFIRMADAS")
    return {
        linha[idx_data]
        for linha in valores[1:]
        if len(linha) > idx_confirmadas and linha[idx_confirmadas] == "SIM"
    }


def datas_pendentes(aba: gspread.Worksheet) -> dict[str, int]:
    """Datas já gravadas mas ainda sem confirmação (fonte não publicada
    na última tentativa) — mapeia data -> número da linha na planilha,
    para serem sobrescritas assim que a fonte publicar."""
    valores = aba.get_all_values()
    if not valores:
        return {}
    cabecalho = valores[0]
    idx_data = cabecalho.index("DATA")
    idx_confirmadas = cabecalho.index("LEITURAS_CONFIRMADAS")
    pendentes = {}
    for i, linha in enumerate(valores[1:], start=2):  # linha 1 = cabeçalho
        if len(linha) > idx_confirmadas and linha[idx_confirmadas] == "NÃO":
            pendentes[linha[idx_data]] = i
    return pendentes


def sincronizar_intervalo(
    aba: gspread.Worksheet,
    data_inicio: date,
    data_fim: date,
    sobrescrever: bool = False,
) -> dict:
    """Extrai o intervalo de datas do site e grava na planilha (recebe a
    aba já autenticada — ver conectar_planilha_com_arquivo/_com_info).

    Datas com LEITURAS_CONFIRMADAS=SIM são puladas (já resolvidas).
    Datas pendentes (fonte não publicada numa tentativa anterior) são
    RETENTADAS: se a fonte já publicou, a linha existente é atualizada
    no lugar; se continuar sem publicar, a linha pendente não é
    duplicada. Datas novas são adicionadas normalmente, confirmadas ou
    não.

    Retorna um resumo: {"novas": N, "confirmadas_agora": N, "ainda_pendentes": N}.
    """
    ja_gravadas = set() if sobrescrever else datas_ja_gravadas(aba)
    pendentes = {} if sobrescrever else datas_pendentes(aba)

    novas_linhas = []
    resumo = {"novas": 0, "confirmadas_agora": 0, "ainda_pendentes": 0}

    for item in extrair_intervalo(data_inicio, data_fim):
        if item.data in ja_gravadas:
            continue

        linha = _linha_de(item)

        if item.data in pendentes:
            if item.leituras_confirmadas:
                num_linha = pendentes[item.data]
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
    oferendas_texto: str,
    comunhao_texto: str,
    fonte: str = "iLiturgia (colado manualmente)",
) -> bool:
    """Atualiza, numa linha já existente, os campos de Oferendas/Comunhão
    — uso típico: colar o texto copiado do app iLiturgia. Retorna False
    se a data ainda não tiver linha na planilha (rode a sincronização
    normal primeiro)."""
    coluna_data = aba.col_values(COL_DATA)
    alvo = dia.isoformat()
    if alvo not in coluna_data:
        return False
    linha = coluna_data.index(alvo) + 1  # 1-based, já inclui o cabeçalho

    aba.update_cell(linha, COL_OFERENDAS_TEXTO, oferendas_texto)
    aba.update_cell(linha, COL_COMUNHAO_TEXTO, comunhao_texto)
    aba.update_cell(linha, COL_FONTE_OFERENDAS_COMUNHAO, fonte)
    return True


def salvar_prefacio_selecionado(
    aba: gspread.Worksheet,
    dia: date,
    nome_prefacio: str,
    texto_prefacio: str,
) -> bool:
    """Grava, numa linha já existente, qual Prefácio foi escolhido pra
    entrar antes da Oração Eucarística no roteiro dessa data — uso
    típico: seleção feita na tela do app a partir dos arquivos da pasta
    Orações Eucarísticas no Drive (ver prefacios_drive.py). Retorna
    False se a data ainda não tiver linha na planilha."""
    coluna_data = aba.col_values(COL_DATA)
    alvo = dia.isoformat()
    if alvo not in coluna_data:
        return False
    linha = coluna_data.index(alvo) + 1

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

def _linha_da_data(aba: gspread.Worksheet, dia: date) -> Optional[int]:
    coluna_data = aba.col_values(COL_DATA)
    alvo = dia.isoformat()
    if alvo not in coluna_data:
        return None
    return coluna_data.index(alvo) + 1  # 1-based, já inclui o cabeçalho


def carregar_overrides_secoes(aba: gspread.Worksheet, dia: date) -> dict[str, str]:
    """Lê o dicionário de overrides por seção salvo para essa data.
    Retorna {} se a data não tiver linha ainda, se a coluna estiver vazia,
    ou se o JSON estiver corrompido (nunca derruba a tela por isso)."""
    linha = _linha_da_data(aba, dia)
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


def salvar_override_secao(aba: gspread.Worksheet, dia: date, numero_secao: str, texto: str) -> bool:
    """Grava (ou remove, se texto vazio) o override de UMA seção para essa
    data, sem afetar as demais seções já salvas. Retorna False se a data
    ainda não tiver linha na planilha ou se numero_secao não for uma das
    seções válidas (ver secoes_roteiro.SECOES)."""
    if numero_secao not in NUMEROS_VALIDOS:
        return False
    linha = _linha_da_data(aba, dia)
    if linha is None:
        return False

    overrides = carregar_overrides_secoes(aba, dia)
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
