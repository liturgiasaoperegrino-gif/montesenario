# -*- coding: utf-8 -*-
"""
secoes_roteiro.py — Monte Senário

Lista única das 20 (+1) seções do roteiro padronizado, na ordem definida
pelo documento do usuário. Serve de fonte única de verdade tanto para o
gerador de PDF (roteiro_completo.py) quanto para a interface de gestão
por seção no app.py — assim as duas nunca ficam dessincronizadas quanto
a quantas seções existem, seus números e nomes.

Cada seção também indica se é "editável por override" (texto livre que
o operador pode digitar/colar para substituir o conteúdo automático) e
se é a seção do Prefácio (que tem interface própria, ligada ao Drive,
em vez de uma caixa de texto livre).
"""

SECOES = [
    {"numero": "00", "nome": "Data da Missa e Horário", "overridable": True},
    {"numero": "01", "nome": "Saudação", "overridable": True},
    {"numero": "02", "nome": "Título da Solenidade / Palavras de Abertura", "overridable": True},
    {"numero": "03", "nome": "Ritos Iniciais", "overridable": True},
    {"numero": "04", "nome": "Ato Penitencial", "overridable": True},
    {"numero": "05", "nome": "Glória", "overridable": True},
    {"numero": "06", "nome": "Oração da Coleta", "overridable": True},
    {"numero": "07", "nome": "Liturgia da Palavra", "overridable": True},
    {"numero": "08", "nome": "Primeira Leitura", "overridable": True},
    {"numero": "09", "nome": "Salmo Responsorial", "overridable": True},
    {"numero": "10", "nome": "Segunda Leitura", "overridable": True},
    {"numero": "11", "nome": "Aclamação ao Evangelho", "overridable": True},
    {"numero": "12", "nome": "Evangelho", "overridable": True},
    {"numero": "13", "nome": "Profissão de Fé", "overridable": True},
    {"numero": "14", "nome": "Liturgia Eucarística (Apresentação das Oferendas)", "overridable": True},
    {"numero": "15", "nome": "Oração sobre as Oferendas", "overridable": True},
    {"numero": "16", "nome": "Prefácio e Oração Eucarística", "overridable": True, "e_prefacio": True},
    {"numero": "17", "nome": "Ritos da Comunhão", "overridable": True},
    {"numero": "18", "nome": "Oração após a Comunhão", "overridable": True},
    {"numero": "19", "nome": "Novenas e Reflexões Especiais", "overridable": True},
    {"numero": "20", "nome": "Ritos Finais e Bênção Final", "overridable": True},
]

NUMEROS_VALIDOS = {s["numero"] for s in SECOES}


def nome_da_secao(numero: str) -> str:
    for s in SECOES:
        if s["numero"] == numero:
            return s["nome"]
    return numero
