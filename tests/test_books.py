from interpore import books


def test_join_lines_paragraphs_and_hyphens():
    lines = [
        "This is a long line of text that fills the page width nicely and",
        "keeps going with a hyphen-",
        "ated word and a full line of text that is as long as the others.",
        "Short end.",
        "A new paragraph starts here with a line that is long enough to be full",
        "and ends.",
    ]
    out = books.join_lines(lines)
    paras = out.split("\n\n")
    assert len(paras) == 2  # a full-width line ending in '.' does not end a paragraph
    assert paras[0].endswith("Short end.")
    assert "hyphenated" in paras[0]


def test_is_author_start():
    assert books._is_author_start("Kai Zhang, China University of Petroleum, China, k@x.cn")
    assert books._is_author_start("milad saljooghi, university of hormozgan, Iran, m@y.com")
    assert not books._is_author_start("DuMux and DUNE: A flexible, fully implicit approach")
    assert not books._is_author_start("Flow, transport and mechanics")


def test_authors_2017_drops_emails_and_repeated_country():
    block = [
        "Yohan Davit, IMFT, Toulouse France, France, yohan.davit@imft.fr",
        "Thomas Hiller, RWTH, Germany, hiller@rwth-",
        "aachen.de",
        "Marta Sanchez, RWTH, Germany, m@rwth.de",
    ]
    a = books._authors_2017(block)
    assert [x["name"] for x in a] == ["Yohan Davit", "Thomas Hiller", "Marta Sanchez"]
    assert a[0]["affiliation"] == "IMFT, Toulouse France, France"
    assert "@" not in str(a)


def test_authors_2016_numbers_and_positions():
    block = [
        "Pauline Simonnin 1, Carlos Nieto-Draghi 2, Ben",
        "Smith 1,2",
        "1 phD student, IFPEN, 1 avenue de Bois Preau, 92852, Rueil Malmaison, FR",
        "2 Institute of Process Engineering, University of Stuttgart, Stuttgart, DE",
    ]
    a = books._authors_2016(block)
    assert [x["name"] for x in a] == ["Pauline Simonnin", "Carlos Nieto-Draghi", "Ben Smith"]
    assert a[0]["affiliation"] == "IFPEN, FR"
    assert a[1]["affiliation"] == "Institute of Process Engineering, DE"
    assert a[2]["affiliation"] == "IFPEN, FR; Institute of Process Engineering, DE"


def test_toc_2016():
    page = "\n".join(
        [
            "Plenary speakers",
            "Howard Stone From biofilms to diffusiophoresis",
            "1",
            "Minisymposium 1.1 - Mixing and reaction in permeable media from pore to",
            "continuum scale",
            "Joachim Moortgat Mixing through Viscous Flow Instabilities 26",
            "General Session 2 - General session on computational challenges",
            "Ana Silva Something 618",
        ]
    )
    toc = books.toc_2016(["", page])
    assert toc[1] == ("Plenary", "Plenary speakers")
    assert toc[26] == (
        "MS 1.1",
        "Mixing and reaction in permeable media from pore to continuum scale",
    )
    assert toc[618][0] == "GS 2"
