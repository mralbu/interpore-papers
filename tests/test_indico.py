from interpore import indico


def test_parse_track():
    assert indico.parse_track("(MS10) Advances in imaging porous media") == (
        "MS10",
        "Advances in imaging porous media",
    )
    assert indico.parse_track("(MS06-A) Physics of multiphase flow") == (
        "MS06-A",
        "Physics of multiphase flow",
    )
    assert indico.parse_track("MS 24 Invited and Plenary Sessions") == (
        "MS24",
        "Invited and Plenary Sessions",
    )
    assert indico.parse_track("Invited & Keynote Lectures") == (None, "Invited & Keynote Lectures")
    assert indico.parse_track(None) == (None, None)


def test_presentation_format():
    f = indico.presentation_format
    assert f("Oral Presentation", "(MS01) Something") == "Oral"
    assert f("Poster + 3 Minute Pitch", None) == "Poster"
    assert f("Online Presentation", None) == "Online"
    assert f("Oral Presentation", "(MS25) Invited & Plenary Speakers") == "Invited"
    assert f("Pre-Recorded Oral Presentation 2", None) == "Oral"
    assert f(None, None) == "Other"


def _p(first, last, aff=None):
    return {"first_name": first, "last_name": last, "affiliation": aff, "emailHash": "x"}


def test_authors_order_and_dedup():
    c = {
        "primaryauthors": [_p("Ana", "Silva", "Uni A"), _p("Bo", "Li")],
        "coauthors": [_p("ana", "silva"), _p("Cy", "Doe", "Lab C")],
    }
    assert indico.authors(c) == [
        {"name": "Ana Silva", "affiliation": "Uni A"},
        {"name": "Bo Li", "affiliation": None},
        {"name": "Cy Doe", "affiliation": "Lab C"},
    ]


def test_attachments_skip_protected_and_non_https():
    c = {
        "folders": [
            {
                "attachments": [
                    {"title": "slides.pdf", "download_url": "https://events.interpore.org/a/1"},
                    {"title": "secret", "download_url": "https://x/2", "is_protected": True},
                    {"title": "bad", "link_url": "javascript:alert(1)"},
                ]
            },
            {"is_protected": True, "attachments": [{"title": "x", "download_url": "https://x/3"}]},
        ]
    }
    assert indico.attachments(c) == [
        {"title": "slides.pdf", "url": "https://events.interpore.org/a/1"}
    ]


def test_parse_event():
    export = {
        "results": [
            {
                "contributions": [
                    {
                        "friendly_id": 7,
                        "title": " A  title ",
                        "description": "Some **text**.",
                        "type": "Poster Presentation",
                        "track": "(MS3) Name",
                        "primaryauthors": [_p("Ana", "Silva")],
                        "speakers": [_p("Ana", "Silva")],
                        "url": "https://events.interpore.org/event/46/contributions/1/",
                    }
                ]
            }
        ]
    }
    (r,) = indico.parse_event(export, {"year": 2024, "number": 16})
    assert r["id"] == "IP2024-7"
    assert r["title"] == "A title"
    assert r["abstract"] == "Some text."
    assert r["format"] == "Poster"
    assert (r["session_code"], r["session"]) == ("MS03", "Name")
    assert r["presenters"] == ["Ana Silva"]
    assert "emailHash" not in str(r)
