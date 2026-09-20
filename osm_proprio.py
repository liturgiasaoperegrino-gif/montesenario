# -*- coding: utf-8 -*-
"""
osm_proprio.py — Monte Senário

Calendário fixo do Próprio dos Santos da Ordem dos Servos de Maria (OSM),
extraído de:
https://servidimaria.net/sitoosm/po/textos-osm/livros-liturgicos-osm/missal-osm.html

Cada PDF traz o formulário COMPLETO da missa própria — incluindo Antífona
de Entrada, Coleta, Prefácio, Oração sobre as Oferendas, Antífona e Oração
depois da Comunhão, e Bênção Solene — o que preenche exatamente a lacuna
que a fonte principal (novaalianca.com.br) deixa.

Cobertura: apenas as datas fixas abaixo (festas/memórias próprias da
Ordem). Para os demais dias do ano, o pipeline continua sem fonte aberta
e scrapável para "Sobre as Oferendas" / "Depois da Comunhão" — precisaria
de um Missal Digital comercial (app fechado) ou digitação manual.

Uso:
    from osm_proprio import PROPRIO_OSM
    from datetime import date
    pdf_url = PROPRIO_OSM.get((9, 15))  # (mês, dia) -> URL do PDF
"""

BASE = "http://servidimaria.net/sitoosm/po/textos-osm/livros-liturgicos-osm/missa"

# Chave: (mês, dia). Valor: (nome da celebração, URL do PDF)
PROPRIO_OSM = {
    (1, 12): ("Santo António M. Pucci", f"{BASE}/antonio.pdf"),
    (1, 15): ("B.A. Tiago de Città della Pieve", f"{BASE}/villa.pdf"),
    (2, 3): ("B.A. Joaquim de Sena", f"{BASE}/joaquin.pdf"),
    (2, 17): ("Sete Santos Fundadores", f"{BASE}/fundadores.pdf"),
    (2, 19): ("B.A. Isabel Picenardi", f"{BASE}/isabel.pdf"),
    (5, 4): ("São Peregrino Laziosi", f"{BASE}/peregrino.pdf"),
    (5, 8): ("Virgem Maria, Mãe e Medianeira", f"{BASE}/mariagracia.pdf"),
    (5, 11): ("B.A. Benincasa", f"{BASE}/benincasa.pdf"),
    (5, 12): ("B.A. Francisco de Sena", f"{BASE}/francisco.pdf"),
    (5, 30): ("B.A. Tiago Filipe Bertoni", f"{BASE}/tiago.pdf"),
    (6, 19): ("Santa Juliana", f"{BASE}/juliana.pdf"),
    (6, 27): ("B.A. Tomás de Orvieto", f"{BASE}/tomas.pdf"),
    (7, 4): ("B.A. Ubaldo de Borgo Sansepolcro", f"{BASE}/ubaldo.pdf"),
    (7, 13): ("Santa Clélia Barbieri", f"{BASE}/clelia.pdf"),
    (8, 23): ("São Filipe Benizi", f"{BASE}/filipe.pdf"),
    (8, 28): ("Santo Agostinho", f"{BASE}/agustin.pdf"),
    (8, 31): ("B.A. André de Borgo Sansepolcro", f"{BASE}/andres.pdf"),
    (9, 1): ("B.A. Joana de Florença", f"{BASE}/juana.pdf"),
    (9, 6): ("B.A. Boaventura de Forlì", f"{BASE}/bonaforli.pdf"),
    (9, 15): ("Nossa Senhora das Dores (Padroeira da Ordem)", f"{BASE}/dolorosa.pdf"),
    (9, 22): ("Dedicação da Basílica de Monte Senário", f"{BASE}/msenario.pdf"),
    (10, 25): ("B.A. João Ângelo de Milão", f"{BASE}/juanangel.pdf"),
    (11, 16): ("Todos os Santos O.S.M.", f"{BASE}/todosantos.pdf"),
    (11, 17): ("Comemoração dos Defuntos O.S.M.", f"{BASE}/difuntos.pdf"),
    (12, 10): ("B.A. Jerónimo de Sant'Angelo in Vado", f"{BASE}/jeronimo.pdf"),
    (12, 15): ("B.A. Boaventura de Pistóia", f"{BASE}/bonapistoia.pdf"),
}

# Formulários sem data fixa (dependem do calendário móvel ou são "comuns",
# usados quando não há celebração própria no dia): mapear manualmente
# quando forem necessários.
OUTROS_FORMULARIOS_OSM = {
    "sexta_feira_pos_5a_semana_quaresma": (
        "B.A. Virgem Maria ao pé da Cruz", f"{BASE}/piecruz.pdf"
    ),
    "memorias_sabado_advento": ("Memória de Santa Maria no Sábado — Advento", f"{BASE}/adviento.pdf"),
    "memorias_sabado_natal": ("Memória de Santa Maria no Sábado — Natal", f"{BASE}/navidad.pdf"),
    "memorias_sabado_pascoa": ("Memória de Santa Maria no Sábado — Páscoa", f"{BASE}/pascua.pdf"),
    "tempo_comum_refugio": ("Santa Maria, Refúgio dos seus Servos — Tempo Comum I", f"{BASE}/maria1.pdf"),
    "tempo_comum_serva": ("Santa Maria, Serva do Senhor — Tempo Comum II", f"{BASE}/maria2.pdf"),
}


def buscar_formulario_osm(dia):
    """Recebe um objeto date e retorna (nome, url_pdf) se houver formulário
    próprio da OSM para essa data, ou None caso contrário."""
    return PROPRIO_OSM.get((dia.month, dia.day))


if __name__ == "__main__":
    from datetime import date

    for teste in [date(2026, 9, 15), date(2026, 9, 17), date(2026, 9, 22)]:
        resultado = buscar_formulario_osm(teste)
        print(teste, "->", resultado or "sem formulário próprio OSM nesta data")
