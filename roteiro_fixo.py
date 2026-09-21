# -*- coding: utf-8 -*-
"""
roteiro_fixo.py — Monte Senário

Textos fixos do Ordinário da Missa: as partes do roteiro que NÃO vêm de
nenhuma fonte online porque não mudam de missa para missa (diálogos,
Ato Penitencial, Profissão de Fé, Ritos da Comunhão, Ritos Finais).

Cada seção é uma lista de (falante, texto) — falante é "Celebrante",
"Todos" ou "" (rubrica/texto corrido sem diálogo). Isso deixa a
renderização no gerador do roteiro simples: só iterar e aplicar o
estilo certo por falante.
"""

SAUDACAO_INICIAL = [
    ("Celebrante", "Louvado Seja o Nosso Senhor Jesus Cristo!"),
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


EVANGELHO_FECHAMENTO = [
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
