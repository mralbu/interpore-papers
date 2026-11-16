from interpore import text


def test_clean_abstract_keeps_paragraphs_and_math():
    raw = "First <b>line</b>\nwraps here.\r\n\r\nSecond **para** with $k_r$ &amp; more."
    assert text.clean_abstract(raw) == ("First line wraps here.\n\nSecond para with $k_r$ & more.")


def test_clean_abstract_html_breaks():
    assert text.clean_abstract("<p>One</p><p>Two</p>") == "One Two"
    assert text.clean_abstract("a<br>b") == "a b"


def test_clean_abstract_empty():
    assert text.clean_abstract(None) == ""
    assert text.clean_abstract("  \n ") == ""


def test_plain_drops_math():
    assert text.plain("flow $\\phi=0.2$ here").split() == ["flow", "here"]


def test_name_key():
    assert text.name_key("Dorthe  Wildenschild") == "dorthe wildenschild"
    assert text.name_key("Tomás Aquino") == "tomas aquino"
    assert text.name_key("J.-F. Dufrêche") == "j f dufreche"


def test_word_count():
    assert text.word_count("a b $x y$ c") == 3
