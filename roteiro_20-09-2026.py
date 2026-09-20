# -*- coding: utf-8 -*-
"""
roteiro_20-09-2026.py — Monte Senário

Monta o dict de dados do dia 20/09/2026 e chama roteiro_completo.montar_pdf.
Substitui o antigo gerar_roteiro_completo.py (agora genérico, sem data
amarrada). Overrides desta data podem vir da planilha (sheets_sync.
carregar_overrides_secoes) — aqui, na ausência de planilha configurada
neste ambiente de teste, usamos overrides={} (roteiro 100% automático,
seção 02 em branco como padrão).
"""

import json
import pickle

from roteiro_completo import montar_pdf
from roteiro_render import cor_do_tema, cortar_secoes_cnbb, extrair_intro_secao, extrair_versiculos, extrair_refrao_salmo, extrair_aclamacao_evangelho
from sheets_sync import sugerir_oracao_eucaristica_completa

resultado = pickle.load(open("/tmp/resultado_20-09.pkl", "rb"))
dados_cnbb = json.load(open("/tmp/dados_domingo_completo.json"))["content"]

secoes_cnbb = cortar_secoes_cnbb(dados_cnbb["body"])
refrao_salmo = extrair_refrao_salmo(dados_cnbb["body"])
aclamacao = extrair_aclamacao_evangelho(secoes_cnbb.get("aclamacao", ""))

_oracao_euc = sugerir_oracao_eucaristica_completa(resultado.titulo_dia, tem_prefacio_proprio=True)

PREFACIO_NOME = "PREFÁCIO DOS DOMINGOS DO TEMPO COMUM I"
PREFACIO_TEXTO = (
    "Na verdade, é digno e justo, é nosso dever e salvação dar-vos "
    "graças, sempre e em todo lugar, Senhor, Pai santo, Deus eterno e "
    "todo-poderoso, por Cristo, Senhor nosso.\n\n"
    "Por seu mistério pascal ele realizou a obra admirável de nos "
    "chamar do pecado e da escravidão da morte à glória de sermos "
    "agora raça escolhida, sacerdócio régio, nação santa e povo que "
    "vos pertence, para anunciarmos por toda parte os vossos grandes "
    "feitos, ó Pai, que nos chamastes das trevas à vossa luz "
    "maravilhosa.\n\n"
    "Por isso, com os Anjos e Arcanjos, os Tronos e as Dominações e "
    "todos os coros celestes, entoamos o hino da vossa glória, "
    "cantando (dizendo) a uma só voz:\n\n"
    "Santo, Santo, Santo, Senhor, Deus do universo! O céu e a terra "
    "proclamam a vossa glória. Hosana nas alturas! Bendito o que vem "
    "em nome do Senhor! Hosana nas alturas!"
)

dados = {
    "data_iso": resultado.data,
    "titulo_dia": resultado.titulo_dia,
    "horario_missa": "19h",
    "cor_tema": cor_do_tema(dados_cnbb.get("color", "")),
    "antifona_entrada": resultado.antifona_entrada,
    "coleta": resultado.coleta,
    "leitura1_ref": resultado.leitura1_ref,
    "leitura1": {
        "intro": extrair_intro_secao(secoes_cnbb["leitura1"], "PRIMEIRA LEITURA"),
        "versos": extrair_versiculos(secoes_cnbb["leitura1"]),
    },
    "salmo_ref": resultado.salmo_ref,
    "salmo_refrao": refrao_salmo,
    "salmo": {"versos": extrair_versiculos(secoes_cnbb["salmo"])},
    "leitura2_ref": resultado.leitura2_ref if "leitura2" in secoes_cnbb else None,
    "leitura2": (
        {
            "intro": extrair_intro_secao(secoes_cnbb["leitura2"], "SEGUNDA LEITURA"),
            "versos": extrair_versiculos(secoes_cnbb["leitura2"]),
        }
        if "leitura2" in secoes_cnbb else None
    ),
    "aclamacao_refrao": aclamacao.get("refrao"),
    "aclamacao_versiculo": aclamacao.get("versiculo"),
    "evangelho_ref": resultado.evangelho_ref,
    "evangelho_proclamacao": extrair_intro_secao(secoes_cnbb["evangelho"], "EVANGELHO"),
    "evangelho": {"versos": extrair_versiculos(secoes_cnbb["evangelho"])},
    "oferendas_texto": (
        "Acolhei benigno, Senhor, nós vos pedimos, as oferendas do vosso "
        "povo, para que alcancemos pelos celestes sacramentos o que "
        "professamos filialmente pela fé. Por Cristo, nosso Senhor."
    ),
    "comunhao_texto": (
        "Sustentai, Senhor de bondade, com vosso constante auxílio, os "
        "que reconfortais com os vossos sacramentos, para podermos colher "
        "os frutos da redenção na liturgia e na vida. Por Cristo, nosso "
        "Senhor."
    ),
    "prefacio_nome": PREFACIO_NOME,
    "prefacio_texto": PREFACIO_TEXTO,
    "oracao_euc": _oracao_euc,
    "fontes": {
        "Fonte das leituras": f"{resultado.fonte_leituras} ({resultado.url_fonte})",
        "Fonte da Antífona/Coleta": resultado.fonte_propers,
        "Fonte de Oferendas/Comunhão": "Pocket Terço (https://pocketterco.com.br/liturgia/20/09/2026)",
        "Fonte do Prefácio": "Google Drive — 002_Liturgia São Peregrino / Orações Eucarísticas",
        "Fonte da Oração Eucarística": "https://comshalom.org/oracoes-eucaristicas/ (I-III) e https://pocketterco.com.br (IV)",
        "Cor litúrgica do dia (CNBB)": dados_cnbb.get("color", ""),
    },
}

if __name__ == "__main__":
    montar_pdf("/mnt/user-data/outputs/monte_senario/roteiro_20-09-2026.pdf", dados, overrides={})
    print("PDF gerado.")
