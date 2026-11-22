"""Parsing of ONCE launch / end-of-sale documents and game pages (src/scraper/notices.py).

The texts are excerpts of real documents from https://www.juegosonce.es/reglamentos,
as pypdf extracts them, covering each wording seen so far.
"""
from datetime import date

from src.scraper.notices import (
    doc_label,
    link_game,
    parse_launch,
    parse_listing,
    parse_product_info,
    parse_termination,
    product_key,
)

# Resolución 98/2026: two products, each with its own end-date clause
RES_98 = (
    "R E S O L U C I Ó N 1º.- Se aprueba la finalización de los siguientes productos de lotería "
    "instantánea en soporte electrónico: • Producto “con mecánica 3 importes iguales de 9” a un euro, "
    "clase 1, con el nombre “Importes Iguales 6”, que comenzó a comercializarse con fecha 2 de marzo de "
    "2022, según Acuerdo del Consejo General de la ONCE publicado en el Boletín Oficial del Estado el 2 de "
    "febrero de 2022. • Producto “con mecánica uno o varios números iguales” a 5 euros, clase 1, con el "
    "nombre “Números iguales 15”, que comenzó a comercializarse con fecha 5 de julio de 2023, según Acuerdo "
    "del Consejo General de la ONCE publicado en el Boletín Oficial del Estado el 8 de mayo de 2023. "
    "2º. La fecha de finalización de la comercialización de los boletos del producto “Importes Iguales 6” "
    "será el 24 de noviembre de 2026. 3º. La fecha de finalización de la comercialización de los boletos del "
    "producto “Números iguales 15” será el 8 de diciembre de 2026. 4º. Transcurridas las fechas fijadas, no "
    "podrán comercializarse boletos. Madrid, 10 de septiembre de 2026"
)

# Resolución 54/2026: one date for "los anteriores productos"
RES_54 = (
    "1º.- Se aprueba la finalización de los siguientes productos: • Productos “con dos áreas de juego y dos "
    "mecánicas” a cinco euros, clase 13, con el nombre “Millonario electrónico 2024” y “con dos áreas de juego "
    "y dos mecánicas” a diez euros, clase 2, con el nombre “Mega Millonario electrónico 2024”, que comenzaron a "
    "comercializarse con fecha 24 de enero de 2024, según Acuerdo publicado el 8 de diciembre de 2023. "
    "2º.- La fecha de finalización de la comercialización de los boletos de los anteriores productos será el "
    "15 de septiembre de 2026. Madrid, 7 de mayo de 2026"
)

# Resolución 31/2026: two products share a date, a third has its own, in one clause
RES_31 = (
    "1º.- Se aprueba la finalización: • Productos “con mecánica uno o varios números iguales de 5 sobre 20» a "
    "dos euros, clase 1”, con el nombre “Números iguales 9” y , “con mecánica … a 3 euros, clase 1” , con el "
    "nombre “Números iguales 10”, que comenzaron a comercializarse con fecha 2 de febrero de 2022, según "
    "Acuerdo. • Producto “con mecánica siete y media» a un euro, clase 10 “, con el nombre “Siete y media "
    "electrónico 2025”: que comenzó a comercializarse con fecha 11 de junio de 2025, según Acuerdo. "
    "2º.- Las fechas de finalización de la comercialización de los boletos “Números iguales 9” y “Números "
    "iguales 10” será el 28 de abril de 2026 y la del boleto “Siete y media electrónico 2025” el 16 de junio "
    "de 2026. Madrid, 12 de marzo de 2026"
)

# Acuerdo CEP.13/2026-3.2: launch table (electronic + physical) and an end date fixed at launch
CEP_13 = (
    "Nombre Apéndice del Reglamento Nombre de la mecánica Fecha de inicio de Comercialización Crucigrama Flip "
    "E-2026-22 «Con mecánica crucigrama» a cinco euros, clase 2 25/11/2026 Símbolos 40 E-2026-23 «Con mecánica "
    "reúne varios símbolos iguales en ocho oportunidades» a cinco euros, clase 1 16/12/2026 Nombre Apéndice "
    "del Reglamento Nombre de la mecánica Fecha de inicio de Comercialización Fechas ganadoras 2027 F-2026-17 "
    "«Con mecánica encuentra tres cantidades iguales en seis oportunidades» a un euro, clase 1 30/12/2026 "
    "https://run.gob.es/x FIRMANTE(2) : X | FECHA : 21/10/2026 11:17 | Sin acción específica Permanente del "
    "Consejo General. 4º.- Conforme a lo dispuesto en el artículo 19.5, la fecha de finalización del producto "
    "«Fechas ganadoras 2027» (grupo de productos del apéndice F-2026-17) será el 24 de febrero de 2027."
)

# BOE copy of CEP.8/2026: a price with a comma, and one end date for two products
BOE_NAVIDAD = (
    "Fecha de inicio de Comercialización 7 de la suerte electrónico 2026 E-2026-19 «Con mecánica 7 de la "
    "suerte» a 0,50 euros, clase 12 16/09/2026 Rasca de Navidad electrónico 2026 E-2026-20 «Con dos áreas de "
    "juego» a cinco euros, clase 3 14/10/2026 en este documento. Millonario 2026 F-2026-14 «Con mecánica uno o "
    "varios números ganadores de 6 sobre 10» a cinco euros, clase 1 16/09/2026 la fecha de finalización de los "
    "productos «Rasca de Navidad electrónico 2026» (grupo de productos del Apéndice E-2026-20) y «Rasca de "
    "Navidad 2026» (grupo de productos del Apéndice F-2026-16) será el 3 de febrero de 2027."
)


def by_name(products):
    return {p["product_name"]: p for p in products}


def test_termination_separate_clauses():
    p = by_name(parse_termination(RES_98))
    assert p["Importes Iguales 6"]["sale_end"] == date(2026, 11, 24)
    assert p["Importes Iguales 6"]["sale_start"] == date(2022, 3, 2)
    assert p["Números iguales 15"]["sale_end"] == date(2026, 12, 8)
    assert p["Números iguales 15"]["sale_start"] == date(2023, 7, 5)


def test_termination_shared_date_for_previous_products():
    p = by_name(parse_termination(RES_54))
    assert set(p) == {"Millonario electrónico 2024", "Mega Millonario electrónico 2024"}
    assert all(x["sale_end"] == date(2026, 9, 15) for x in p.values())
    assert all(x["sale_start"] == date(2024, 1, 24) for x in p.values())


def test_termination_two_dates_in_one_clause():
    p = by_name(parse_termination(RES_31))
    assert p["Números iguales 9"]["sale_end"] == date(2026, 4, 28)
    assert p["Números iguales 10"]["sale_end"] == date(2026, 4, 28)
    assert p["Siete y media electrónico 2025"]["sale_end"] == date(2026, 6, 16)
    assert p["Siete y media electrónico 2025"]["sale_start"] == date(2025, 6, 11)


def test_launch_table_and_end_clause():
    p = by_name(parse_launch(CEP_13))
    assert set(p) == {"Crucigrama Flip", "Símbolos 40", "Fechas ganadoras 2027"}
    assert p["Crucigrama Flip"] == {
        "product_name": "Crucigrama Flip", "appendix": "E-2026-22",
        "sale_start": date(2026, 11, 25), "sale_end": None,
    }
    assert p["Fechas ganadoras 2027"]["sale_end"] == date(2027, 2, 24)


def test_launch_comma_price_sentence_boundary_and_plural_end_clause():
    p = by_name(parse_launch(BOE_NAVIDAD))
    assert p["7 de la suerte electrónico 2026"]["appendix"] == "E-2026-19"
    assert p["Millonario 2026"]["appendix"] == "F-2026-14"  # row after "… documento."
    assert p["Rasca de Navidad electrónico 2026"]["sale_start"] == date(2026, 10, 14)
    assert p["Rasca de Navidad electrónico 2026"]["sale_end"] == date(2027, 2, 3)
    assert p["Rasca de Navidad 2026"]["sale_end"] == date(2027, 2, 3)


def test_product_info_from_game_page():
    html = (
        "<p>RascaCash (Importes iguales 6) es el juego en el que por 1 € puedes llegar a ganar hasta 15.000 €.</p>"
        "<p>Para más información sobre RascaCash, puedes consultar el apéndice E-2022-01 del reglamento.</p>"
    )
    assert parse_product_info(html) == {"product_name": "Importes iguales 6", "appendix": "E-2022-01"}
    assert parse_product_info("<p>Navidad de Súper Millones: tres juegos. Apéndice E-2021-12.</p>") == {
        "product_name": None, "appendix": "E-2021-12",
    }


def test_product_key_ignores_case_accents_and_spacing():
    assert product_key("Importes Iguales 6") == product_key(" importes  iguales 6 ")
    assert product_key("Símbolos 40") == "simbolos 40"


PRODUCTS = [
    {"product_key": product_key("Importes Iguales 6"), "appendix": None,
     "sale_start": date(2022, 3, 2), "sale_end": date(2026, 11, 24)},
    {"product_key": product_key("Rasca de Navidad electrónico 2026"), "appendix": "E-2026-20",
     "sale_start": date(2026, 10, 14), "sale_end": date(2027, 2, 3)},
    {"product_key": product_key("Rasca de Navidad 2026"), "appendix": "F-2026-16",
     "sale_start": date(2026, 10, 14), "sale_end": date(2027, 2, 3)},
    {"product_key": product_key("Millonario 2024"), "appendix": "F-2024-01",
     "sale_start": date(2024, 1, 24), "sale_end": date(2026, 9, 23)},
]


TODAY = date(2026, 11, 22)
RASCACASH = {  # as seen on the website: listed 2024, first scraped May 2026, last days
    "product_key": product_key("Importes iguales 6"), "appendix": "E-2022-01",
    "listed_start": date(2024, 9, 4), "first_seen": date(2026, 5, 2), "listing_label": "¡Últimos días!",
}


def test_link_by_internal_name():
    assert link_game(RASCACASH, PRODUCTS, TODAY) == {
        "product_key": product_key("Importes Iguales 6"), "matched_by": "product_name",
        "status": "auto", "check_notes": None,
    }


def test_link_never_uses_physical_twin():
    game = {"product_key": product_key("Millonario 2024"), "first_seen": date(2026, 5, 2)}
    assert link_game(game, PRODUCTS, TODAY) is None


def test_link_by_appendix_needs_matching_launch_date():
    near = {"appendix": "E-2026-20", "listed_start": date(2026, 10, 15), "first_seen": date(2026, 10, 15)}
    far = {"appendix": "E-2026-20", "listed_start": date(2026, 6, 1), "first_seen": date(2026, 6, 1)}
    assert link_game(near, PRODUCTS, TODAY)["matched_by"] == "appendix"
    assert link_game(far, PRODUCTS, TODAY) is None


def test_link_rejected_when_product_ended_before_game_appeared():
    game = {**RASCACASH, "first_seen": date(2026, 12, 1)}
    link = link_game(game, PRODUCTS, TODAY)
    assert link["status"] == "rejected"
    assert "before the game was first seen" in link["check_notes"]


def test_link_rejected_when_product_launched_after_game_listed():
    game = {**RASCACASH, "listed_start": date(2021, 1, 1)}
    assert link_game(game, PRODUCTS, TODAY)["status"] == "rejected"


def test_link_warns_when_label_and_date_disagree():
    no_label = link_game({**RASCACASH, "listing_label": None}, PRODUCTS, TODAY)
    assert no_label["status"] == "auto" and "no last-days label" in no_label["check_notes"]
    early = link_game(RASCACASH, PRODUCTS, date(2026, 10, 1))
    assert early["status"] == "auto" and "listing says last days" in early["check_notes"]


def test_parse_listing_card():
    html = (
        '<li class="rascaOrdenable" data-producto="EE4" data-name="RascaCash">'
        '<a class="informacionrasca" href="/rasca-cash"><span class="lblsorteohoy">¡Últimos días!</span></a>'
        '<span class="ocu" data-fecha="1725400800000" data-filter="fechaInicio"></span></li>'
    )
    assert parse_listing(html) == [{
        "game_id": "EE4", "url": "https://www.juegosonce.es/rasca-cash",
        "listing_label": "¡Últimos días!", "listed_start": date(2024, 9, 4),  # 2024-09-03 22:00 UTC
    }]


def test_doc_label():
    assert doc_label("10/09/2026 Resolución 98/2026 Director General ONCE. Aprobando la terminación") \
        == "Resolución 98/2026"
    assert doc_label("21/10/2026 Certificado … Verificación del Acuerdo CEP.13/2026-3.2, de 16 de septiembre") \
        == "Acuerdo CEP.13/2026-3.2"
    assert doc_label("Verificación de los Acuerdos CEP.13/2026-3.1 …", "https://www.boe.es/x.pdf") \
        == "BOE, Acuerdo CEP.13/2026-3.1"
