"""Storage-class reconciler (story 7) with a fake listing and a fake ops backend."""

import json
import subprocess

from ingestion import storage_class as sc

SHA = "a" * 64
URI = f"gs://b/source=s/feed=f/ingest_date=2026-10-08/sha256={SHA}/x.csv"
UNTRACKED = f"gs://b/source=s/feed=f/ingest_date=2026-10-08/sha256={'b' * 64}/y.csv"


class Fake:
    def __init__(self):
        self.classes = {URI: "STANDARD", UNTRACKED: "STANDARD"}
        self.rows = [{"file_sha256": SHA, "object_uri": URI, "source": "s", "feed": "f", "state": "reconciled",
                      "storage_class": None, "detail": {}}]  # fmt: skip
        self.inserts = 0

    def run(self, args, **kw):
        if args[0] == "gcloud":
            items = [{"url": f"{u}#123", "metadata": {"storageClass": c}} for u, c in self.classes.items()]
            return subprocess.CompletedProcess(args, 0, json.dumps(items), "")
        sql = args[-1]
        params = {a.split(":", 1)[0][len("--parameter="):]: a.split(":", 2)[2]
                  for a in args if a.startswith("--parameter=")}  # fmt: skip
        if sql.startswith("SELECT"):
            uris = json.loads(params["uris"])
            latest = {r["object_uri"]: dict(r) for r in self.rows if r["object_uri"] in uris}
            for u, r in latest.items():
                classes = [x["storage_class"] for x in self.rows if x["object_uri"] == u and x["storage_class"]]
                r["storage_class"] = classes[-1] if classes else None
            out = [{k: v for k, v in r.items() if k != "detail"} for r in latest.values()]
            return subprocess.CompletedProcess(args, 0, json.dumps(out), "")
        assert sql.startswith("INSERT")
        self.inserts += 1
        for m in json.loads(params["rows"]):
            self.rows.append({"file_sha256": m["sha"], "object_uri": m["uri"], "source": m["source"],
                              "feed": m["feed"], "state": m["state"], "storage_class": m["sc"],
                              "detail": json.loads(m["detail"])})  # fmt: skip
        return subprocess.CompletedProcess(args, 0, "", "")

    def go(self):
        return sc.reconcile(project_id="p", max_bytes_billed=1, bucket="b", run_id="r", run=self.run)


def test_class_moves_across_runs():
    f = Fake()
    assert f.go() == 1
    f.classes[URI] = "COLDLINE"
    assert f.go() == 1
    f.classes[URI] = "ARCHIVE"
    assert f.go() == 1
    moves = [r for r in f.rows if r["storage_class"]]
    assert [(r["detail"]["storage_class_from"], r["detail"]["storage_class_to"]) for r in moves] == [
        (None, "STANDARD"), ("STANDARD", "COLDLINE"), ("COLDLINE", "ARCHIVE")]  # fmt: skip
    assert all(r["state"] == "reconciled" for r in moves)


def test_identical_rerun_appends_nothing():
    f = Fake()
    f.go()
    before = (len(f.rows), f.inserts)
    assert f.go() == 0
    assert (len(f.rows), f.inserts) == before


def test_untracked_object_skipped():
    f = Fake()
    f.go()
    assert not any(r["object_uri"] == UNTRACKED for r in f.rows)


def test_inserts_are_chunked(monkeypatch):
    monkeypatch.setattr(sc, "CHUNK", 1)
    f = Fake()
    f.rows.append({**f.rows[0], "object_uri": UNTRACKED})
    assert f.go() == 2
    assert f.inserts == 2


def test_later_state_row_without_class_does_not_rerecord():
    f = Fake()
    f.go()
    f.rows.append({**f.rows[0], "state": "silver_loaded", "storage_class": None})
    assert f.go() == 0
