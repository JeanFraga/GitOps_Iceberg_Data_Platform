import csv
import random
import re

import pytest

from datagen import registry
from datagen.generate import generate
from datagen.ndc import FORMS, generate_ndc, normalize_ndc
from datagen.npi import is_valid_npi
from datagen.tests.test_datagen import SMALL, TOKEN, _ctx, _hashes

PHARM = ("landing", "payer_a", "pharmacy")
PROV = ("landing", "provider_directory", "providers", "providers.csv")
FORM_RE = {f: re.compile(r"^" + "-".join(rf"\d{{{w}}}" for w in f.split("-")) + "$") for f in FORMS}


def _rows(path):
    lines = path.read_text().splitlines()
    assert lines[0] == f"# {TOKEN}"
    return list(csv.DictReader(lines[1:]))


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    root = tmp_path_factory.mktemp("pp") / "out"
    generate(_ctx(), root)
    return root


def _pharm_files(out):
    return sorted(out.joinpath(*PHARM).iterdir())


@pytest.mark.parametrize(
    "raw,norm",
    [
        ("1234-5678-90", "01234567890"),
        ("12345-678-90", "12345067890"),
        ("12345-6789-0", "12345678900"),
        ("12345-6789-01", "12345678901"),
        ("12345678901", "12345678901"),
    ],
)
def test_normalize_ndc(raw, norm):
    assert normalize_ndc(raw) == norm


@pytest.mark.parametrize("bad", ["123-45-6", "abcd-efgh-ij", "1234567890", "", "12345-6789-012", "1234-5678-9a"])
def test_normalize_ndc_errors(bad):
    with pytest.raises(ValueError):
        normalize_ndc(bad)


def test_generate_ndc_forms():
    rng = random.Random(3)
    for f in FORMS:
        ndc = generate_ndc(rng, f)
        assert FORM_RE[f].match(ndc) and len(normalize_ndc(ndc)) == 11


def test_pharmacy_files(out):
    files = _pharm_files(out)
    assert [p.name for p in files] == [f"payer_a_pharmacy_{y}.csv" for y in _ctx().years]
    from datagen.feeds.payer_a_pharmacy import FEED as PHARM_FEED

    own = PHARM_FEED.generate(_ctx()).person_truth
    pa = {r["source_record_id"]: r["person_truth"] for r in own}
    assert all(r["source"] == "payer_a" for r in own)
    seen = set()
    for p in files:
        rows = _rows(p)
        assert 0 < len(rows) <= SMALL["records_per_file"]
        assert rows == sorted(rows, key=lambda r: (r["date_of_service"], r["rx_number"], int(r["fill_number"])))
        for r in rows:
            assert is_valid_npi(r["service_provider_id"]) and is_valid_npi(r["prescriber_id"])
            assert re.fullmatch(r"7\d{6}", r["ncpdp_id"]) and r["cardholder_id"] in pa
            assert r["date_of_service"][:4] == p.stem[-4:] and r["transaction_response_status"] == "P"
            assert float(r["patient_pay_amount"]) + float(r["total_amount_paid"]) == pytest.approx(
                float(r["ingredient_cost_paid"]) + float(r["dispensing_fee_paid"])
            )
            seen.update(f for f, rx in FORM_RE.items() if rx.match(r["product_service_id"]))
    assert seen == set(FORMS)


def test_providers(out):
    rows = _rows(out.joinpath(*PROV))
    npis = [r["npi"] for r in rows]
    assert npis == sorted(set(npis)) and all(map(is_valid_npi, npis))
    assert {r["entity_type_code"] for r in rows} == {"1", "2"}
    assert len(rows) <= SMALL["records_per_file"]


def test_two_runs_identical(tmp_path):
    generate(_ctx(), tmp_path / "a")
    generate(_ctx(), tmp_path / "b")
    assert _hashes(tmp_path / "a") == _hashes(tmp_path / "b")


def test_existing_feed_bytes_unchanged(tmp_path, out):
    old = [
        f
        for f in registry.discover()
        if (f.source, f.feed) not in {("payer_a", "pharmacy"), ("provider_directory", "providers")}
    ]
    generate(_ctx(), tmp_path / "old", feeds=old)
    old_h, all_h = _hashes(tmp_path / "old"), _hashes(out)
    shared = [k for k in old_h if k.startswith("landing/")]
    assert shared and all(old_h[k] == all_h[k] for k in shared)


def test_normalize_ndc_rejects_non_ascii_digits():
    with pytest.raises(ValueError):
        normalize_ndc("\u0661" * 11)
