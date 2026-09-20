# -*- coding: utf-8 -*-
"""
roteiro_27-09-2026.py — Monte Senário

Roteiro de 27/09/2026 (26º Domingo do Tempo Comum).

Diferença em relação a roteiro_20-09-2026.py: a API da CNBB bloqueou o
acesso (403) tanto para requisição direta quanto via WebFetch nesta
sessão, então as leituras/salmo/evangelho aqui vêm do Nova Aliança e do
Pocket Terço (também usados normalmente para antífona/coleta e
oferendas/comunhão), buscados um bloco de cada vez, com instrução
explícita de citação literal — sem paráfrase — para preservar o texto
oficial. Por não vir do JSON estruturado da CNBB, essas leituras não têm
numeração de versículo individual (ver roteiro_completo._renderizar_leitura,
formato "texto_corrido").
"""

from roteiro_completo import montar_pdf
from roteiro_render import cor_do_tema
from sheets_sync import sugerir_oracao_eucaristica_completa

TITULO_DIA = "26º Domingo do Tempo Comum"
COR_LITURGICA = "verde"  # Tempo Comum

ANTIFONA_ENTRADA = (
    "Tudo quanto nos fizestes, Senhor, com verdadeira justiça o fizestes, "
    "porque pecamos contra vós e não obedecemos a vossos mandamentos; mas "
    "dai glória ao vosso nome e tratai-nos conforme a grandeza da vossa "
    "misericórdia."
)
COLETA = (
    "Ó Deus, que mostrais vosso poder sobretudo no perdão e na "
    "misericórdia, derramai em nós a vossa graça, para que, correndo ao "
    "encontro das vossas promessas, mereçamos participar dos bens "
    "celestes."
)

LEITURA1_TEXTO = (
    "Assim diz o Senhor: Vós andais dizendo: \"A conduta do Senhor não é "
    "correta\". Ouvi, vós da casa de Israel: É a minha conduta que não é "
    "correta, ou antes é a vossa conduta que não é correta?\n\n"
    "Quando um justo se desvia da justiça, pratica o mal e morre, é por "
    "causa do mal praticado que ele morre. Quando um ímpio se arrepende "
    "da maldade que praticou e observa o direito e a justiça, conserva a "
    "própria vida. Arrependendo-se de todos os seus pecados, com certeza "
    "viverá; não morrerá\".\n\n"
    "— Palavra do Senhor."
)

SALMO_REFRAO = "Recordai, Senhor meu Deus, vossa ternura e compaixão!"
SALMO_TEXTO = (
    "Mostrai-me, ó Senhor, vossos caminhos, e fazei-me conhecer a vossa "
    "estrada! Vossa verdade me oriente e me conduza, porque sois o Deus "
    "da minha salvação; em vós espero, ó Senhor, todos os dias!\n\n"
    "Recordai, Senhor meu Deus, vossa ternura e a vossa compaixão que são "
    "eternas! Não recordeis os meus pecados quando jovem, nem vos lembreis "
    "de minhas faltas e delitos! De mim lembrai-vos, porque sois "
    "misericórdia e sois bondade sem limites, ó Senhor!\n\n"
    "O Senhor é piedade e retidão, e reconduz ao bom caminho os "
    "pecadores. Ele dirige os humildes na justiça, e aos pobres ele "
    "ensina o seu caminho."
)

LEITURA2_TEXTO = (
    "Irmãos: Se existe consolação na vida em Cristo, se existe alento no "
    "mútuo amor, se existe comunhão no Espírito, se existe ternura e "
    "compaixão, tornai então completa a minha alegria: aspirai à mesma "
    "coisa, unidos no mesmo amor; vivei em harmonia, procurando a "
    "unidade. Nada façais por competição ou vanglória, mas, com "
    "humildade, cada um julgue que o outro é mais importante, e não "
    "cuide somente do que é seu, mas também do que é do outro. Tende "
    "entre vós o mesmo sentimento que existe em Cristo Jesus.\n\n"
    "Jesus Cristo, existindo em condição divina, não fez do ser igual a "
    "Deus uma usurpação, mas esvaziou-se a si mesmo, assumindo a "
    "condição de escravo e tornando-se igual aos homens. Encontrado com "
    "aspecto humano, humilhou-se a si mesmo, fazendo-se obediente até à "
    "morte, e morte de cruz. Por isso, Deus o exaltou acima de tudo e "
    "lhe deu o Nome que está acima de todo nome.\n\n"
    "Assim, ao nome de Jesus, todo joelho se dobre no céu, na terra e "
    "abaixo da terra, e toda língua proclame: \"Jesus Cristo é o "
    "Senhor!\" — para a glória de Deus Pai.\n\n"
    "— Palavra do Senhor."
)

ACLAMACAO_REFRAO = "Aleluia, Aleluia, Aleluia."
ACLAMACAO_VERSICULO = (
    "Minhas ovelhas escutam a minha voz, minha voz estão elas a "
    "escutar; eu conheço, então, minhas ovelhas, que me seguem, comigo "
    "a caminhar! (Jo 10,27)"
)

EVANGELHO_PROCLAMACAO = "Proclamação do Evangelho de Jesus Cristo segundo Mateus"
EVANGELHO_TEXTO = (
    "Naquele tempo, Jesus disse aos sacerdotes e anciãos do povo: \"Que "
    "vos parece? Um homem tinha dois filhos. Dirigindo-se ao primeiro, "
    "ele disse: 'Filho, vai trabalhar hoje na vinha!' O filho respondeu: "
    "'Não quero'. Mas depois mudou de opinião e foi. O pai dirigiu-se ao "
    "outro filho e disse a mesma coisa. Este respondeu: 'Sim, senhor, "
    "eu vou'. Mas não foi. Qual dos dois fez a vontade do pai?\"\n\n"
    "Os sumos sacerdotes e os anciãos do povo responderam: \"O "
    "primeiro\".\n\n"
    "Então Jesus lhes disse: \"Em verdade vos digo que os cobradores de "
    "impostos e as prostitutas vos precedem no Reino de Deus. Porque "
    "João veio até vós, num caminho de justiça, e vós não acreditastes "
    "nele. Ao contrário, os cobradores de impostos e as prostitutas "
    "creram nele. Vós, porém, mesmo vendo isso, não vos arrependestes "
    "para crer nele\".\n\n"
    "— Palavra da Salvação."
)

OFERENDAS_TEXTO = (
    "Concedei-nos, Deus de misericórdia, que vos agrade esta nossa "
    "oblação e que ela nos abra a fonte de toda bênção. Por Cristo, "
    "nosso Senhor."
)
COMUNHAO_TEXTO = (
    "Fazei, Senhor, que este sacramento celeste renove inteiramente a "
    "nossa vida, para que, anunciando a morte de Cristo, possamos "
    "participar de sua herança gloriosa. Ele, que vive e reina pelos "
    "séculos dos séculos."
)

# Prefácio: sem prefácio próprio salvo no Drive para este domingo do
# Tempo Comum ainda — reaproveita o mesmo Prefácio dos Domingos do Tempo
# Comum I usado em 20/09/2026 (é um dos prefácios genéricos que servem
# para qualquer domingo comum, não específico da data).
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

oracao_euc = sugerir_oracao_eucaristica_completa(TITULO_DIA, tem_prefacio_proprio=True)

dados = {
    "data_iso": "2026-09-27",
    "titulo_dia": TITULO_DIA,
    "horario_missa": "19h",
    "cor_tema": cor_do_tema(COR_LITURGICA),
    "antifona_entrada": ANTIFONA_ENTRADA,
    "coleta": COLETA,
    "leitura1_ref": "Ez 18,25-28",
    "leitura1": {
        "intro": "Leitura da Profecia de Ezequiel 18,25-28",
        "texto_corrido": LEITURA1_TEXTO,
    },
    "salmo_ref": "Sl 24(25),4bc-5.6-7.8-9 (R. 6a)",
    "salmo_refrao": SALMO_REFRAO,
    "salmo": {"texto_corrido": SALMO_TEXTO},
    "leitura2_ref": "Fl 2,1-11",
    "leitura2": {
        "intro": "Leitura da Carta de São Paulo aos Filipenses 2,1-11",
        "texto_corrido": LEITURA2_TEXTO,
    },
    "aclamacao_refrao": ACLAMACAO_REFRAO,
    "aclamacao_versiculo": ACLAMACAO_VERSICULO,
    "evangelho_ref": "Mt 21,28-32",
    "evangelho_proclamacao": EVANGELHO_PROCLAMACAO,
    "evangelho": {"texto_corrido": EVANGELHO_TEXTO},
    "oferendas_texto": OFERENDAS_TEXTO,
    "comunhao_texto": COMUNHAO_TEXTO,
    "prefacio_nome": PREFACIO_NOME,
    "prefacio_texto": PREFACIO_TEXTO,
    "oracao_euc": oracao_euc,
    "fontes": {
        "Fonte das leituras": "Pocket Terço (https://pocketterco.com.br/liturgia/27/09/2026) "
                               "— API da CNBB indisponível para esta data (bloqueio 403)",
        "Fonte da Antífona/Coleta": "Nova Aliança (https://novaalianca.com.br/liturgia-de-27-de-setembro-de-2026/)",
        "Fonte de Oferendas/Comunhão": "Pocket Terço (https://pocketterco.com.br/liturgia/27/09/2026)",
        "Fonte do Prefácio": "Reaproveitado de 20/09/2026 (Prefácio genérico dos Domingos do Tempo Comum I) "
                              "— nenhum prefácio específico desta data na pasta do Drive ainda",
        "Fonte da Oração Eucarística": "https://comshalom.org/oracoes-eucaristicas/ (I-III) e https://pocketterco.com.br (IV)",
        "Cor litúrgica do dia": COR_LITURGICA,
    },
}

if __name__ == "__main__":
    import sys
    overrides = {}
    montar_pdf("/mnt/user-data/outputs/monte_senario/roteiro_27-09-2026.pdf", dados, overrides=overrides)
    print("PDF gerado.")
