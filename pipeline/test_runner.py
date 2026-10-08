from datetime import UTC, datetime, timedelta

import pytest

from pipeline import runner

T0 = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def test_first_run_mints_run_id_and_holds_lock():
    backend = runner.FakeBackend()
    run_id = runner.run(backend, "demo", 120, now=T0, release=False)
    assert run_id.startswith("20261008T120000Z-")
    assert backend.rows["demo"].run_id == run_id
    assert backend.rows["demo"].expires_at == T0 + timedelta(minutes=120)


def test_second_concurrent_run_fails_with_lock_held():
    backend = runner.FakeBackend()
    first = runner.run(backend, "demo", 120, now=T0, release=False)
    with pytest.raises(runner.LockHeld, match="lock held"):
        runner.run(backend, "demo", 120, now=T0 + timedelta(minutes=5))
    assert backend.rows["demo"].run_id == first


def test_expired_lock_is_taken_over():
    backend = runner.FakeBackend()
    first = runner.run(backend, "demo", 120, now=T0, release=False)
    second = runner.run(backend, "demo", 120, now=T0 + timedelta(minutes=121), release=False)
    assert second != first
    assert backend.rows["demo"].run_id == second


def test_completed_run_releases_lock():
    backend = runner.FakeBackend()
    runner.run(backend, "demo", 120, now=T0)
    assert "demo" not in backend.rows


def test_main_exits_nonzero_when_lock_held(monkeypatch, capsys):
    backend = runner.FakeBackend()
    runner.run(backend, "demo", 120, release=False)
    monkeypatch.setattr(runner, "BigQueryBackend", lambda project_id, max_bytes_billed: backend)
    assert runner.main([]) == 1
    assert "lock held" in capsys.readouterr().err
