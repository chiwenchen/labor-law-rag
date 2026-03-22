from app.services.law_registry import LAW_REGISTRY, BASE_URL, get_law_by_id


def test_registry_has_eleven_laws():
    assert len(LAW_REGISTRY) == 11


def test_registry_includes_labor_standards_act():
    ids = [law.law_id for law in LAW_REGISTRY]
    assert "N0030001" in ids


def test_all_laws_have_id_and_name():
    for law in LAW_REGISTRY:
        assert law.law_id.startswith("N")
        assert len(law.law_name) > 0


def test_base_url_format():
    url = BASE_URL.format(law_id="N0030001")
    assert "N0030001" in url
    assert url.startswith("https://")


def test_get_law_by_id_found():
    law = get_law_by_id("N0030001")
    assert law is not None
    assert law.law_name == "勞動基準法"


def test_get_law_by_id_not_found():
    assert get_law_by_id("INVALID") is None
