"""AGFDATA Iteration 2 Backend Tests - User Management, Delete endpoints, new Rekap tabs."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://agf-production.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@agfdata.com", "admin123")


@pytest.fixture(scope="module")
def staff():
    return _login("staff@agfdata.com", "staff123")


@pytest.fixture(scope="module")
def guest():
    return _login("tamu@agfdata.com", "tamu123")


@pytest.fixture(scope="module")
def admin_id(admin):
    r = admin.get(f"{API}/auth/me", timeout=30)
    return r.json()["_id"]


# ================== User Management (new in iter 2) ==================
class TestUserManagement:
    """User CRUD - admin only."""

    def test_list_users_admin(self, admin):
        r = admin.get(f"{API}/users", timeout=30)
        assert r.status_code == 200
        users = r.json()
        emails = {u["email"] for u in users}
        assert "admin@agfdata.com" in emails
        assert "staff@agfdata.com" in emails
        assert "tamu@agfdata.com" in emails
        # ObjectId should not leak - _id must be a string
        for u in users:
            assert isinstance(u["_id"], str)
            assert "password_hash" not in u

    def test_list_users_staff_forbidden(self, staff):
        r = staff.get(f"{API}/users", timeout=30)
        assert r.status_code == 403

    def test_list_users_guest_forbidden(self, guest):
        r = guest.get(f"{API}/users", timeout=30)
        assert r.status_code == 403

    def test_create_user_admin(self, admin):
        payload = {
            "email": f"TEST_user_{uuid.uuid4().hex[:6]}@example.com",
            "password": "secret123",
            "name": "TEST_NewUser",
            "role": "staff",
        }
        r = admin.post(f"{API}/users", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == payload["email"].lower()
        assert data["role"] == "staff"
        assert "_id" in data
        # verify persisted via list
        rl = admin.get(f"{API}/users", timeout=30)
        emails = {u["email"] for u in rl.json()}
        assert payload["email"].lower() in emails

    def test_create_user_staff_forbidden(self, staff):
        r = staff.post(f"{API}/users", json={
            "email": "TEST_forbidden@example.com", "password": "x", "name": "y", "role": "staff"
        }, timeout=30)
        assert r.status_code == 403

    def test_create_user_duplicate_email(self, admin):
        email = f"TEST_dup_{uuid.uuid4().hex[:6]}@example.com"
        payload = {"email": email, "password": "s", "name": "n", "role": "staff"}
        r1 = admin.post(f"{API}/users", json=payload, timeout=30)
        assert r1.status_code == 200
        r2 = admin.post(f"{API}/users", json=payload, timeout=30)
        assert r2.status_code == 400

    def test_create_user_invalid_role(self, admin):
        r = admin.post(f"{API}/users", json={
            "email": f"TEST_ir_{uuid.uuid4().hex[:6]}@example.com",
            "password": "s", "name": "n", "role": "superadmin"
        }, timeout=30)
        assert r.status_code == 400

    def test_update_user(self, admin):
        # create then update
        email = f"TEST_upd_{uuid.uuid4().hex[:6]}@example.com"
        c = admin.post(f"{API}/users", json={"email": email, "password": "p1", "name": "OldName", "role": "staff"}, timeout=30)
        uid = c.json()["_id"]
        r = admin.put(f"{API}/users/{uid}", json={"name": "NewName", "role": "guest"}, timeout=30)
        assert r.status_code == 200
        # verify
        users = admin.get(f"{API}/users", timeout=30).json()
        found = next((u for u in users if u["_id"] == uid), None)
        assert found is not None
        assert found["name"] == "NewName"
        assert found["role"] == "guest"

    def test_delete_user(self, admin):
        email = f"TEST_del_{uuid.uuid4().hex[:6]}@example.com"
        c = admin.post(f"{API}/users", json={"email": email, "password": "p", "name": "n", "role": "staff"}, timeout=30)
        uid = c.json()["_id"]
        r = admin.delete(f"{API}/users/{uid}", timeout=30)
        assert r.status_code == 200
        # verify removal
        users = admin.get(f"{API}/users", timeout=30).json()
        assert not any(u["_id"] == uid for u in users)

    def test_delete_user_cannot_delete_self(self, admin, admin_id):
        r = admin.delete(f"{API}/users/{admin_id}", timeout=30)
        assert r.status_code == 400, f"Should refuse self-delete, got {r.status_code}"


# ================== Delete Endpoints (new in iter 2) ==================
class TestDeleteEndpoints:
    def test_delete_barang_admin(self, admin):
        # create then delete
        r = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_delB_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "X", "spesifikasi": "y",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30)
        bid = r.json()["_id"]
        d = admin.delete(f"{API}/barang/{bid}", timeout=30)
        assert d.status_code == 200
        # verify: get by id should 404 (or empty)
        g = admin.get(f"{API}/barang/{bid}", timeout=30)
        assert g.status_code == 404

    def test_delete_barang_staff_forbidden(self, staff, admin):
        # need existing barang id
        r = admin.get(f"{API}/barang", timeout=30)
        if not r.json():
            pytest.skip("no barang exists")
        bid = r.json()[0]["_id"]
        d = staff.delete(f"{API}/barang/{bid}", timeout=30)
        assert d.status_code == 403

    def test_delete_po_admin(self, admin):
        # create a barang + po, then delete po
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_delPO_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "P", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        po = admin.post(f"{API}/po", json={
            "no_po": f"TEST_PODEL_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": b["_id"], "qty": 3}]
        }, timeout=30).json()
        d = admin.delete(f"{API}/po/{po['_id']}", timeout=30)
        assert d.status_code == 200
        # verify
        g = admin.get(f"{API}/po/{po['_id']}", timeout=30)
        assert g.status_code == 404

    def test_delete_po_staff_forbidden(self, staff, admin):
        r = admin.get(f"{API}/po", timeout=30)
        if not r.json():
            pytest.skip("no po")
        d = staff.delete(f"{API}/po/{r.json()[0]['_id']}", timeout=30)
        assert d.status_code == 403

    def test_delete_spk_admin(self, admin):
        # create barang + spk
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_spkDel_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "P", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        spk = admin.post(f"{API}/spk", json={
            "no_spk": f"TEST_SPKDEL_{uuid.uuid4().hex[:6]}",
            "items": [{
                "barang_id": b["_id"], "nama_barang": b["nama_barang"],
                "spesifikasi": "s", "nama_pengrajin": "P", "qty": 2
            }],
            "catatan_pembayaran": "x", "owner_perusahaan": "y", "deadline": "2026-01-30"
        }, timeout=30).json()
        d = admin.delete(f"{API}/spk/{spk['_id']}", timeout=30)
        assert d.status_code == 200

    def test_delete_barang_masuk_reverts_po_qty(self, staff, admin):
        # setup: barang + po
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_bmRev_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "P", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        po = admin.post(f"{API}/po", json={
            "no_po": f"TEST_bmRevPO_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": b["_id"], "qty": 10}]
        }, timeout=30).json()
        # BM w/ qty 4
        bm = staff.post(f"{API}/barang-masuk", json={
            "po_id": po["_id"], "tanggal_masuk": "2026-01-15", "penerima": "TEST_p",
            "items": [{
                "barang_id": b["_id"], "nama_barang": b["nama_barang"],
                "nama_pengrajin": "P", "qty_diterima": 4
            }]
        }, timeout=30).json()
        # verify PO qty_diterima=4
        po_after = admin.get(f"{API}/po/{po['_id']}", timeout=30).json()
        assert po_after["items"][0]["qty_diterima"] == 4
        # delete BM
        d = staff.delete(f"{API}/barang-masuk/{bm['_id']}", timeout=30)
        assert d.status_code == 200, d.text
        # verify PO qty_diterima reverted to 0
        po_final = admin.get(f"{API}/po/{po['_id']}", timeout=30).json()
        assert po_final["items"][0]["qty_diterima"] == 0

    def test_delete_staffing_admin(self, admin):
        r = admin.get(f"{API}/staffing", timeout=30)
        if not r.json():
            pytest.skip("no staffing")
        st = r.json()[0]
        d = admin.delete(f"{API}/staffing/{st['_id']}", timeout=30)
        assert d.status_code == 200


# ================== PUT/Edit endpoints (new/expanded in iter 2) ==================
class TestUpdateEndpoints:
    def test_update_barang(self, admin):
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_edit_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "Old", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        r = admin.put(f"{API}/barang/{b['_id']}", json={
            "nama_barang": "TEST_edited", "nama_pengrajin": "New",
            "spesifikasi": "new", "harga_pengrajin": 5.0, "harga_jual": 10.0
        }, timeout=30)
        assert r.status_code == 200
        # verify
        g = admin.get(f"{API}/barang/{b['_id']}", timeout=30).json()
        assert g["nama_barang"] == "TEST_edited"
        assert g["nama_pengrajin"] == "New"

    def test_update_barang_masuk(self, staff, admin):
        # setup
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_editBM_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "P", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        po = admin.post(f"{API}/po", json={
            "no_po": f"TEST_editBMPO_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": b["_id"], "qty": 20}]
        }, timeout=30).json()
        bm = staff.post(f"{API}/barang-masuk", json={
            "po_id": po["_id"], "tanggal_masuk": "2026-01-01", "penerima": "P1",
            "items": [{"barang_id": b["_id"], "nama_barang": b["nama_barang"], "nama_pengrajin": "P", "qty_diterima": 3}]
        }, timeout=30).json()
        # update qty to 7
        r = staff.put(f"{API}/barang-masuk/{bm['_id']}", json={
            "po_id": po["_id"], "tanggal_masuk": "2026-01-02", "penerima": "P2",
            "items": [{"barang_id": b["_id"], "nama_barang": b["nama_barang"], "nama_pengrajin": "P", "qty_diterima": 7}]
        }, timeout=30)
        assert r.status_code == 200, r.text
        # verify PO qty_diterima is 7 (reverted -3, added 7)
        po_after = admin.get(f"{API}/po/{po['_id']}", timeout=30).json()
        assert po_after["items"][0]["qty_diterima"] == 7


# ================== New Rekap tabs (per-barang, progres, staffing-detail) ==================
class TestRekapNewTabs:
    def test_rekap_per_barang_admin(self, admin):
        r = admin.get(f"{API}/rekap/per-barang", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # each row must have qty_masuk, qty_packing, kurang, nama_barang
        for row in data:
            for k in ["nama_barang", "qty_masuk", "qty_packing", "kurang"]:
                assert k in row
            # nama_pengrajin visible for admin
            # (skip - may not exist if item lacked one)

    def test_rekap_per_barang_guest_hides_pengrajin(self, guest):
        r = guest.get(f"{API}/rekap/per-barang", timeout=30)
        assert r.status_code == 200
        for row in r.json():
            assert "nama_pengrajin" not in row

    def test_rekap_progres_admin(self, admin):
        r = admin.get(f"{API}/rekap/progres", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for row in data:
            for k in ["no_po", "nama_barang", "qty_masuk", "grinda", "servis", "finishing", "packing", "komplit"]:
                assert k in row, f"missing key {k} in {row}"
            assert isinstance(row["komplit"], bool)

    def test_rekap_progres_guest_hides_pengrajin(self, guest):
        r = guest.get(f"{API}/rekap/progres", timeout=30)
        assert r.status_code == 200
        for row in r.json():
            assert "nama_pengrajin" not in row

    def test_rekap_staffing_detail_admin(self, admin):
        r = admin.get(f"{API}/rekap/staffing-detail", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_rekap_staffing_detail_date_range(self, admin):
        r = admin.get(f"{API}/rekap/staffing-detail", params={
            "tanggal_from": "2026-01-01", "tanggal_to": "2026-12-31"
        }, timeout=30)
        assert r.status_code == 200
        for row in r.json():
            assert row["tanggal_keluar"] >= "2026-01-01"
            assert row["tanggal_keluar"] <= "2026-12-31"

    def test_rekap_all_po_uses_kurang_kirim(self, admin):
        """The response should use 'kurang_kirim' key (renamed from 'remaining')."""
        r = admin.get(f"{API}/rekap/all-po", timeout=30)
        assert r.status_code == 200
        data = r.json()
        if data:
            row = data[0]
            assert "kurang_kirim" in row, f"Expected 'kurang_kirim' field; got keys: {list(row.keys())}"
            assert "remaining" not in row, "Old 'remaining' field should be removed"

    def test_rekap_all_po_staffing_join_fixed(self, admin, staff):
        """After iteration 1 fix, qty_staffing should reflect actual staffing rows."""
        # Setup barang, po, staffing tied together
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_joinB_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "P", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        po = admin.post(f"{API}/po", json={
            "no_po": f"TEST_joinPO_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": b["_id"], "qty": 50}]
        }, timeout=30).json()
        staff.post(f"{API}/staffing", json={
            "po_id": po["_id"], "tanggal_keluar": "2026-01-20",
            "items": [{"barang_id": b["_id"], "nama_barang": b["nama_barang"], "qty": 8}]
        }, timeout=30)
        # rekap
        r = admin.get(f"{API}/rekap/all-po", timeout=30).json()
        row = next((x for x in r if x["no_po"] == po["no_po"] and x["nama_barang"] == b["nama_barang"]), None)
        assert row is not None
        assert row["qty_staffing"] == 8, f"Expected qty_staffing=8, got {row['qty_staffing']}"
        assert row["kurang_kirim"] == 42


# ================== Export endpoints - PDF/Excel for new areas ==================
class TestExports:
    def test_export_barang_masuk_pdf(self, admin):
        r = admin.get(f"{API}/barang-masuk", timeout=30)
        if not r.json():
            pytest.skip("no barang-masuk")
        bm_id = r.json()[0]["_id"]
        p = admin.get(f"{API}/export/barang-masuk/{bm_id}/pdf", timeout=60)
        assert p.status_code == 200
        assert p.content[:4] == b"%PDF"

    def test_export_staffing_pdf(self, admin):
        r = admin.get(f"{API}/staffing", timeout=30)
        if not r.json():
            pytest.skip("no staffing")
        st_id = r.json()[0]["_id"]
        p = admin.get(f"{API}/export/staffing/{st_id}/pdf", timeout=60)
        assert p.status_code == 200
        assert p.content[:4] == b"%PDF"

    def test_export_spk_pdf(self, admin):
        r = admin.get(f"{API}/spk", timeout=30)
        if not r.json():
            pytest.skip("no spk")
        spk_id = r.json()[0]["_id"]
        p = admin.get(f"{API}/export/spk/{spk_id}/pdf", timeout=60)
        assert p.status_code == 200
        assert p.content[:4] == b"%PDF"


# ================== Search on GET endpoints ==================
class TestSearch:
    def test_search_po(self, admin):
        r = admin.get(f"{API}/po", params={"search": "TEST_"}, timeout=30)
        assert r.status_code == 200
        # every result must contain TEST_ substring
        for po in r.json():
            assert "TEST_" in po.get("no_po", "")

    def test_search_spk(self, admin):
        r = admin.get(f"{API}/spk", params={"search": "TEST_"}, timeout=30)
        assert r.status_code == 200
        for spk in r.json():
            assert "TEST_" in spk.get("no_spk", "")


# ================== Guest full-hide checks for iter 2 ==================
class TestGuestHides:
    def test_guest_cannot_access_users(self, guest):
        r = guest.get(f"{API}/users", timeout=30)
        assert r.status_code == 403

    def test_guest_barang_no_price_no_pengrajin(self, guest):
        r = guest.get(f"{API}/barang", timeout=30).json()
        for b in r:
            assert "harga_pengrajin" not in b
            assert "harga_jual" not in b
            assert "nama_pengrajin" not in b

    def test_guest_po_no_price_no_pengrajin(self, guest):
        r = guest.get(f"{API}/po", timeout=30).json()
        for po in r:
            for it in po.get("items", []):
                assert "harga_pengrajin" not in it
                assert "nama_pengrajin" not in it

    def test_guest_spk_no_price_no_pengrajin(self, guest):
        r = guest.get(f"{API}/spk", timeout=30).json()
        for spk in r:
            for it in spk.get("items", []):
                assert "harga_pengrajin" not in it
                assert "nama_pengrajin" not in it

    def test_guest_rekap_all_po_no_pengrajin(self, guest):
        r = guest.get(f"{API}/rekap/all-po", timeout=30).json()
        for row in r:
            assert "nama_pengrajin" not in row
