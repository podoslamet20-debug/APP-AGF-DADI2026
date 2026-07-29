"""
Iter19 fix-verification: POST /api/progres per-pengrajin validation + pengrajin_id persistence.

Scenario:
  - Barang B, PO qty=10 (single item).
  - SPK allocates: P1=3, P2=2 (sum=5, so PO qty=5).
  - BM records: 3 for P1 only, 0 for P2.
  - POST /api/progres (stage=grinda, pengrajin=P2, qty=1) => 400 (no BM for P2).
  - POST /api/progres (stage=grinda, pengrajin=P1, qty=3) => 200.
  - GET /api/progres/entries verifies pengrajin_id persisted on the created doc.
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STAMP = str(int(time.time()))


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@agfdata.com", "admin123")


@pytest.fixture(scope="module")
def ctx(admin):
    c = {}
    # barang
    r = admin.post(f"{API}/barang", json={
        "nama_barang": f"TEST_iter19_barang_{STAMP}", "spesifikasi": "sp",
        "harga_pengrajin": 1000, "harga_jual": 2000
    })
    assert r.status_code == 200, r.text
    c["barang_id"] = r.json()["_id"]

    # pengrajin p1, p2
    r1 = admin.post(f"{API}/pengrajin", json={"nama": f"TEST_iter19_P1_{STAMP}"})
    r2 = admin.post(f"{API}/pengrajin", json={"nama": f"TEST_iter19_P2_{STAMP}"})
    assert r1.status_code == 200 and r2.status_code == 200
    c["p1"] = r1.json()
    c["p2"] = r2.json()

    # PO qty=5
    r = admin.post(f"{API}/po", json={
        "no_po": f"TEST_ITER19_PO_{STAMP}",
        "items": [{"barang_id": c["barang_id"], "qty": 5, "catatan": ""}],
        "catatan": ""
    })
    assert r.status_code == 200, r.text
    c["po_id"] = r.json()["_id"]
    c["no_po"] = r.json()["no_po"]

    # SPK: P1=3, P2=2
    r = admin.post(f"{API}/spk", json={
        "no_spk": f"TEST_ITER19_SPK_{STAMP}",
        "catatan_pembayaran": "cash", "owner_perusahaan": "T",
        "deadline": "2026-03-01",
        "items": [{
            "no_po": c["no_po"], "barang_id": c["barang_id"],
            "nama_barang": "TEST_iter19", "spesifikasi": "sp",
            "qty": 5,
            "allocations": [
                {"pengrajin_id": c["p1"]["_id"], "pengrajin_nama": c["p1"]["nama"], "qty": 3},
                {"pengrajin_id": c["p2"]["_id"], "pengrajin_nama": c["p2"]["nama"], "qty": 2},
            ]
        }]
    })
    assert r.status_code == 200, r.text
    c["spk_id"] = r.json()["_id"]

    # BM: qty 3 for P1 only
    r = admin.post(f"{API}/barang-masuk", json={
        "po_id": c["po_id"], "tanggal_masuk": "2026-01-19", "penerima": "T",
        "items": [{
            "barang_id": c["barang_id"],
            "pengrajin_id": c["p1"]["_id"],
            "pengrajin_nama": c["p1"]["nama"],
            "qty_diterima": 3
        }]
    })
    assert r.status_code == 200, r.text
    c["bm_id"] = r.json()["_id"]

    yield c

    # cleanup
    for pid_key, url in [
        ("progres_ids", None),
        ("bm_id", f"{API}/barang-masuk/{c.get('bm_id','')}"),
        ("spk_id", f"{API}/spk/{c.get('spk_id','')}"),
        ("po_id", f"{API}/po/{c.get('po_id','')}"),
        ("barang_id", f"{API}/barang/{c.get('barang_id','')}"),
    ]:
        if pid_key == "progres_ids":
            for pid in c.get("progres_ids", []):
                admin.delete(f"{API}/progres/{pid}")
        elif c.get(pid_key):
            admin.delete(url)
    for pk in ("p1", "p2"):
        if c.get(pk):
            admin.delete(f"{API}/pengrajin/{c[pk]['_id']}")


def test_p2_no_bm_grinda_rejected(admin, ctx):
    """P2 has 0 BM - grinda entry for P2 must be rejected 400."""
    r = admin.post(f"{API}/progres", json={
        "po_id": ctx["po_id"], "item_id": ctx["barang_id"],
        "pengrajin_id": ctx["p2"]["_id"], "pengrajin_nama": ctx["p2"]["nama"],
        "stage": "grinda", "qty": 1
    })
    assert r.status_code == 400, f"expected 400 (no BM for P2), got {r.status_code}: {r.text}"
    body = r.text.lower()
    assert "melebihi" in body or "barang masuk" in body


def test_p1_grinda_valid(admin, ctx):
    """P1 has 3 BM - grinda qty=3 should succeed and persist pengrajin_id."""
    r = admin.post(f"{API}/progres", json={
        "po_id": ctx["po_id"], "item_id": ctx["barang_id"],
        "pengrajin_id": ctx["p1"]["_id"], "pengrajin_nama": ctx["p1"]["nama"],
        "stage": "grinda", "qty": 3
    })
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc.get("pengrajin_id") == ctx["p1"]["_id"], f"pengrajin_id not returned in POST body: {doc}"
    ctx.setdefault("progres_ids", []).append(doc["_id"])


def test_progres_entries_persist_pengrajin_id(admin, ctx):
    """GET /api/progres/entries must show pengrajin_id set on the doc created above."""
    r = admin.get(f"{API}/progres/entries", params={"po_id": ctx["po_id"], "item_id": ctx["barang_id"]})
    assert r.status_code == 200
    entries = r.json()
    p1_entries = [e for e in entries if e.get("pengrajin_id") == ctx["p1"]["_id"] and e["stage"] == "grinda"]
    assert len(p1_entries) >= 1, f"No progres entry with pengrajin_id=P1 found. Entries={entries}"
    e = p1_entries[0]
    assert e["qty"] == 3
    assert e.get("pengrajin_id") == ctx["p1"]["_id"]


def test_p1_grinda_exceed_now_rejected(admin, ctx):
    """After 3/3 P1 grinda done, additional 1 grinda for P1 must be rejected."""
    r = admin.post(f"{API}/progres", json={
        "po_id": ctx["po_id"], "item_id": ctx["barang_id"],
        "pengrajin_id": ctx["p1"]["_id"], "pengrajin_nama": ctx["p1"]["nama"],
        "stage": "grinda", "qty": 1
    })
    assert r.status_code == 400, r.text
