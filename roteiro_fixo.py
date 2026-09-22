# -*- coding: utf-8 -*-
"""
roteiro_fixo.py — Monte Senário

Textos fixos do Ordinário da Missa: as partes do roteiro que NÃO vêm de
nenhuma fonte online porque não mudam de missa para missa (diálogos,
Ato Penitencial, Profissão de Fé, Ritos da Comunhão, Ritos Finais).

Cada seção é uma lista de (falante, texto) — falante é "Celebrante",
"Comentarista", "Todos" ou "" (rubrica/texto corrido sem diálogo). Isso
deixa a renderização no gerador do roteiro simples: só iterar e aplicar
o estilo certo por falante (roteiro_render.paragrafo_dialogo trata
qualquer falante que não seja "Todos" com o mesmo estilo — negrito,
preto, justificado).
"""

import re

# Logo oficial da Igreja São Peregrino — usado no cabeçalho do app
# (app.py) e no topo do PDF gerado (roteiro_completo.py). Fonte única
# pra trocar em um lugar só, se um dia mudar de novo.
LOGO_URL = "https://i.ibb.co/HLqFZgZK/logo-igreja.jpg"

SAUDACAO_INICIAL = [
    # A saudação de abertura é feita pelo comentarista, não pelo
    # celebrante — correção explícita do usuário.
    ("Comentarista", "Louvado Seja o Nosso Senhor Jesus Cristo!"),
    ("Todos", "Para sempre seja louvado."),
    ("", (
        "Bom dia! Boa noite! Sejam bem-vindos todos os que estão aqui "
        "presentes e, também os que nos acompanham pelas redes sociais "
        "da Igreja São Peregrino."
    )),
]

RITOS_INICIAIS = [
    ("Celebrante", "Em nome do Pai, do Filho e do Espírito Santo."),
    ("Todos", "Amém."),
    ("Celebrante", (
        "A graça de nosso Senhor Jesus Cristo, o amor do Pai e a "
        "comunhão do Espírito Santo estejam convosco."
    )),
    ("Todos", "Bendito seja Deus que nos reuniu no Amor de Cristo."),
]

ATO_PENITENCIAL = [
    ("Celebrante", (
        "Deus, nosso Pai, todo poderoso, rico em ternura, bondade, "
        "mansidão e misericórdia, perdoe todos e cada um de nossos "
        "pecados, nos oriente e nos conduza ao reino da eterna "
        "felicidade. Por Cristo Senhor nosso."
    )),
    ("Todos", "Amém."),
]

GLORIA = (
    "Glória a Deus nas alturas, e paz na terra aos homens por Ele "
    "amados. Senhor Deus, rei dos céus, Deus Pai todo-poderoso. Nós "
    "vos louvamos, nós vos bendizemos, nós vos adoramos, nós vos "
    "glorificamos, nós vos damos graças por vossa imensa glória. "
    "Senhor Jesus Cristo, Filho Unigênito, Senhor Deus, Cordeiro de "
    "Deus, Filho de Deus Pai. Vós que tirais o pecado do mundo, tende "
    "piedade de nós. Vós que tirais o pecado do mundo, acolhei a "
    "nossa súplica. Vós que estais à direita do Pai, tende piedade de "
    "nós. Só Vós sois o Santo, só vós, o Senhor, só vós, o Altíssimo, "
    "Jesus Cristo, com o Espírito Santo, na glória de Deus Pai. Amém."
)


def gloria_e_dita(titulo_dia: str) -> bool:
    """Regra do documento: 'omitido durante a semana, no Advento e na
    Quaresma, exceto em solenidades ocorridas na semana'."""
    titulo = (titulo_dia or "").lower()
    e_solenidade_ou_festa = "solenidade" in titulo or "festa" in titulo
    e_advento_ou_quaresma = "advento" in titulo or "quaresma" in titulo
    e_domingo = "domingo" in titulo
    if e_advento_ou_quaresma:
        return e_solenidade_ou_festa
    return e_domingo or e_solenidade_ou_festa


def dialogo_abertura_evangelho(texto_proclamacao: str) -> list:
    """Diálogo fixo que antecede a leitura do Evangelho (antífona/aclamação
    de abertura). `texto_proclamacao` é a linha "Proclamação do Evangelho
    de Jesus Cristo segundo <Evangelista> <referência>" — essa parte varia
    por dia (nome do evangelista e capítulo/versículo), mas o restante do
    diálogo é fixo no Ordinário da Missa e não vem de nenhuma fonte
    online, por isso mora aqui e não em roteiro_render.py.

    Confirmado contra o Pocket Terço (pocketterco.com.br/liturgia), que
    traz essa moldura completa; a CNBB só fornece a linha da proclamação,
    sem o diálogo em si.
    """
    return [
        ("Celebrante", "O Senhor esteja convosco."),
        ("Todos", "Ele está no meio de nós."),
        ("Celebrante", texto_proclamacao),
        ("Todos", "Glória a vós, Senhor."),
    ]


DIALOGO_PREFACIO = [
    # Diálogo Introdutório do Prefácio — texto fixo do Missal Romano,
    # idêntico para todo Prefácio, por isso mora aqui (igual às outras
    # partes do Ordinário) em vez de depender do texto de cada arquivo
    # de Prefácio (Google Drive) ou do boletim da Diocese de SJC — essa
    # era, aliás, a origem de um bug real: quando esse trecho vinha de
    # PDF de boletim, era o mais sujeito a caracteres quebrados (fonte
    # sem mapeamento correto para acentos, gerando quadrados pretos).
    ("Celebrante", "O Senhor esteja convosco."),
    ("Todos", "Ele está no meio de nós."),
    ("Celebrante", "Corações ao alto."),
    ("Todos", "O nosso coração está em Deus."),
    ("Celebrante", "Demos graças ao Senhor, nosso Deus."),
    ("Todos", "É nosso dever e nossa salvação."),
]


CONVITE_ACLAMACAO = (
    "Fiquemos em pé e com muita alegria vamos aclamar o Santo "
    "Evangelho, cantando."
)


EVANGELHO_FECHAMENTO = [
    ("Celebrante", "Palavra da Salvação."),
    ("Todos", "Glória a vós, Senhor."),
]


PROFISSAO_DE_FE = (
    "Creio em Deus Pai todo-poderoso, Criador do céu e da terra. E em "
    "Jesus Cristo, seu único Filho, nosso Senhor, que foi concebido "
    "pelo poder do Espírito Santo, nasceu da Virgem Maria, padeceu sob "
    "Pôncio Pilatos, foi crucificado, morto e sepultado, desceu à "
    "mansão dos mortos, ressuscitou ao terceiro dia, subiu aos céus, "
    "está sentado à direita de Deus Pai todo-poderoso, donde há de vir "
    "a julgar os vivos e os mortos. Creio no Espírito Santo, na santa "
    "Igreja Católica, na comunhão dos santos, na remissão dos pecados, "
    "na ressurreição da carne e na vida eterna. Amém."
)

APRESENTACAO_DAS_OFERENDAS = [
    ("Celebrante", (
        "Oremos, irmãos e irmãs, para que este nosso sacrifício seja "
        "aceito por Deus Pai todo-poderoso."
    )),
    ("Todos", (
        "Receba o Senhor por tuas mãos este sacrifício, para a glória "
        "do Seu Nome, para o nosso bem e de toda a Sua Santa Igreja."
    )),
]

RITOS_DA_COMUNHAO = [
    ("", "Oração do Pai Nosso"),
    ("Todos", (
        "Pai Nosso que estais nos céus, santificado seja vosso nome; "
        "venha a nós o vosso reino; seja feita a vossa vontade assim "
        "na terra como no céu. O pão nosso de cada dia nos dai hoje, "
        "perdoai-nos as nossas ofensas, assim como nós perdoamos a "
        "quem nos tem ofendido; e não nos deixeis cair em tentação, "
        "mas livrai-nos do mal."
    )),
    ("Celebrante", (
        "Livrai-nos de todos os males, ó Pai, e dai-nos hoje a vossa "
        "paz. Ajudados pela vossa misericórdia, sejamos sempre livres "
        "do pecado e protegidos de todos os perigos, enquanto "
        "aguardamos a feliz esperança e a vinda do Nosso Salvador, "
        "Jesus Cristo."
    )),
    ("Todos", "Vosso é o reino, o poder e a glória para sempre!"),
    ("Celebrante", (
        "Senhor Jesus Cristo, dissestes aos vossos Apóstolos: Eu vos "
        "deixo a paz, eu vos dou a minha paz. Não olheis os nossos "
        "pecados, mas a fé que anima vossa Igreja; dai-lhe, segundo o "
        "vosso desejo, a paz e a unidade. Vós, que sois Deus, com o "
        "Pai e o Espírito Santo."
    )),
    ("Todos", "Amém."),
    ("Celebrante", "A paz do Senhor esteja sempre convosco."),
    ("Todos", "O amor de Cristo nos uniu."),
    ("", (
        "Cordeiro de Deus que tirais os pecados do mundo, tende "
        "piedade de nós; Cordeiro de Deus que tirais os pecados do "
        "mundo, tende piedade de nós; Cordeiro de Deus que tirais os "
        "pecados do mundo, dai-nos a paz."
    )),
    ("Celebrante", "Eis o Cordeiro de Deus, que tira o pecado do mundo."),
    ("Todos", (
        "Senhor, eu não sou digno/a que entreis em minha morada, mas "
        "dizei uma palavra e serei salvo/a."
    )),
]

RITOS_FINAIS = [
    ("Celebrante", "O Senhor esteja convosco!"),
    ("Todos", "Ele está no meio de nós."),
    ("Celebrante", (
        "E a bênção de Deus todo poderoso, Pai, Filho e Espírito "
        "Santo desça sobre vós e permaneça para sempre."
    )),
    ("Todos", "Amém."),
]


# Livro bíblico (abreviação usual do Lecionário) -> linha de introdução
# litúrgica da leitura (ex.: "Is" -> "Leitura do Livro do Profeta
# Isaías."). Usada para gerar automaticamente a linha que precede o
# texto de cada leitura (Primeira/Segunda Leitura), a partir só da
# referência bíblica (ex.: "Is 55,6-9") — pedido do usuário para seguir
# o padrão usual dos boletins litúrgicos.
LIVROS_BIBLICOS = {
    "Gn": "Leitura do Livro do Gênesis.",
    "Ex": "Leitura do Livro do Êxodo.",
    "Lv": "Leitura do Livro do Levítico.",
    "Nm": "Leitura do Livro dos Números.",
    "Dt": "Leitura do Livro do Deuteronômio.",
    "Js": "Leitura do Livro de Josué.",
    "Jz": "Leitura do Livro dos Juízes.",
    "Rt": "Leitura do Livro de Rute.",
    "1Sm": "Leitura do Primeiro Livro de Samuel.",
    "2Sm": "Leitura do Segundo Livro de Samuel.",
    "1Rs": "Leitura do Primeiro Livro dos Reis.",
    "2Rs": "Leitura do Segundo Livro dos Reis.",
    "1Cr": "Leitura do Primeiro Livro das Crônicas.",
    "2Cr": "Leitura do Segundo Livro das Crônicas.",
    "Ed": "Leitura do Livro de Esdras.",
    "Ne": "Leitura do Livro de Neemias.",
    "Tb": "Leitura do Livro de Tobias.",
    "Jt": "Leitura do Livro de Judite.",
    "Et": "Leitura do Livro de Ester.",
    "Jo": "Leitura do Livro de Jó.",  # ambíguo com o evangelho (ver nota abaixo)
    "Sl": "Leitura do Livro dos Salmos.",
    "Pr": "Leitura do Livro dos Provérbios.",
    "Ecl": "Leitura do Livro do Eclesiastes.",
    "Ct": "Leitura do Cântico dos Cânticos.",
    "Sb": "Leitura do Livro da Sabedoria.",
    "Eclo": "Leitura do Livro do Eclesiástico (Ben Sirá).",
    "Is": "Leitura do Livro do Profeta Isaías.",
    "Jr": "Leitura do Livro do Profeta Jeremias.",
    "Lm": "Leitura das Lamentações.",
    "Br": "Leitura do Livro de Baruc.",
    "Ez": "Leitura do Livro do Profeta Ezequiel.",
    "Dn": "Leitura do Livro do Profeta Daniel.",
    "Os": "Leitura do Livro do Profeta Oseias.",
    "Jl": "Leitura do Livro do Profeta Joel.",
    "Am": "Leitura do Livro do Profeta Amós.",
    "Ab": "Leitura do Livro do Profeta Abdias.",
    "Jn": "Leitura do Livro do Profeta Jonas.",
    "Mq": "Leitura do Livro do Profeta Miqueias.",
    "Na": "Leitura do Livro do Profeta Naum.",
    "Hab": "Leitura do Livro do Profeta Habacuc.",
    "Sf": "Leitura do Livro do Profeta Sofonias.",
    "Ag": "Leitura do Livro do Profeta Ageu.",
    "Zc": "Leitura do Livro do Profeta Zacarias.",
    "Ml": "Leitura do Livro do Profeta Malaquias.",
    "1Mc": "Leitura do Primeiro Livro dos Macabeus.",
    "2Mc": "Leitura do Segundo Livro dos Macabeus.",
    "At": "Leitura dos Atos dos Apóstolos.",
    "Rm": "Leitura da Carta de São Paulo aos Romanos.",
    "1Cor": "Leitura da Primeira Carta de São Paulo aos Coríntios.",
    "2Cor": "Leitura da Segunda Carta de São Paulo aos Coríntios.",
    "Gl": "Leitura da Carta de São Paulo aos Gálatas.",
    "Ef": "Leitura da Carta de São Paulo aos Efésios.",
    "Fl": "Leitura da Carta de São Paulo aos Filipenses.",
    "Cl": "Leitura da Carta de São Paulo aos Colossenses.",
    "1Ts": "Leitura da Primeira Carta de São Paulo aos Tessalonicenses.",
    "2Ts": "Leitura da Segunda Carta de São Paulo aos Tessalonicenses.",
    "1Tm": "Leitura da Primeira Carta de São Paulo a Timóteo.",
    "2Tm": "Leitura da Segunda Carta de São Paulo a Timóteo.",
    "Tt": "Leitura da Carta de São Paulo a Tito.",
    "Fm": "Leitura da Carta de São Paulo a Filêmon.",
    "Hb": "Leitura da Carta aos Hebreus.",
    "Tg": "Leitura da Carta de São Tiago.",
    "1Pd": "Leitura da Primeira Carta de São Pedro.",
    "2Pd": "Leitura da Segunda Carta de São Pedro.",
    "1Jo": "Leitura da Primeira Carta de São João.",
    "2Jo": "Leitura da Segunda Carta de São João.",
    "3Jo": "Leitura da Terceira Carta de São João.",
    "Jd": "Leitura da Carta de São Judas.",
    "Ap": "Leitura do Livro do Apocalipse.",
}

# Evangelho (abreviação) -> nome do evangelista, para a linha
# "Proclamação do Evangelho de Jesus Cristo † segundo <Evangelista>."
EVANGELISTAS = {
    "Mt": "Mateus",
    "Mc": "Marcos",
    "Lc": "Lucas",
    "Jo": "João",
}

_PADRAO_ABREVIACAO = re.compile(r"^\s*([1-3]?\s*[A-Za-zÀ-ÿ]+)")


def _abreviacao_de(ref: str) -> str:
    """Extrai a abreviação do livro bíblico do início de uma referência
    (ex.: 'Is 55,6-9' -> 'Is', '1Cor 12,4-11' -> '1Cor'; tolera espaço
    opcional entre o número e o nome do livro — '1 Cor 12,4-11' também
    funciona, já que algumas fontes formatam assim)."""
    m = _PADRAO_ABREVIACAO.match(ref or "")
    if not m:
        return ""
    return m.group(1).replace(" ", "")


def intro_leitura(ref: str) -> str:
    """Retorna a linha de introdução litúrgica da leitura (ex.: 'Leitura
    do Livro do Profeta Isaías.' para 'Is 55,6-9'), a partir só da
    referência bíblica — pedido do usuário para seguir o padrão usual
    dos boletins ('Primeira Leitura <ref>' seguido dessa linha, depois o
    texto). String vazia se o livro não estiver mapeado (a leitura
    continua sendo exibida normalmente, só sem essa linha extra)."""
    return LIVROS_BIBLICOS.get(_abreviacao_de(ref), "")


def nome_evangelista(ref: str) -> str:
    """Retorna o nome do evangelista a partir da referência do Evangelho
    (ex.: 'Mateus' para 'Mt 20,1-16a'). String vazia se não reconhecido."""
    return EVANGELISTAS.get(_abreviacao_de(ref), "")
