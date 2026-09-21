# -*- coding: utf-8 -*-
"""
prefacios.py — Monte Senário

Esqueleto da base de Prefácios do Missal Romano (3ª edição, tradução
CNBB). Não há fonte pública gratuita com o texto em português (ver
apuração feita na conversa) — os "texto": "" abaixo são para você colar
o conteúdo copiado do app iLiturgia.

Estrutura pensada para bater com a lista de categorias do Missal; a
numeração/nomes exatos podem variar um pouco entre edições — ajuste
livremente ao ir preenchendo. Uma vez preenchido, esse arquivo se torna
reutilizável para sempre (prefácio é texto fixo, não muda ano a ano).

Uso:
    from prefacios import PREFACIOS
    texto = PREFACIOS["tempo_comum"]["III"]["texto"]
"""

def _vazio(nome, quando_usar=""):
    return {"nome": nome, "quando_usar": quando_usar, "texto": ""}


PREFACIOS = {
    "advento": {
        "I": _vazio("Prefácio I do Advento", "1ª-2ª semana do Advento — as duas vindas de Cristo"),
        "II": _vazio("Prefácio II do Advento", "17-24 de dezembro — a dupla espera de Cristo"),
    },
    "natal": {
        "I": _vazio("Prefácio I do Natal", "Natal e Oitava — Cristo, luz"),
        "II": _vazio("Prefácio II do Natal", "Natal e Oitava — restauração universal pela Encarnação"),
        "III": _vazio("Prefácio III do Natal", "Natal e Oitava — a admirável troca"),
        "epifania": _vazio("Prefácio da Epifania", "Epifania do Senhor"),
    },
    "quaresma": {
        "I": _vazio("Prefácio I da Quaresma", "sentido espiritual da Quaresma"),
        "II": _vazio("Prefácio II da Quaresma", "espírito de penitência"),
        "III": _vazio("Prefácio III da Quaresma", "frutos da penitência/jejum"),
        "IV": _vazio("Prefácio IV da Quaresma", "frutos do jejum"),
    },
    "paixao": {
        "I": _vazio("Prefácio I da Paixão do Senhor", "força da cruz"),
        "II": _vazio("Prefácio II da Paixão do Senhor", "vitória da Paixão"),
    },
    "pascoa": {
        "I": _vazio("Prefácio I da Páscoa", "mistério pascal"),
        "II": _vazio("Prefácio II da Páscoa", "vida nova em Cristo"),
        "III": _vazio("Prefácio III da Páscoa", "Cristo vive e intercede por nós"),
        "IV": _vazio("Prefácio IV da Páscoa", "restauração do universo"),
        "V": _vazio("Prefácio V da Páscoa", "Cristo sacerdote e vítima"),
    },
    "ascensao": {
        "I": _vazio("Prefácio I da Ascensão do Senhor"),
        "II": _vazio("Prefácio II da Ascensão do Senhor"),
    },
    "pentecostes": {
        "unico": _vazio("Prefácio de Pentecostes"),
    },
    "santissima_trindade": {
        "unico": _vazio("Prefácio da Santíssima Trindade"),
    },
    "domingos_tempo_comum": {
        # Prefácios próprios dos domingos do Tempo Comum — ciclo de 8
        numeral: _vazio(f"Prefácio {numeral} dos Domingos do Tempo Comum")
        for numeral in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
    },
    "prefacios_comuns": {
        # Usados em dias de semana sem prefácio próprio
        numeral: _vazio(f"Prefácio Comum {numeral}")
        for numeral in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
    },
    "nossa_senhora": {
        "I": _vazio("Prefácio I da Virgem Maria"),
        "II": _vazio("Prefácio II da Virgem Maria"),
    },
    "santos": {
        "apostolos": _vazio("Prefácio dos Apóstolos"),
        "martires": _vazio("Prefácio dos Mártires"),
        "pastores": _vazio("Prefácio dos Pastores"),
        "virgens_religiosos": _vazio("Prefácio das Virgens e Religiosos"),
        "santos_geral": _vazio("Prefácio dos Santos"),
    },
    "dedicacao_igreja": {
        "unico": _vazio("Prefácio da Dedicação da Igreja"),
    },
    "defuntos": {
        numeral: _vazio(f"Prefácio {numeral} dos Defuntos")
        for numeral in ["I", "II", "III", "IV", "V"]
    },
    "diversas_necessidades": {
        numeral: _vazio(f"Prefácio {numeral} para Diversas Necessidades")
        for numeral in ["I", "II", "III", "IV"]
    },
    "reconciliacao": {
        "I": _vazio("Prefácio da Oração Eucarística da Reconciliação I"),
        "II": _vazio("Prefácio da Oração Eucarística da Reconciliação II"),
    },
}


import re

_ARABICO_PARA_ROMANO = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
}

_PADRAO_NUMERO_TITULO = re.compile(r"(\d+)[ºª]?\s*(?:Domingo|semana)", re.IGNORECASE)


def categoria_prefacio_automatica(titulo_dia: str, tempo_liturgico: str | None, dia=None):
    """Seção 16 — sugestão automática de Prefácio pela estação litúrgica
    do dia (pedido explícito do usuário: "busque o prefácio conforme a
    recomendação litúrgica, na base que está no Drive, pasta
    'Prefácios'" — na prática, a mesma pasta 'Orações Eucarísticas' já
    usada pela seleção manual, onde os arquivos já vêm nomeados
    'PREFÁCIO DO ADVENTO I', 'PREFÁCIO DA QUARESMA II' etc.).

    Retorna (termo_de_busca, ad_libitum) — `termo_de_busca` é o nome (ou
    início do nome) do arquivo a localizar na pasta do Drive;
    `ad_libitum` marca quando a escolha entre variantes é livre por
    rubrica (não uma regra fixa), para o roteiro avisar isso ao
    operador em vez de apresentar como regra rígida. Retorna None
    quando não há uma correspondência confiável (cai no aviso "a
    critério da escolha pastoral", como já era).

    As regras fixas (Advento/Natal/Quaresma — datas e semanas com
    Prefácio próprio definido no Missal) são as únicas tratadas como
    determinísticas; Tempo Comum e a maior parte da Páscoa são ad
    libitum por rubrica (o celebrante escolhe livremente entre as
    opções) — a sugestão aqui é só um ponto de partida razoável, nunca
    uma imposição, e a tela de seleção manual sempre tem prioridade."""
    titulo = titulo_dia or ""
    baixo = titulo.lower()
    tl = tempo_liturgico or ""

    if "semana santa" in baixo or re.search(r"(segunda|ter[çc]a|quarta)-feira santa", baixo):
        return ("PREFÁCIO DA PAIXÃO DO SENHOR I", True)

    # Epifania nem sempre traz "Natal" no próprio título (ex.: "Epifania
    # do Senhor" simples) — checada à parte de tempo_liturgico_de, que
    # só reconhece o Tempo do Natal pela palavra "natal" no título.
    if "epifania" in baixo:
        return ("PREFÁCIO DA EPIFANIA DO SENHOR", False)

    if tl == "Advento":
        if dia and dia.month == 12 and 17 <= dia.day <= 24:
            return ("PREFÁCIO DO ADVENTO II", False)
        return ("PREFÁCIO DO ADVENTO I", False)

    if tl == "Tempo do Natal":
        if "epifania" in baixo:
            return ("PREFÁCIO DA EPIFANIA DO SENHOR", False)
        return ("PREFÁCIO DO NATAL DO SENHOR I", True)

    if tl == "Quaresma":
        m = _PADRAO_NUMERO_TITULO.search(titulo)
        semana = int(m.group(1)) if m else None
        mapa = {1: "I", 2: "I", 3: "II", 4: "III", 5: "IV"}
        if semana in mapa:
            return (f"PREFÁCIO DA QUARESMA {mapa[semana]}", False)
        return ("PREFÁCIO DA QUARESMA I", True)

    if tl == "Tempo Pascal":
        if "ascens" in baixo:
            return ("PREFÁCIO DEPOIS DA ASCENÇÃO DO SENHOR", False)
        if "pentecostes" in baixo:
            return ("PREFÁCIO DE PENTECOSTES", True)
        return ("PREFÁCIO DA PÁSCOA I", True)

    if tl == "Tempo Comum":
        m = _PADRAO_NUMERO_TITULO.search(titulo)
        if m:
            semana = int(m.group(1))
            numeral = _ARABICO_PARA_ROMANO[((semana - 1) % 10) + 1]
            return (f"PREFÁCIO DOS DOMINGOS DO TEMPO COMUM {numeral}", True)
        return ("PREFÁCIO COMUM I", True)

    return None


def obter_prefacio(categoria: str, numeral: str = "unico") -> dict | None:
    cat = PREFACIOS.get(categoria)
    if not cat:
        return None
    return cat.get(numeral)


def listar_pendentes() -> list[str]:
    """Lista 'categoria/numeral' de todos os prefácios ainda sem texto —
    útil como checklist enquanto você vai copiando do iLiturgia."""
    pendentes = []
    for categoria, itens in PREFACIOS.items():
        for numeral, dados in itens.items():
            if not dados["texto"]:
                pendentes.append(f"{categoria}/{numeral} — {dados['nome']}")
    return pendentes


if __name__ == "__main__":
    pendentes = listar_pendentes()
    print(f"{len(pendentes)} prefácios ainda sem texto:\n")
    for p in pendentes:
        print(" -", p)
