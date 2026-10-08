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


def test_phi_scan_names_file(tmp_path):
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "summary.txt").write_text("loaded member Ada Lovelace\n")
    names = tmp_path / "names.txt"
    names.write_text("Grace Hopper\nAda Lovelace\n")
    assert guardrails.main(["phi-scan", "--names-file", str(names), str(tmp_path / "scan")]) == 1
    names.write_text("Grace Hopper\n")
    assert guardrails.main(["phi-scan", "--names-file", str(names), str(tmp_path / "scan")]) == 0


def _weight():
    return guardrails.SPEC["repo_weight"]


def test_repo_weight_flags_oversized_file(tmp_path, capsys):
    (tmp_path / "big.csv").write_bytes(b"a\n" + b"x" * (_weight()["max_bytes"] + 1))
    assert guardrails.main(["repo-weight", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "big.csv" in err and "bytes" in err


def test_repo_weight_flags_too_many_records(tmp_path, capsys):
    n = _weight()["sample_records"] + 1
    (tmp_path / "rows.csv").write_text("# marker\nid\n" + "".join(f"{i}\n" for i in range(n)))
    assert guardrails.main(["repo-weight", str(tmp_path)]) == 1
    assert "rows.csv" in capsys.readouterr().err


def test_repo_weight_csv_header_and_comments_not_counted(tmp_path):
    n = _weight()["sample_records"]
    (tmp_path / "rows.csv").write_text("# marker\nid\n" + "".join(f"{i}\n" for i in range(n)))
    assert guardrails.main(["repo-weight", str(tmp_path)]) == 0


def test_repo_weight_counts_x12_claims(tmp_path):
    n = _weight()["sample_records"]
    (tmp_path / "a.837").write_text("ISA*x~" + "CLM*1~NM1*y~" * (n + 1))
    (tmp_path / "b.837").write_text("ISA*x~" + "CLM*1~NM1*y~" * n)
    assert [f.split(":")[0] for f in guardrails.repo_weight(str(tmp_path))] == [str(tmp_path / "a.837")]


def test_repo_weight_ignores_samples_dir(tmp_path):
    d = tmp_path / "datagen" / "samples" / "payer_a"
    d.mkdir(parents=True)
    (d / "big.csv").write_bytes(b"x" * (_weight()["max_bytes"] + 1))
    assert guardrails.main(["repo-weight", str(tmp_path)]) == 0


def test_repo_weight_clean_repo():
    assert guardrails.main(["repo-weight"]) == 0
