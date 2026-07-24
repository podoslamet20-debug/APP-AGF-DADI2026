"""
Iteration 5 backend tests:
1. PO create/update initializes items[].qty_staffed = 0
2. POST /api/staffing increments qty_staffed
3. PUT /api/staffing reverts old & applies new qty_staffed
4. DELETE /api/staffing reverts qty_staffed (404 if not found)
5. GET /api/rekap/all-po returns komplit_spk, komplit_terkirim, komplit_pengrajin, ready
6. Existing N10036 (has SPK entries) -> komplit_spk True
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://agf-production.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@agfdata.com", "password": "admin123"}


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---------- Helpers ----------
def _create_barang(client, tag):
    payload = {
        "nama_barang": f"TEST_iter5_barang_{tag}",
        "nama_pengrajin": f"TEST_iter5_pengrajin_{tag}",
        "spesifikasi": "spec-iter5",
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
        "catatan": "iter5",
    }
    r = client.post(f"{API}/po", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _get_po(client, po_id):
    r = client.get(f"{API}/po/{po_id}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Tests ----------
class TestPOQtyStaffedInit:
    """(1) create_po and update_po should set qty_staffed=0 on every item"""

    def test_create_po_initializes_qty_staffed_zero(self, admin_client):
        b = _create_barang(admin_client, f"init_{int(time.time())}")
        no_po = f"TEST_ITER5_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=10)
        po_id = po.get("_id") or po.get("id")
        got = _get_po(admin_client, po_id)
        for item in got["items"]:
            assert "qty_staffed" in item, "qty_staffed field missing"
            assert item["qty_staffed"] == 0, f"expected 0 got {item['qty_staffed']}"

    def test_update_po_resets_qty_staffed_to_zero(self, admin_client):
        b = _create_barang(admin_client, f"upd_{int(time.time())}")
        no_po = f"TEST_ITER5_UPD_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=5)
        po_id = po.get("_id") or po.get("id")
        # update PO
        upd = {
            "no_po": no_po,
            "items": [{"barang_id": b["_id"], "qty": 8, "catatan": ""}],
            "catatan": "updated",
        }
        r = admin_client.put(f"{API}/po/{po_id}", json=upd, timeout=30)
        assert r.status_code == 200, r.text
        got = _get_po(admin_client, po_id)
        for item in got["items"]:
            assert item.get("qty_staffed", None) == 0


class TestStaffingQtyStaffed:
    """(2)(3)(4) POST/PUT/DELETE update qty_staffed on PO items"""

    @pytest.fixture(scope="class")
    def po_ctx(self, admin_client):
        b = _create_barang(admin_client, f"st_{int(time.time())}")
        no_po = f"TEST_ITER5_ST_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=20)
        po_id = po.get("_id") or po.get("id")
        return {"barang_id": b["_id"], "no_po": no_po, "po_id": po_id}

    def test_create_staffing_increments_qty_staffed(self, admin_client, po_ctx):
        payload = {
            "po_id": po_ctx["po_id"],
            "tanggal_keluar": "2026-01-15",
            "items": [{"barang_id": po_ctx["barang_id"], "nama_barang": "TEST", "qty": 5}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        st = r.json()
        po_ctx["staffing_id"] = st.get("_id") or st.get("id")
        po = _get_po(admin_client, po_ctx["po_id"])
        # qty_staffed for our item should be 5
        item = next((i for i in po["items"] if i["barang_id"] == po_ctx["barang_id"]), None)
        assert item is not None
        assert item.get("qty_staffed", 0) == 5, f"expected 5 got {item.get('qty_staffed')}"

    def test_create_second_staffing_accumulates(self, admin_client, po_ctx):
        # Add another 3
        payload = {
            "po_id": po_ctx["po_id"],
            "tanggal_keluar": "2026-01-16",
            "items": [{"barang_id": po_ctx["barang_id"], "nama_barang": "TEST", "qty": 3}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        st = r.json()
        po_ctx["staffing_id_2"] = st.get("_id") or st.get("id")
        po = _get_po(admin_client, po_ctx["po_id"])
        item = next((i for i in po["items"] if i["barang_id"] == po_ctx["barang_id"]), None)
        assert item.get("qty_staffed", 0) == 8, f"expected 8 got {item.get('qty_staffed')}"

    def test_update_staffing_reverts_and_applies(self, admin_client, po_ctx):
        st_id = po_ctx.get("staffing_id")
        assert st_id, "no staffing id in ctx"
        # Change first staffing qty from 5 -> 10 (net +5 => total 3 + 10 = 13)
        payload = {
            "po_id": po_ctx["po_id"],
            "tanggal_keluar": "2026-01-15",
            "items": [{"barang_id": po_ctx["barang_id"], "nama_barang": "TEST", "qty": 10}],
        }
        r = admin_client.put(f"{API}/staffing/{st_id}", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        po = _get_po(admin_client, po_ctx["po_id"])
        item = next((i for i in po["items"] if i["barang_id"] == po_ctx["barang_id"]), None)
        assert item.get("qty_staffed", 0) == 13, f"expected 13 got {item.get('qty_staffed')}"

    def test_delete_staffing_reverts(self, admin_client, po_ctx):
        st_id = po_ctx.get("staffing_id_2")
        r = admin_client.delete(f"{API}/staffing/{st_id}", timeout=30)
        assert r.status_code == 200, r.text
        po = _get_po(admin_client, po_ctx["po_id"])
        item = next((i for i in po["items"] if i["barang_id"] == po_ctx["barang_id"]), None)
        # was 13, deleted second staffing (qty=3) -> 10
        assert item.get("qty_staffed", 0) == 10, f"expected 10 got {item.get('qty_staffed')}"
        # cleanup: delete remaining staffing
        r2 = admin_client.delete(f"{API}/staffing/{po_ctx['staffing_id']}", timeout=30)
        assert r2.status_code == 200

    def test_delete_staffing_not_found_returns_404(self, admin_client):
        r = admin_client.delete(f"{API}/staffing/507f1f77bcf86cd799439011", timeout=30)
        assert r.status_code == 404


class TestRekapAllPOStatus:
    """(5)(6) GET /api/rekap/all-po returns four status booleans"""

    def test_rekap_all_po_returns_status_fields(self, admin_client):
        r = admin_client.get(f"{API}/rekap/all-po", timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0, "no rekap rows"
        for row in rows:
            for k in ("komplit_spk", "komplit_terkirim", "komplit_pengrajin", "ready"):
                assert k in row, f"missing key {k} in row {row}"
                assert isinstance(row[k], bool), f"{k} not bool: {type(row[k])}"

    def test_n10036_has_komplit_spk_true(self, admin_client):
        r = admin_client.get(f"{API}/rekap/all-po", params={"no_po": "N10036"}, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) > 0, "N10036 not found"
        for row in rows:
            assert row["komplit_spk"] is True, f"N10036 row should have komplit_spk=True: {row}"

    def test_new_po_without_spk_has_komplit_spk_false(self, admin_client):
        # Create fresh PO -> shouldn't have SPK => komplit_spk False, komplit_terkirim False
        b = _create_barang(admin_client, f"nospk_{int(time.time())}")
        no_po = f"TEST_ITER5_NOSPK_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=4)
        r = admin_client.get(f"{API}/rekap/all-po", params={"no_po": no_po}, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) > 0
        for row in rows:
            assert row["komplit_spk"] is False
            assert row["komplit_terkirim"] is False
            assert row["komplit_pengrajin"] is False
            assert row["ready"] is False

    def test_komplit_terkirim_flips_true_when_qty_staffed_meets_qty(self, admin_client):
        # Create PO qty=3 then create staffing qty=3 -> komplit_terkirim True
        b = _create_barang(admin_client, f"kt_{int(time.time())}")
        no_po = f"TEST_ITER5_KT_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=3)
        po_id = po.get("_id") or po.get("id")
        payload = {
            "po_id": po_id,
            "tanggal_keluar": "2026-01-17",
            "items": [{"barang_id": b["_id"], "nama_barang": "TEST", "qty": 3}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        st_id = r.json().get("_id")

        r2 = admin_client.get(f"{API}/rekap/all-po", params={"no_po": no_po}, timeout=30)
        assert r2.status_code == 200
        rows = r2.json()
        assert len(rows) > 0
        for row in rows:
            assert row["komplit_terkirim"] is True, f"expected komplit_terkirim True: {row}"
        # cleanup
        admin_client.delete(f"{API}/staffing/{st_id}", timeout=30)
