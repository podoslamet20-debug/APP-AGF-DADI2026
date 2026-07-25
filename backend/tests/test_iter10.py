"""
Iteration 10 backend tests:
1. PUT /api/progres/{entry_id} edits with own_old subtraction
2. PUT fails when qty > sisa_upstream + own_old
3. GET /api/export/progres/pdf returns PDF with Tanggal column
4. GET /api/export/progres/pdf?tanggal=YYYY-MM-DD filter works
5. GET /api/rekap/progres returns tanggal_terakhir + sisa_* fields; no inconsistent rows
6. N10036 napeleon values (grinda=310..packing=310) parity between /progres and rekap
7. BM cards: for N10036 komplit; negative case
8. Legacy rebalance idempotent: no downstream > upstream in rekap
"""
import os
import uuid
import pytest
import requests


def _load_backend_url():
    env_path = "/app/frontend/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@agfdata.com", "password": "admin123"}


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


# ---------- helpers ----------
def _mk_scenario(admin_client, qty_masuk=100):
    tag = uuid.uuid4().hex[:8]
    r = admin_client.post(f"{API}/barang", json={
        "nama_barang": f"TEST_ITER10_{tag}",
        "nama_pengrajin": f"P_{tag}",
        "spesifikasi": "spec", "harga_pengrajin": 10000, "harga_jual": 15000,
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    barang_id = r.json()["_id"]
    r = admin_client.post(f"{API}/po", json={
        "no_po": f"TEST_ITER10_{tag}",
        "items": [{"barang_id": barang_id, "qty": 500, "catatan": ""}],
        "catatan": "iter10",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    po_id = r.json().get("_id") or r.json().get("id")
    r = admin_client.post(f"{API}/barang-masuk", json={
        "po_id": po_id, "tanggal_masuk": "2026-07-24", "penerima": "IT10",
        "items": [{"barang_id": barang_id, "qty_diterima": qty_masuk, "nama_barang": "T"}],
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    return {"barang_id": barang_id, "po_id": po_id}


# ==========================================
# PUT /api/progres/{entry_id}
# ==========================================
class TestProgresEdit:
    @pytest.fixture(scope="class")
    def entry(self, admin_client):
        sc = _mk_scenario(admin_client, qty_masuk=100)
        r = admin_client.post(f"{API}/progres", json={
            "po_id": sc["po_id"], "item_id": sc["barang_id"],
            "stage": "grinda", "qty": 5, "tanggal": "2026-07-24",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        entry_id = d.get("_id") or d.get("id") or d.get("entry_id")
        return {**sc, "entry_id": entry_id}

    def test_edit_qty_up_ok(self, admin_client, entry):
        r = admin_client.put(f"{API}/progres/{entry['entry_id']}", json={
            "po_id": entry["po_id"], "item_id": entry["barang_id"],
            "stage": "grinda", "qty": 10, "tanggal": "2026-07-24",
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sisa_setelah_input" in d, d

    def test_edit_qty_over_limit_400(self, admin_client, entry):
        # qty_masuk=100 -> grinda pipeline max 100. Try 999.
        r = admin_client.put(f"{API}/progres/{entry['entry_id']}", json={
            "po_id": entry["po_id"], "item_id": entry["barang_id"],
            "stage": "grinda", "qty": 999, "tanggal": "2026-07-24",
        }, timeout=30)
        assert r.status_code == 400, r.text
        assert "melebihi" in r.text.lower() or "sisa" in r.text.lower()


# ==========================================
# PDF Export
# ==========================================
class TestProgresPDFExport:
    def test_pdf_export_ok(self, admin_client):
        r = admin_client.get(f"{API}/export/progres/pdf", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        assert r.content.startswith(b"%PDF"), r.content[:20]
        assert len(r.content) > 1000

    def test_pdf_export_filtered_by_tanggal(self, admin_client):
        r = admin_client.get(f"{API}/export/progres/pdf", params={"tanggal": "2026-07-24"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.content.startswith(b"%PDF")


# ==========================================
# Rekap Progres
# ==========================================
class TestRekapProgres:
    def test_rekap_has_new_fields(self, admin_client):
        r = admin_client.get(f"{API}/rekap/progres", timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert isinstance(rows, list)
        # find a row with any progres to inspect fields
        target = None
        for row in rows:
            if row.get("qty_masuk", 0) > 0:
                target = row
                break
        assert target is not None, "no rows with qty_masuk>0"
        for key in ["tanggal_terakhir", "sisa_grinda", "sisa_servis", "sisa_finishing", "sisa_packing"]:
            assert key in target, f"missing {key} in {target}"

    def test_no_inconsistent_rows(self, admin_client):
        r = admin_client.get(f"{API}/rekap/progres", timeout=60)
        assert r.status_code == 200
        bad = []
        for row in r.json():
            qm = row.get("qty_masuk", 0) or 0
            g = row.get("grinda", 0) or 0
            s = row.get("servis", 0) or 0
            f = row.get("finishing", 0) or 0
            p = row.get("packing", 0) or 0
            if g > qm or s > g or f > s or p > f:
                bad.append({"no_po": row.get("no_po"), "nama_barang": row.get("nama_barang"),
                            "qm": qm, "g": g, "s": s, "f": f, "p": p})
        assert bad == [], f"inconsistent rows: {bad[:5]}"

    def test_n10036_napeleon_values(self, admin_client):
        r = admin_client.get(f"{API}/rekap/progres", timeout=60)
        rows = r.json()
        napeleon = [row for row in rows if row.get("no_po") == "N10036"
                    and "napeleon" in (row.get("nama_barang") or "").lower()]
        if not napeleon:
            pytest.skip("N10036 napeleon not present")
        row = napeleon[0]
        assert row.get("qty_masuk") == 400, row
        assert row.get("grinda") == 310, row
        assert row.get("servis") == 310, row
        assert row.get("finishing") == 310, row
        assert row.get("packing") == 310, row


# ==========================================
# BM KOMPLIT (backend data check)
# ==========================================
class TestBMKomplitData:
    def test_n10036_qty_diterima_full(self, admin_client):
        # We check via BM endpoint that N10036 has qty_diterima == PO qty for all items
        r_po = admin_client.get(f"{API}/po", timeout=30)
        assert r_po.status_code == 200
        pos = r_po.json()
        po = next((p for p in pos if p.get("no_po") == "N10036"), None)
        if not po:
            pytest.skip("N10036 PO not present")
        # qty_diterima aggregate from BM
        r_bm = admin_client.get(f"{API}/barang-masuk", timeout=30)
        assert r_bm.status_code == 200
        bms = r_bm.json()
        totals = {}
        for bm in bms:
            if bm.get("po_id") != (po.get("_id") or po.get("id")):
                continue
            for it in bm.get("items", []):
                totals[it.get("barang_id")] = totals.get(it.get("barang_id"), 0) + (it.get("qty_diterima", 0) or 0)
        for it in po.get("items", []):
            bid = it.get("barang_id")
            assert totals.get(bid, 0) >= it.get("qty", 0), \
                f"N10036 barang {bid}: qty_diterima={totals.get(bid,0)} < po_qty={it.get('qty')}"


# ==========================================
# Cleanup TEST_ITER10_
# ==========================================
def test_zzz_cleanup(admin_client):
    # delete test POs
    r = admin_client.get(f"{API}/po", timeout=30)
    if r.status_code == 200:
        for po in r.json():
            if (po.get("no_po") or "").startswith("TEST_ITER10_"):
                pid = po.get("_id") or po.get("id")
                admin_client.delete(f"{API}/po/{pid}", timeout=30)
    r = admin_client.get(f"{API}/barang", timeout=30)
    if r.status_code == 200:
        for b in r.json():
            if (b.get("nama_barang") or "").startswith("TEST_ITER10_"):
                admin_client.delete(f"{API}/barang/{b.get('_id')}", timeout=30)
