# tests/test_allowlist.py

from src.retrieval.allowlist import Allowlist, host_from_url, normalize_host


def test_normalize_host():
    assert normalize_host("WWW.IRS.GOV") == "irs.gov"
    assert normalize_host(" irs.gov ") == "irs.gov"


def test_host_from_url():
    assert host_from_url("https://www.irs.gov/forms-pubs") == "irs.gov"
    assert host_from_url("law.cornell.edu") == "law.cornell.edu"
    assert host_from_url("not a url") is None


def test_allowlist_exact_and_subdomain():
    al = Allowlist.from_domains(["irs.gov", "treasury.gov", "law.cornell.edu"])
    assert al.is_allowed_url("https://www.irs.gov/") is True
    assert al.is_allowed_url("https://apps.irs.gov/app/picklist/list/priorFormPublication.html") is True
    assert al.is_allowed_url("https://www.law.cornell.edu/uscode/text/26/2702") is True
    assert al.is_allowed_url("https://example.com/foo") is False
