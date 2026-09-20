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
