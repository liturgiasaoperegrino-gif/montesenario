# -*- coding: utf-8 -*-
"""
prefacios_drive.py — Monte Senário

Lista e baixa os textos de Prefácio que você for subindo em
002_Liturgia São Peregrino / Orações Eucarísticas no Google Drive, para
escolher qual entra no roteiro antes da Oração Eucarística.

Usa a mesma Service Account já configurada para o Google Sheets — o
escopo "drive" já estava incluído em sheets_sync.SCOPES, então não
precisa de nenhuma credencial nova.

Requisitos:
    pip install google-api-python-client
"""

from __future__ import annotations

from googleapiclient.discovery import build

# Pasta "002_Liturgia São Peregrino / Orações Eucarísticas" no Drive
PASTA_ORACOES_EUCARISTICAS_ID = "1N1Hi9M9PfVnp7V8UUYloIkwI-cVlZzsB"


def conectar_drive(credenciais):
    """Recebe as mesmas credenciais (google.oauth2.service_account.Credentials)
    já usadas para o Sheets — ver sheets_sync.conectar_planilha_com_arquivo
    / _com_info — e devolve um cliente da API do Drive."""
    return build("drive", "v3", credentials=credenciais)


def listar_prefacios(servico_drive, pasta_id: str = PASTA_ORACOES_EUCARISTICAS_ID) -> list[dict]:
    """Retorna [{'id': ..., 'nome': ...}] de todo arquivo cujo nome comece
    com 'PREFÁCIO' na pasta indicada, ordenado alfabeticamente. Passe o
    resultado para um selectbox — o 'nome' já sai limpo (sem .txt)."""
    query = (
        f"'{pasta_id}' in parents and trashed = false "
        f"and name contains 'PREFÁCIO'"
    )
    resultados = []
    page_token = None
    while True:
        resp = servico_drive.files().list(
            q=query, fields="nextPageToken, files(id, name)",
            pageToken=page_token, pageSize=100,
        ).execute()
        for f in resp.get("files", []):
            nome = f["name"]
            if nome.lower().endswith(".txt"):
                nome = nome[:-4]
            resultados.append({"id": f["id"], "nome": nome.strip()})
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return sorted(resultados, key=lambda x: x["nome"])


def baixar_texto_prefacio(servico_drive, file_id: str) -> str:
    """Baixa o conteúdo de um arquivo .txt da pasta pelo seu id."""
    conteudo = servico_drive.files().get_media(fileId=file_id).execute()
    if isinstance(conteudo, bytes):
        return conteudo.decode("utf-8")
    return str(conteudo)
