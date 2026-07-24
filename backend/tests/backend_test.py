"""AGFDATA Backend API Tests - covers auth, RBAC, CRUD, exports."""
import os
import io
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://agf-production.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ----------------- Fixtures -----------------
def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def admin():
    return _login("admin@agfdata.com", "admin123")


@pytest.fixture(scope="session")
def staff():
    return _login("staff@agfdata.com", "staff123")


@pytest.fixture(scope="session")
def guest():
    return _login("tamu@agfdata.com", "tamu123")


@pytest.fixture(scope="session")
def seeded_barang(admin):
    """Create a seed barang shared across tests."""
    payload = {
        "nama_barang": f"TEST_Kursi_{uuid.uuid4().hex[:6]}",
        "nama_pengrajin": "TEST_Pengrajin_A",
        "spesifikasi": "Kayu jati 40x40",
        "harga_pengrajin": 100000.0,
        "harga_jual": 150000.0,
        "catatan": "seed",
    }
    r = admin.post(f"{API}/barang", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def seeded_po(admin, seeded_barang):
    payload = {
        "no_po": f"TEST_PO_{uuid.uuid4().hex[:6]}",
        "items": [{"barang_id": seeded_barang["_id"], "qty": 10, "catatan": "x"}],
        "catatan": "seed po",
    }
    r = admin.post(f"{API}/po", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ================== Auth Tests ==================
class TestAuth:
    def test_login_admin_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": "admin@agfdata.com", "password": "admin123"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "admin"
        assert data["email"] == "admin@agfdata.com"
        assert "access_token" in r.cookies or r.cookies.get("access_token") is not None

    def test_login_staff_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": "staff@agfdata.com", "password": "staff123"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "staff"

    def test_login_guest_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": "tamu@agfdata.com", "password": "tamu123"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "guest"

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "admin@agfdata.com", "password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_me_unauthenticated(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_me_authenticated(self, admin):
        r = admin.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_logout(self, admin):
        s = _login("admin@agfdata.com", "admin123")
        r = s.post(f"{API}/auth/logout", timeout=30)
        assert r.status_code == 200


# ================== Barang RBAC/CRUD ==================
class TestBarang:
    def test_create_barang_admin(self, admin):
        payload = {
            "nama_barang": f"TEST_Meja_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "TEST_Pengrajin_B",
            "spesifikasi": "Kayu jati",
            "harga_pengrajin": 50000.0,
            "harga_jual": 75000.0,
        }
        r = admin.post(f"{API}/barang", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["nama_barang"] == payload["nama_barang"]
        assert "_id" in data
        # Verify persistence via GET
        rg = admin.get(f"{API}/barang/{data['_id']}", timeout=30)
        assert rg.status_code == 200
        assert rg.json()["nama_barang"] == payload["nama_barang"]

    def test_create_barang_staff_forbidden(self, staff):
        r = staff.post(f"{API}/barang", json={
            "nama_barang": "TEST_x", "nama_pengrajin": "y", "spesifikasi": "z",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30)
        assert r.status_code == 403

    def test_create_barang_guest_forbidden(self, guest):
        r = guest.post(f"{API}/barang", json={
            "nama_barang": "TEST_x", "nama_pengrajin": "y", "spesifikasi": "z",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30)
        assert r.status_code == 403

    def test_list_barang_admin_has_prices(self, admin, seeded_barang):
        r = admin.get(f"{API}/barang", timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0
        target = next((i for i in items if i["_id"] == seeded_barang["_id"]), None)
        assert target is not None
        assert "harga_pengrajin" in target
        assert "harga_jual" in target
        assert "nama_pengrajin" in target

    def test_list_barang_staff_hides_price_shows_pengrajin(self, staff, seeded_barang):
        r = staff.get(f"{API}/barang", timeout=30)
        assert r.status_code == 200
        items = r.json()
        target = next((i for i in items if i["_id"] == seeded_barang["_id"]), None)
        assert target is not None
        assert "harga_pengrajin" not in target
        assert "harga_jual" not in target
        assert "nama_pengrajin" in target

    def test_list_barang_guest_hides_price_and_pengrajin(self, guest, seeded_barang):
        r = guest.get(f"{API}/barang", timeout=30)
        assert r.status_code == 200
        items = r.json()
        target = next((i for i in items if i["_id"] == seeded_barang["_id"]), None)
        assert target is not None
        assert "harga_pengrajin" not in target
        assert "harga_jual" not in target
        assert "nama_pengrajin" not in target

    def test_search_barang(self, admin, seeded_barang):
        # Search by prefix TEST_
        r = admin.get(f"{API}/barang", params={"search": "TEST_"}, timeout=30)
        assert r.status_code == 200
        assert any(i["_id"] == seeded_barang["_id"] for i in r.json())


# ================== PO Tests ==================
class TestPO:
    def test_create_po_admin(self, admin, seeded_barang):
        payload = {
            "no_po": f"TEST_POx_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": seeded_barang["_id"], "qty": 5, "catatan": ""}],
            "catatan": "",
        }
        r = admin.post(f"{API}/po", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["items"][0]["nama_barang"] == seeded_barang["nama_barang"]
        assert data["items"][0]["qty"] == 5
        assert data["items"][0]["qty_diterima"] == 0
        # Verify persist
        rg = admin.get(f"{API}/po/{data['_id']}", timeout=30)
        assert rg.status_code == 200

    def test_create_po_staff_forbidden(self, staff, seeded_barang):
        r = staff.post(f"{API}/po", json={
            "no_po": f"TEST_POx_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": seeded_barang["_id"], "qty": 1}],
        }, timeout=30)
        assert r.status_code == 403

    def test_update_po_admin(self, admin, seeded_po, seeded_barang):
        payload = {
            "no_po": seeded_po["no_po"],
            "items": [{"barang_id": seeded_barang["_id"], "qty": 20, "catatan": "updated"}],
            "catatan": "updated",
        }
        r = admin.put(f"{API}/po/{seeded_po['_id']}", json=payload, timeout=30)
        assert r.status_code == 200
        # Verify persist
        rg = admin.get(f"{API}/po/{seeded_po['_id']}", timeout=30)
        assert rg.status_code == 200
        assert rg.json()["items"][0]["qty"] == 20

    def test_po_list_staff_no_prices(self, staff):
        r = staff.get(f"{API}/po", timeout=30)
        assert r.status_code == 200
        for po in r.json():
            for it in po.get("items", []):
                assert "harga_pengrajin" not in it
                assert "harga_jual" not in it

    def test_po_list_guest_no_prices_no_pengrajin(self, guest):
        r = guest.get(f"{API}/po", timeout=30)
        assert r.status_code == 200
        for po in r.json():
            for it in po.get("items", []):
                assert "harga_pengrajin" not in it
                assert "nama_pengrajin" not in it


# ================== Barang Masuk ==================
class TestBarangMasuk:
    def test_create_barang_masuk_staff_allowed(self, staff, admin, seeded_po, seeded_barang):
        # Refresh po to get updated qty from prior test
        rp = admin.get(f"{API}/po/{seeded_po['_id']}", timeout=30)
        po = rp.json()
        item = po["items"][0]
        payload = {
            "po_id": seeded_po["_id"],
            "tanggal_masuk": "2026-01-15",
            "penerima": "TEST_Staff",
            "items": [{
                "barang_id": item["barang_id"],
                "nama_barang": item["nama_barang"],
                "nama_pengrajin": item["nama_pengrajin"],
                "qty_diterima": 3,
            }],
        }
        r = staff.post(f"{API}/barang-masuk", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        # Verify PO qty_diterima increment
        rp2 = admin.get(f"{API}/po/{seeded_po['_id']}", timeout=30)
        po2 = rp2.json()
        assert po2["items"][0]["qty_diterima"] >= 3

    def test_barang_masuk_guest_forbidden(self, guest, seeded_po):
        r = guest.post(f"{API}/barang-masuk", json={
            "po_id": seeded_po["_id"], "tanggal_masuk": "2026-01-01",
            "penerima": "x", "items": [],
        }, timeout=30)
        assert r.status_code == 403

    def test_list_barang_masuk(self, admin):
        r = admin.get(f"{API}/barang-masuk", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ================== Staffing ==================
class TestStaffing:
    def test_create_staffing_staff_allowed(self, staff, seeded_po, seeded_barang):
        payload = {
            "po_id": seeded_po["_id"],
            "tanggal_keluar": "2026-01-16",
            "items": [{
                "barang_id": seeded_barang["_id"],
                "nama_barang": seeded_barang["nama_barang"],
                "qty": 2,
            }],
        }
        r = staff.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code == 200

    def test_staffing_guest_forbidden(self, guest, seeded_po):
        r = guest.post(f"{API}/staffing", json={
            "po_id": seeded_po["_id"], "tanggal_keluar": "2026-01-01", "items": []
        }, timeout=30)
        assert r.status_code == 403


# ================== SPK ==================
class TestSPK:
    def test_create_spk_admin(self, admin, seeded_barang):
        payload = {
            "no_spk": f"TEST_SPK_{uuid.uuid4().hex[:6]}",
            "items": [{
                "barang_id": seeded_barang["_id"],
                "nama_barang": seeded_barang["nama_barang"],
                "spesifikasi": seeded_barang["spesifikasi"],
                "nama_pengrajin": seeded_barang["nama_pengrajin"],
                "qty": 5,
            }],
            "catatan_pembayaran": "test bayar",
            "owner_perusahaan": "Test Owner",
            "deadline": "2026-02-01",
        }
        r = admin.post(f"{API}/spk", json=payload, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["no_spk"] == payload["no_spk"]
        # Also try update
        spk_id = data["_id"]
        payload["catatan_pembayaran"] = "updated bayar"
        r2 = admin.put(f"{API}/spk/{spk_id}", json=payload, timeout=30)
        assert r2.status_code == 200

    def test_spk_staff_forbidden(self, staff):
        r = staff.post(f"{API}/spk", json={
            "no_spk": "TEST_SPKfail", "items": [], "catatan_pembayaran": "",
            "owner_perusahaan": "x", "deadline": "2026-01-01"
        }, timeout=30)
        assert r.status_code == 403


# ================== Progres ==================
class TestProgres:
    def test_update_progres_staff(self, staff):
        payload = {
            "barang_masuk_id": "test_bm_id_1",
            "item_id": "test_item_1",
            "grinda": 5, "servis": 4, "finishing": 3, "packing": 2
        }
        r = staff.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code == 200
        # idempotent update
        payload["packing"] = 5
        r2 = staff.post(f"{API}/progres", json=payload, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["packing"] == 5

    def test_progres_guest_forbidden(self, guest):
        r = guest.post(f"{API}/progres", json={
            "barang_masuk_id": "x", "item_id": "y",
            "grinda": 0, "servis": 0, "finishing": 0, "packing": 0
        }, timeout=30)
        assert r.status_code == 403


# ================== Rekap ==================
class TestRekap:
    def test_rekap_all_po(self, admin):
        r = admin.get(f"{API}/rekap/all-po", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_rekap_per_pengrajin_admin(self, admin):
        r = admin.get(f"{API}/rekap/per-pengrajin", timeout=30)
        assert r.status_code == 200

    def test_rekap_per_pengrajin_guest_forbidden(self, guest):
        r = guest.get(f"{API}/rekap/per-pengrajin", timeout=30)
        assert r.status_code == 403


# ================== Export ==================
class TestExport:
    def test_export_po_pdf(self, admin, seeded_po):
        r = admin.get(f"{API}/export/po/{seeded_po['_id']}/pdf", timeout=60)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_export_barang_masuk_excel(self, admin):
        r = admin.get(f"{API}/export/barang-masuk/excel", timeout=60)
        assert r.status_code == 200
        ctype = r.headers.get("content-type", "")
        assert "spreadsheet" in ctype or "excel" in ctype
        # XLSX = zip signature PK
        assert r.content[:2] == b"PK"
