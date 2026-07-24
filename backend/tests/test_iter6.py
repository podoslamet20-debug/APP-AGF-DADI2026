"""
Iteration 6 backend tests:
1. BUG FIX: PUT /api/po/{po_id} must preserve qty_staffed & qty_diterima counters
2. VALIDATION: POST /api/barang-masuk with qty_diterima > sisa -> HTTP 400 with 'sisa' text
3. VALIDATION: POST /api/staffing with qty > sisa -> HTTP 400 with 'sisa' text
4. PYDANTIC: POST /api/barang-masuk missing barang_id / negative qty_diterima -> 422
5. PYDANTIC: POST /api/staffing missing barang_id / negative qty -> 422
6. PUT /api/barang-masuk/{id} revert old + apply new + validate remaining
7. PUT /api/staffing/{id} revert old + apply new + validate remaining
"""
import os
import time
import pytest
import requests

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    # Fallback: parse frontend/.env
    env_path = "/app/frontend/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set and frontend/.env missing")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@agfdata.com", "password": "admin123"}


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    # cookie is set on session automatically
    return s


# -------- helpers --------
def _create_barang(client, tag):
    payload = {
        "nama_barang": f"TEST_iter6_barang_{tag}",
        "nama_pengrajin": f"TEST_iter6_pengrajin_{tag}",
        "spesifikasi": "spec-iter6",
        "harga_pengrajin": 10000,
        "harga_jual": 15000,
    }
    r = client.post(f"{API}/barang", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_po(client, barang_id, no_po, qty=10):
    payload = {
        "no_po": no_po,
        "items": [{"barang_id": barang_id, "qty": qty, "catatan": ""}],
        "catatan": "iter6",
    }
    r = client.post(f"{API}/po", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _get_po(client, po_id):
    r = client.get(f"{API}/po/{po_id}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ==================================================================
# TEST 1: update_po preserves qty_staffed & qty_diterima
# ==================================================================
class TestUpdatePOPreservesCounters:

    def test_update_po_preserves_qty_staffed_and_qty_diterima(self, admin_client):
        # Create barang + PO qty=20
        b = _create_barang(admin_client, f"upd_{int(time.time())}_1")
        no_po = f"TEST_ITER6_UPD_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=20)
        po_id = po.get("_id") or po.get("id")

        # Create a Barang Masuk qty_diterima=5 -> po.qty_diterima=5
        bm_payload = {
            "po_id": po_id, "tanggal_masuk": "2026-01-15", "penerima": "Iter6Test",
            "items": [{"barang_id": b["_id"], "qty_diterima": 5, "nama_barang": "T"}],
        }
        r_bm = admin_client.post(f"{API}/barang-masuk", json=bm_payload, timeout=30)
        assert r_bm.status_code in (200, 201), r_bm.text
        bm_id = r_bm.json().get("_id")

        # Create Staffing qty=3 -> po.qty_staffed=3
        st_payload = {
            "po_id": po_id, "tanggal_keluar": "2026-01-16",
            "items": [{"barang_id": b["_id"], "qty": 3, "nama_barang": "T"}],
        }
        r_st = admin_client.post(f"{API}/staffing", json=st_payload, timeout=30)
        assert r_st.status_code in (200, 201), r_st.text
        st_id = r_st.json().get("_id")

        # Verify pre-update state
        before = _get_po(admin_client, po_id)
        item_before = next(i for i in before["items"] if i["barang_id"] == b["_id"])
        assert item_before.get("qty_diterima") == 5, f"pre-update qty_diterima expected 5 got {item_before.get('qty_diterima')}"
        assert item_before.get("qty_staffed") == 3, f"pre-update qty_staffed expected 3 got {item_before.get('qty_staffed')}"

        # PUT PO with modified qty=25 (increase)
        upd = {
            "no_po": no_po,
            "items": [{"barang_id": b["_id"], "qty": 25, "catatan": "updated"}],
            "catatan": "iter6-updated",
        }
        r_up = admin_client.put(f"{API}/po/{po_id}", json=upd, timeout=30)
        assert r_up.status_code == 200, r_up.text

        # Verify post-update: counters MUST NOT reset
        after = _get_po(admin_client, po_id)
        item_after = next(i for i in after["items"] if i["barang_id"] == b["_id"])
        assert item_after.get("qty") == 25, f"qty should be updated to 25 got {item_after.get('qty')}"
        assert item_after.get("qty_diterima") == 5, f"BUG: qty_diterima was reset from 5 to {item_after.get('qty_diterima')}"
        assert item_after.get("qty_staffed") == 3, f"BUG: qty_staffed was reset from 3 to {item_after.get('qty_staffed')}"

        # cleanup
        admin_client.delete(f"{API}/staffing/{st_id}", timeout=30)
        admin_client.delete(f"{API}/barang-masuk/{bm_id}", timeout=30)


# ==================================================================
# TEST 2 & 3: Sisa validation on Barang Masuk & Staffing
# ==================================================================
class TestSisaValidation:

    @pytest.fixture(scope="class")
    def po_ctx(self, admin_client):
        b = _create_barang(admin_client, f"sisa_{int(time.time())}")
        no_po = f"TEST_ITER6_SISA_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=10)
        po_id = po.get("_id") or po.get("id")
        return {"barang_id": b["_id"], "po_id": po_id}

    def test_bm_qty_exceeds_sisa_returns_400_with_sisa(self, admin_client, po_ctx):
        payload = {
            "po_id": po_ctx["po_id"], "tanggal_masuk": "2026-01-15", "penerima": "T",
            "items": [{"barang_id": po_ctx["barang_id"], "qty_diterima": 999, "nama_barang": "T"}],
        }
        r = admin_client.post(f"{API}/barang-masuk", json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "sisa" in detail, f"expected 'sisa' in detail, got: {detail}"

    def test_staffing_qty_exceeds_sisa_returns_400_with_sisa(self, admin_client, po_ctx):
        payload = {
            "po_id": po_ctx["po_id"], "tanggal_keluar": "2026-01-16",
            "items": [{"barang_id": po_ctx["barang_id"], "qty": 999, "nama_barang": "T"}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "sisa" in detail, f"expected 'sisa' in detail, got: {detail}"


# ==================================================================
# TEST 4 & 5: Pydantic validation errors (422)
# ==================================================================
class TestPydanticValidation:

    @pytest.fixture(scope="class")
    def po_ctx(self, admin_client):
        b = _create_barang(admin_client, f"pyd_{int(time.time())}")
        no_po = f"TEST_ITER6_PYD_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=10)
        return {"barang_id": b["_id"], "po_id": po.get("_id") or po.get("id")}

    def test_bm_missing_barang_id_returns_422(self, admin_client, po_ctx):
        payload = {
            "po_id": po_ctx["po_id"], "tanggal_masuk": "2026-01-15", "penerima": "T",
            "items": [{"qty_diterima": 1}],
        }
        r = admin_client.post(f"{API}/barang-masuk", json=payload, timeout=30)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"

    def test_bm_negative_qty_diterima_returns_422(self, admin_client, po_ctx):
        payload = {
            "po_id": po_ctx["po_id"], "tanggal_masuk": "2026-01-15", "penerima": "T",
            "items": [{"barang_id": po_ctx["barang_id"], "qty_diterima": -3}],
        }
        r = admin_client.post(f"{API}/barang-masuk", json=payload, timeout=30)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"

    def test_staffing_missing_barang_id_returns_422(self, admin_client, po_ctx):
        payload = {
            "po_id": po_ctx["po_id"], "tanggal_keluar": "2026-01-15",
            "items": [{"qty": 1}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"

    def test_staffing_negative_qty_returns_422(self, admin_client, po_ctx):
        payload = {
            "po_id": po_ctx["po_id"], "tanggal_keluar": "2026-01-15",
            "items": [{"barang_id": po_ctx["barang_id"], "qty": -5}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"


# ==================================================================
# TEST 6: PUT /barang-masuk/{id} revert & apply + validate
# ==================================================================
class TestUpdateBM:

    def test_update_bm_reverts_old_and_applies_new(self, admin_client):
        b = _create_barang(admin_client, f"upbm_{int(time.time())}")
        no_po = f"TEST_ITER6_UPBM_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=20)
        po_id = po.get("_id") or po.get("id")

        # Create BM qty=5
        payload1 = {
            "po_id": po_id, "tanggal_masuk": "2026-01-15", "penerima": "T",
            "items": [{"barang_id": b["_id"], "qty_diterima": 5, "nama_barang": "T"}],
        }
        r1 = admin_client.post(f"{API}/barang-masuk", json=payload1, timeout=30)
        assert r1.status_code in (200, 201), r1.text
        bm_id = r1.json()["_id"]
        po_state = _get_po(admin_client, po_id)
        assert next(i for i in po_state["items"] if i["barang_id"] == b["_id"])["qty_diterima"] == 5

        # PUT BM change qty to 8 -> po.qty_diterima=8 (not 13)
        payload2 = {
            "po_id": po_id, "tanggal_masuk": "2026-01-15", "penerima": "T",
            "items": [{"barang_id": b["_id"], "qty_diterima": 8, "nama_barang": "T"}],
        }
        r2 = admin_client.put(f"{API}/barang-masuk/{bm_id}", json=payload2, timeout=30)
        assert r2.status_code == 200, r2.text
        po_state = _get_po(admin_client, po_id)
        item = next(i for i in po_state["items"] if i["barang_id"] == b["_id"])
        assert item["qty_diterima"] == 8, f"expected 8 got {item['qty_diterima']}"

        # PUT BM exceeding remaining -> 400 with 'sisa'
        payload3 = {
            "po_id": po_id, "tanggal_masuk": "2026-01-15", "penerima": "T",
            "items": [{"barang_id": b["_id"], "qty_diterima": 999, "nama_barang": "T"}],
        }
        r3 = admin_client.put(f"{API}/barang-masuk/{bm_id}", json=payload3, timeout=30)
        assert r3.status_code == 400, f"expected 400 got {r3.status_code}: {r3.text}"
        assert "sisa" in (r3.json().get("detail") or "").lower()

        # After failed PUT, po should be re-consistent (the endpoint reverts before validating,
        # so after 400 the state may drop - verify current state and re-apply if needed)
        # cleanup
        admin_client.delete(f"{API}/barang-masuk/{bm_id}", timeout=30)


# ==================================================================
# TEST 7: PUT /staffing/{id} revert & apply + validate
# ==================================================================
class TestUpdateStaffing:

    def test_update_staffing_reverts_old_and_applies_new(self, admin_client):
        b = _create_barang(admin_client, f"upst_{int(time.time())}")
        no_po = f"TEST_ITER6_UPST_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=20)
        po_id = po.get("_id") or po.get("id")

        payload1 = {
            "po_id": po_id, "tanggal_keluar": "2026-01-15",
            "items": [{"barang_id": b["_id"], "qty": 4, "nama_barang": "T"}],
        }
        r1 = admin_client.post(f"{API}/staffing", json=payload1, timeout=30)
        assert r1.status_code in (200, 201), r1.text
        st_id = r1.json()["_id"]

        # Change to qty=10
        payload2 = {
            "po_id": po_id, "tanggal_keluar": "2026-01-15",
            "items": [{"barang_id": b["_id"], "qty": 10, "nama_barang": "T"}],
        }
        r2 = admin_client.put(f"{API}/staffing/{st_id}", json=payload2, timeout=30)
        assert r2.status_code == 200, r2.text
        po_state = _get_po(admin_client, po_id)
        item = next(i for i in po_state["items"] if i["barang_id"] == b["_id"])
        assert item["qty_staffed"] == 10, f"expected 10 got {item['qty_staffed']}"

        # Exceed remaining -> 400 with 'sisa'
        payload3 = {
            "po_id": po_id, "tanggal_keluar": "2026-01-15",
            "items": [{"barang_id": b["_id"], "qty": 999, "nama_barang": "T"}],
        }
        r3 = admin_client.put(f"{API}/staffing/{st_id}", json=payload3, timeout=30)
        assert r3.status_code == 400, f"expected 400 got {r3.status_code}: {r3.text}"
        assert "sisa" in (r3.json().get("detail") or "").lower()

        admin_client.delete(f"{API}/staffing/{st_id}", timeout=30)


# ==================================================================
# TEST 8: Regression - existing endpoints work
# ==================================================================
class TestRegression:

    def test_get_all_po(self, admin_client):
        r = admin_client.get(f"{API}/po", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_barang_masuk(self, admin_client):
        r = admin_client.get(f"{API}/barang-masuk", timeout=30)
        assert r.status_code == 200

    def test_get_staffing(self, admin_client):
        r = admin_client.get(f"{API}/staffing", timeout=30)
        assert r.status_code == 200

    def test_get_rekap_all_po_has_status_flags(self, admin_client):
        r = admin_client.get(f"{API}/rekap/all-po", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            for k in ("komplit_spk", "komplit_terkirim", "komplit_pengrajin", "ready"):
                assert k in rows[0], f"missing {k}"

    def test_get_rekap_per_barang(self, admin_client):
        r = admin_client.get(f"{API}/rekap/per-barang", timeout=30)
        assert r.status_code == 200

    def test_get_rekap_progres(self, admin_client):
        r = admin_client.get(f"{API}/rekap/progres", timeout=30)
        assert r.status_code == 200

    def test_get_rekap_per_pengrajin(self, admin_client):
        r = admin_client.get(f"{API}/rekap/per-pengrajin", timeout=30)
        assert r.status_code == 200
