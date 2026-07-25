"""
Iteration 9 backend tests - Progres Barang stage-entry model:
1. POST /api/progres creates NEW entry per stage (per date, per input, per stage)
2. Pipeline validation: grinda<=BM sisa, servis<=grinda_sum-servis_sum, finishing<=servis-finishing, packing<=finishing-packing
3. Multiple entries same barang aggregated in by-po
4. Sisa fields on by-po
5. Sync with barang_masuk changes
6. Packing sum -> qty_ready on PO
7. DELETE /api/progres/{entry_id} admin-only
8. GET /api/progres/entries sort desc by tanggal
9. SPKItem validation (qty>=1, nama_barang required)
10. Migration: legacy cumulative progres docs converted (verified via GET /api/progres returning only stage entries)
"""
import os
import time
from datetime import datetime, timezone
import pytest
import requests


def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
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
STAFF = {"email": "staff@agfdata.com", "password": "staff123"}


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def staff_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=STAFF, timeout=30)
    if r.status_code != 200:
        pytest.skip("staff login failed")
    return s


# ---------- helpers ----------
def _create_barang(client, tag):
    payload = {
        "nama_barang": f"TEST_ITER9_{tag}",
        "nama_pengrajin": f"Pengrajin_{tag}",
        "spesifikasi": "spec-iter9",
        "harga_pengrajin": 10000,
        "harga_jual": 15000,
    }
    r = client.post(f"{API}/barang", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_po(client, barang_id, no_po, qty=500):
    payload = {"no_po": no_po, "items": [{"barang_id": barang_id, "qty": qty, "catatan": ""}], "catatan": "iter9"}
    r = client.post(f"{API}/po", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _add_bm(client, po_id, barang_id, qty_diterima, tag=""):
    payload = {
        "po_id": po_id, "tanggal_masuk": "2026-07-17", "penerima": f"IT9{tag}",
        "items": [{"barang_id": barang_id, "qty_diterima": qty_diterima, "nama_barang": "T"}],
    }
    r = client.post(f"{API}/barang-masuk", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


import uuid


def _mk_scenario(admin_client, qty_masuk=100):
    tag = f"{uuid.uuid4().hex[:8]}"
    b = _create_barang(admin_client, tag)
    po = _create_po(admin_client, b["_id"], f"TEST_ITER9_{tag}", qty=500)
    po_id = po.get("_id") or po.get("id")
    _add_bm(admin_client, po_id, b["_id"], qty_masuk)
    return {"barang_id": b["_id"], "po_id": po_id, "qty_masuk": qty_masuk}


# ============================================================
# TEST GROUP 1+2: Stage entry model + Pipeline validation
# (Combined into one class - class-scoped scenario keeps cumulative state)
# ============================================================
class TestStageEntryAndPipeline:
    @pytest.fixture(scope="class")
    def scenario(self, admin_client):
        return _mk_scenario(admin_client, qty_masuk=100)

    def test_1_post_creates_new_entry_with_sisa_setelah_input(self, admin_client, scenario):
        payload = {
            "po_id": scenario["po_id"],
            "item_id": scenario["barang_id"],
            "stage": "grinda",
            "qty": 50,
            "tanggal": "2026-07-17",
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("stage") == "grinda"
        assert d.get("qty") == 50
        assert d.get("tanggal") == "2026-07-17"
        # sisa_setelah_input = 100 - 0 - 50 = 50
        assert d.get("sisa_setelah_input") == 50, d
        assert d.get("upstream_label") == "Barang Masuk", d
        assert d.get("_id"), "no _id returned"

    def test_2_grinda_exceeds_bm_returns_400(self, admin_client, scenario):
        # after previous test: grinda_sum=50, qty_masuk=100 => sisa=50. qty=60 must fail
        payload = {
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "stage": "grinda", "qty": 60, "tanggal": "2026-07-17",
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code == 400, r.text
        assert "melebihi sisa dari Barang Masuk" in r.text, r.text


# ============================================================
# (Continues in same class for shared state)
# ============================================================
class TestPipelineValidation:
    @pytest.fixture(scope="class")
    def scenario(self, admin_client):
        s = _mk_scenario(admin_client, qty_masuk=100)
        # pre-populate: grinda=50
        r = admin_client.post(f"{API}/progres", json={
            "po_id": s["po_id"], "item_id": s["barang_id"],
            "stage": "grinda", "qty": 50, "tanggal": "2026-07-17",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        return s

    def test_servis_ok_then_over(self, admin_client, scenario):
        # grinda_sum should be 50 now
        payload = {"po_id": scenario["po_id"], "item_id": scenario["barang_id"],
                   "stage": "servis", "qty": 30, "tanggal": "2026-07-17"}
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        # servis_sum=30, grinda_sum=50, sisa=20; qty=100 fails
        r2 = admin_client.post(f"{API}/progres", json={
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "stage": "servis", "qty": 100, "tanggal": "2026-07-17"
        }, timeout=30)
        assert r2.status_code == 400, r2.text
        assert "melebihi sisa dari Grinda" in r2.text, r2.text

    def test_finishing_ok_then_over(self, admin_client, scenario):
        r = admin_client.post(f"{API}/progres", json={
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "stage": "finishing", "qty": 30, "tanggal": "2026-07-17"
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        # servis_sum=30, finishing_sum=30, sisa=0
        r2 = admin_client.post(f"{API}/progres", json={
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "stage": "finishing", "qty": 99, "tanggal": "2026-07-17"
        }, timeout=30)
        assert r2.status_code == 400, r2.text
        assert "melebihi sisa dari Servis" in r2.text, r2.text

    def test_packing_ok_then_over(self, admin_client, scenario):
        r = admin_client.post(f"{API}/progres", json={
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "stage": "packing", "qty": 30, "tanggal": "2026-07-17"
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        r2 = admin_client.post(f"{API}/progres", json={
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "stage": "packing", "qty": 99, "tanggal": "2026-07-17"
        }, timeout=30)
        assert r2.status_code == 400, r2.text
        assert "melebihi sisa dari Finishing" in r2.text, r2.text

    def test_invalid_stage_rejected(self, admin_client, scenario):
        r = admin_client.post(f"{API}/progres", json={
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "stage": "xyz", "qty": 1
        }, timeout=30)
        # Pydantic accepts stage as string, validation happens in handler -> 400
        assert r.status_code in (400, 422), r.text


# ============================================================
# TEST GROUP 3: Multiple entries same barang + entries endpoint
# ============================================================
class TestMultipleEntries:
    @pytest.fixture(scope="class")
    def multi_scenario(self, admin_client):
        tag = f"multi_{int(time.time())}"
        b = _create_barang(admin_client, tag)
        po = _create_po(admin_client, b["_id"], f"TEST_ITER9_MULTI_{tag}", qty=500)
        po_id = po.get("_id") or po.get("id")
        _add_bm(admin_client, po_id, b["_id"], 100)
        # Two grinda entries with different dates
        admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "stage": "grinda", "qty": 20, "tanggal": "2026-07-17"
        }, timeout=30)
        admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "stage": "grinda", "qty": 30, "tanggal": "2026-07-18"
        }, timeout=30)
        return {"po_id": po_id, "barang_id": b["_id"]}

    def test_by_po_aggregates_grinda_sum(self, admin_client, multi_scenario):
        r = admin_client.get(f"{API}/progres/by-po", timeout=30)
        assert r.status_code == 200
        found = None
        for po in r.json():
            if po["po_id"] == multi_scenario["po_id"]:
                for it in po["items"]:
                    if it["barang_id"] == multi_scenario["barang_id"]:
                        found = it; break
        assert found, "item not found in by-po"
        assert found["grinda"] == 50, found
        # sisa checks
        assert found["sisa_grinda"] == 100 - 50 == 50
        assert found["sisa_servis"] == 50 - 0
        assert found["sisa_finishing"] >= 0
        assert found["sisa_packing"] >= 0

    def test_entries_endpoint_returns_2_sorted_desc(self, admin_client, multi_scenario):
        r = admin_client.get(f"{API}/progres/entries",
                             params={"po_id": multi_scenario["po_id"], "item_id": multi_scenario["barang_id"]},
                             timeout=30)
        assert r.status_code == 200, r.text
        entries = r.json()
        assert len(entries) == 2, entries
        # sorted by tanggal desc
        assert entries[0]["tanggal"] >= entries[1]["tanggal"]
        assert entries[0]["tanggal"] == "2026-07-18"


# ============================================================
# TEST GROUP 4: Sync with barang_masuk + qty_ready
# ============================================================
class TestSyncFlows:
    def test_add_bm_updates_sisa_grinda(self, admin_client):
        tag = f"sync_{int(time.time())}"
        b = _create_barang(admin_client, tag)
        po = _create_po(admin_client, b["_id"], f"TEST_ITER9_SYNC_{tag}", qty=500)
        po_id = po.get("_id") or po.get("id")
        _add_bm(admin_client, po_id, b["_id"], 50)
        # grinda 40
        admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "stage": "grinda", "qty": 40, "tanggal": "2026-07-17"
        }, timeout=30)
        # add second BM
        _add_bm(admin_client, po_id, b["_id"], 30, tag="_2")
        r = admin_client.get(f"{API}/progres/by-po", timeout=30)
        item = None
        for p in r.json():
            if p["po_id"] == po_id:
                item = p["items"][0]; break
        assert item, "not found"
        assert item["qty_masuk"] == 80, item
        assert item["sisa_grinda"] == 40  # 80-40

    def test_packing_sum_syncs_to_qty_ready(self, admin_client):
        tag = f"ready_{int(time.time())}"
        b = _create_barang(admin_client, tag)
        po = _create_po(admin_client, b["_id"], f"TEST_ITER9_READY_{tag}", qty=500)
        po_id = po.get("_id") or po.get("id")
        _add_bm(admin_client, po_id, b["_id"], 20)
        # Full pipeline: grinda->servis->finishing->packing 10 each
        for stg in ["grinda", "servis", "finishing", "packing"]:
            r = admin_client.post(f"{API}/progres", json={
                "po_id": po_id, "item_id": b["_id"], "stage": stg, "qty": 10, "tanggal": "2026-07-17"
            }, timeout=30)
            assert r.status_code in (200, 201), (stg, r.text)
        # Packing again
        admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "stage": "packing", "qty": 0, "tanggal": "2026-07-18"
        }, timeout=30)
        # Verify qty_ready
        r = admin_client.get(f"{API}/po/{po_id}", timeout=30)
        assert r.status_code == 200, r.text
        po_data = r.json()
        item = po_data["items"][0]
        # qty_ready must reflect packing_sum=10
        assert item.get("qty_ready", 0) == 10, item


# ============================================================
# TEST GROUP 5: DELETE entry (admin) + staff denied
# ============================================================
class TestDeleteEntry:
    def test_admin_can_delete_and_reaggregate(self, admin_client):
        tag = f"del_{int(time.time())}"
        b = _create_barang(admin_client, tag)
        po = _create_po(admin_client, b["_id"], f"TEST_ITER9_DEL_{tag}", qty=500)
        po_id = po.get("_id") or po.get("id")
        _add_bm(admin_client, po_id, b["_id"], 20)
        r1 = admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "stage": "grinda", "qty": 10, "tanggal": "2026-07-17"
        }, timeout=30)
        entry_id = r1.json()["_id"]
        # delete
        rd = admin_client.delete(f"{API}/progres/{entry_id}", timeout=30)
        assert rd.status_code == 200, rd.text
        # re-aggregate: grinda should be 0
        r = admin_client.get(f"{API}/progres/by-po", timeout=30)
        item = None
        for p in r.json():
            if p["po_id"] == po_id:
                if p["items"]:
                    item = p["items"][0]; break
        # after delete, grinda_sum=0. Item may or may not appear (0 grinda is fine)
        if item:
            assert item["grinda"] == 0

    def test_staff_cannot_delete(self, admin_client, staff_client):
        tag = f"deln_{int(time.time())}"
        b = _create_barang(admin_client, tag)
        po = _create_po(admin_client, b["_id"], f"TEST_ITER9_DELN_{tag}", qty=500)
        po_id = po.get("_id") or po.get("id")
        _add_bm(admin_client, po_id, b["_id"], 10)
        r1 = admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "stage": "grinda", "qty": 5, "tanggal": "2026-07-17"
        }, timeout=30)
        entry_id = r1.json()["_id"]
        rd = staff_client.delete(f"{API}/progres/{entry_id}", timeout=30)
        assert rd.status_code == 403, rd.text


# ============================================================
# TEST GROUP 6: Migration - all progres docs have 'stage' field
# ============================================================
class TestMigration:
    def test_no_legacy_progres_docs_remain(self, admin_client):
        r = admin_client.get(f"{API}/progres", timeout=30)
        assert r.status_code == 200
        docs = r.json()
        # Every doc must have 'stage'
        legacy = [d for d in docs if "stage" not in d or not d.get("stage")]
        assert len(legacy) == 0, f"legacy docs remain: {legacy[:3]}"


# ============================================================
# TEST GROUP 7: SPKItem model validation
# ============================================================
class TestSPKItemModel:
    def test_spk_qty_less_than_1_returns_422(self, admin_client):
        payload = {
            "no_spk": f"TEST_ITER9_SPK_{int(time.time())}",
            "items": [{"nama_barang": "X", "qty": 0}],
            "catatan_pembayaran": "", "owner_perusahaan": "AGF", "deadline": "2026-08-01",
        }
        r = admin_client.post(f"{API}/spk", json=payload, timeout=30)
        assert r.status_code == 422, r.text

    def test_spk_missing_nama_barang_returns_422(self, admin_client):
        payload = {
            "no_spk": f"TEST_ITER9_SPK2_{int(time.time())}",
            "items": [{"qty": 1}],  # missing nama_barang
            "catatan_pembayaran": "", "owner_perusahaan": "AGF", "deadline": "2026-08-01",
        }
        r = admin_client.post(f"{API}/spk", json=payload, timeout=30)
        assert r.status_code == 422, r.text

    def test_spk_valid_item_accepted(self, admin_client):
        payload = {
            "no_spk": f"TEST_ITER9_SPK3_{int(time.time())}",
            "items": [{"nama_barang": "TEST_ITER9_item", "qty": 5, "harga": 1000}],
            "catatan_pembayaran": "cash", "owner_perusahaan": "AGF", "deadline": "2026-08-01",
        }
        r = admin_client.post(f"{API}/spk", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text


# ============================================================
# TEST GROUP 8: Regression - update_bm validate-first
# ============================================================
class TestUpdateBmValidateFirst:
    def test_update_bm_over_sisa_rejected_without_side_effect(self, admin_client):
        tag = f"bmup_{int(time.time())}"
        b = _create_barang(admin_client, tag)
        po = _create_po(admin_client, b["_id"], f"TEST_ITER9_BMUP_{tag}", qty=50)
        po_id = po.get("_id") or po.get("id")
        bm = _add_bm(admin_client, po_id, b["_id"], 30)
        bm_id = bm.get("_id") or bm.get("id")
        # Try to update to 999 (over PO qty 50) - must return 400 and NOT wipe PO qty_diterima
        payload = {
            "po_id": po_id, "tanggal_masuk": "2026-07-17", "penerima": "IT9",
            "items": [{"barang_id": b["_id"], "qty_diterima": 999, "nama_barang": "T"}],
        }
        r = admin_client.put(f"{API}/barang-masuk/{bm_id}", json=payload, timeout=30)
        assert r.status_code == 400, r.text
        # Verify PO still has qty_diterima=30
        po_r = admin_client.get(f"{API}/po/{po_id}", timeout=30).json()
        assert po_r["items"][0].get("qty_diterima", 0) == 30, po_r["items"][0]


# ============================================================
# Cleanup at end
# ============================================================
def test_zzz_cleanup(admin_client):
    """Delete all TEST_ITER9_* records."""
    # progres entries (no delete-many via API; rely on delete_one per id via GET /api/progres)
    r = admin_client.get(f"{API}/progres", timeout=30)
    if r.status_code == 200:
        for d in r.json():
            po_id = d.get("po_id")
            if not po_id:
                continue
            # We'll cascade-delete via PO delete below
    # delete BMs for TEST_ITER9 POs first, then PO, then barang
    pos = admin_client.get(f"{API}/po", timeout=30).json()
    test_pos = [p for p in pos if str(p.get("no_po", "")).startswith("TEST_ITER9")]
    bm_list = admin_client.get(f"{API}/barang-masuk", timeout=30).json()
    for bm in bm_list:
        if bm.get("po_id") in [p.get("_id") for p in test_pos]:
            try:
                admin_client.delete(f"{API}/barang-masuk/{bm['_id']}", timeout=30)
            except Exception:
                pass
    for p in test_pos:
        try:
            admin_client.delete(f"{API}/po/{p['_id']}", timeout=30)
        except Exception:
            pass
    # barang
    barangs = admin_client.get(f"{API}/barang", timeout=30).json()
    for b in barangs:
        if str(b.get("nama_barang", "")).startswith("TEST_ITER9"):
            try:
                admin_client.delete(f"{API}/barang/{b['_id']}", timeout=30)
            except Exception:
                pass
    # SPK cleanup
    spks = admin_client.get(f"{API}/spk", timeout=30).json()
    for s in spks:
        if str(s.get("no_spk", "")).startswith("TEST_ITER9"):
            try:
                admin_client.delete(f"{API}/spk/{s['_id']}", timeout=30)
            except Exception:
                pass
    assert True
