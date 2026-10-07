import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import guardrails

FIX = REPO / "tests" / "fixtures"


def test_phi_scan_flags_seeded_ssn_without_echoing_it(capsys):
    assert guardrails.main(["phi-scan", str(FIX / "phi" / "dirty")]) == 1
    err = capsys.readouterr().err
    assert "run.log:1: ssn" in err
    seeded = guardrails.re.search(r"\d{3}-\d{2}-\d{4}", (FIX / "phi" / "dirty" / "run.log").read_text()).group()
    assert seeded not in err


def test_phi_scan_clean_fixture_passes():
    assert guardrails.main(["phi-scan", str(FIX / "phi" / "clean")]) == 0


def test_phi_scan_flags_generated_full_name(tmp_path):
    (tmp_path / "summary.txt").write_text("loaded member Ada Lovelace\n")
    assert guardrails.main(["phi-scan", "--names", "Ada Lovelace", str(tmp_path)]) == 1


def test_names_match_whole_words_only(tmp_path):
    (tmp_path / "lock.txt").write_text("hash adalovelace99 and Ada Lovelaces\n")
    assert guardrails.main(["phi-scan", "--names", "Ada Lovelace", str(tmp_path)]) == 0


def test_marker_check_fixtures():
    assert guardrails.main(["marker-check", str(FIX / "marker" / "unmarked")]) == 1
    assert guardrails.main(["marker-check", str(FIX / "marker" / "marked")]) == 0


def test_marker_must_be_within_window(tmp_path):
    f = tmp_path / "late.csv"
    f.write_text("x\n" * 5000 + guardrails.SPEC["synthetic_marker"]["token"] + "\n")
    assert guardrails.main(["marker-check", str(f)]) == 1


def test_repo_default_skips_allowlisted_fixtures():
    assert guardrails.phi_scan(None) == []
    assert guardrails.marker_check(None) == []


def test_missing_path_is_an_error():
    assert guardrails.main(["phi-scan", "no/such/dir"]) == 2
