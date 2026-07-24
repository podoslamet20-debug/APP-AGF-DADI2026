"""AGFDATA Iteration 3 Backend Tests - Progres by-po refactor, PDF export, Rekap no_po filter, DELETE 404."""
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
def seeded_po_bm(admin, staff):
    """Create barang -> po -> barang_masuk with qty_diterima=5. Returns (barang, po, bm)."""
    b = admin.post(f"{API}/barang", json={
        "nama_barang": f"TEST_iter3_{uuid.uuid4().hex[:6]}",
        "nama_pengrajin": "TEST_P3", "spesifikasi": "spec",
        "harga_pengrajin": 1.0, "harga_jual": 2.0
    }, timeout=30).json()
    po = admin.post(f"{API}/po", json={
        "no_po": f"TEST_ITER3_{uuid.uuid4().hex[:6]}",
        "items": [{"barang_id": b["_id"], "qty": 20}]
    }, timeout=30).json()
    bm = staff.post(f"{API}/barang-masuk", json={
        "po_id": po["_id"], "tanggal_masuk": "2026-01-20", "penerima": "TEST_iter3",
        "items": [{"barang_id": b["_id"], "nama_barang": b["nama_barang"], "nama_pengrajin": "TEST_P3",
                   "spesifikasi": "spec", "qty_diterima": 5}]
    }, timeout=30).json()
    return b, po, bm


# ================== Progres by-po (new endpoint) ==================
class TestProgresByPo:
    def test_by_po_returns_grouped(self, admin, seeded_po_bm):
        b, po, bm = seeded_po_bm
        r = admin.get(f"{API}/progres/by-po", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Find our PO in response
        target = next((p for p in data if p["po_id"] == po["_id"]), None)
        assert target is not None, "Newly seeded PO with barang_masuk not found in by-po"
        assert target["no_po"] == po["no_po"]
        # items shape
        assert len(target["items"]) >= 1
        it = target["items"][0]
        for k in ["barang_id", "nama_barang", "qty_masuk", "grinda", "servis", "finishing", "packing", "komplit"]:
            assert k in it, f"missing {k}"
        assert it["qty_masuk"] == 5
        assert isinstance(it["komplit"], bool)

    def test_by_po_only_includes_items_with_barang_masuk(self, admin):
        """PO without any barang_masuk should NOT appear."""
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_solo_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "P", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        po = admin.post(f"{API}/po", json={
            "no_po": f"TEST_SOLO_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": b["_id"], "qty": 5}]
        }, timeout=30).json()
        # NO barang_masuk created
        r = admin.get(f"{API}/progres/by-po", timeout=30).json()
        target = next((p for p in r if p["po_id"] == po["_id"]), None)
        assert target is None, "PO with no barang_masuk should NOT appear in by-po"

    def test_by_po_guest_hides_pengrajin(self, guest, seeded_po_bm):
        r = guest.get(f"{API}/progres/by-po", timeout=30)
        assert r.status_code == 200
        for po in r.json():
            for it in po.get("items", []):
                assert "nama_pengrajin" not in it


# ================== POST /api/progres with po_id + packing max enforcement ==================
class TestProgresPackingMax:
    def test_post_progres_with_po_id(self, staff, seeded_po_bm):
        b, po, bm = seeded_po_bm
        r = staff.post(f"{API}/progres", json={
            "po_id": po["_id"], "item_id": b["_id"],
            "grinda": 5, "servis": 3, "finishing": 2, "packing": 4
        }, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["packing"] == 4  # <= qty_masuk=5, no cap needed
        assert data["qty_masuk"] == 5

    def test_packing_capped_at_qty_masuk(self, staff, seeded_po_bm):
        """packing input 100 should be capped at qty_masuk=5."""
        b, po, bm = seeded_po_bm
        r = staff.post(f"{API}/progres", json={
            "po_id": po["_id"], "item_id": b["_id"],
            "grinda": 5, "servis": 5, "finishing": 5, "packing": 100
        }, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["packing"] == 5, f"Expected packing capped to qty_masuk=5, got {data['packing']}"

    def test_grinda_servis_not_capped(self, staff, seeded_po_bm):
        """grinda/servis/finishing should NOT be capped at qty_masuk."""
        b, po, bm = seeded_po_bm
        r = staff.post(f"{API}/progres", json={
            "po_id": po["_id"], "item_id": b["_id"],
            "grinda": 999, "servis": 888, "finishing": 777, "packing": 0
        }, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["grinda"] == 999
        assert data["servis"] == 888
        assert data["finishing"] == 777

    def test_by_po_marks_komplit_when_packing_meets_qty(self, staff, admin):
        """When packing == qty_masuk, komplit=True; otherwise False."""
        # Fresh setup
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_kom_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "P", "spesifikasi": "s",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30).json()
        po = admin.post(f"{API}/po", json={
            "no_po": f"TEST_KOM_{uuid.uuid4().hex[:6]}",
            "items": [{"barang_id": b["_id"], "qty": 10}]
        }, timeout=30).json()
        staff.post(f"{API}/barang-masuk", json={
            "po_id": po["_id"], "tanggal_masuk": "2026-01-21", "penerima": "T",
            "items": [{"barang_id": b["_id"], "nama_barang": b["nama_barang"], "nama_pengrajin": "P",
                       "spesifikasi": "s", "qty_diterima": 3}]
        }, timeout=30)
        # Set packing = 3 (== qty_masuk)
        staff.post(f"{API}/progres", json={
            "po_id": po["_id"], "item_id": b["_id"],
            "grinda": 0, "servis": 0, "finishing": 0, "packing": 3
        }, timeout=30)
        r = admin.get(f"{API}/progres/by-po", timeout=30).json()
        target = next((p for p in r if p["po_id"] == po["_id"]), None)
        assert target is not None
        assert target["items"][0]["komplit"] is True

    def test_progres_guest_forbidden(self, guest, seeded_po_bm):
        b, po, bm = seeded_po_bm
        r = guest.post(f"{API}/progres", json={
            "po_id": po["_id"], "item_id": b["_id"],
            "grinda": 0, "servis": 0, "finishing": 0, "packing": 0
        }, timeout=30)
        assert r.status_code == 403


# ================== GET /api/export/progres/pdf ==================
class TestProgresPDFExport:
    def test_pdf_no_filter(self, admin):
        r = admin.get(f"{API}/export/progres/pdf", timeout=60)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_pdf_with_tanggal_filter(self, admin):
        r = admin.get(f"{API}/export/progres/pdf", params={"tanggal": "2026-01-21"}, timeout=60)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_pdf_requires_auth(self):
        r = requests.get(f"{API}/export/progres/pdf", timeout=30)
        assert r.status_code == 401


# ================== Rekap all-po with no_po filter ==================
class TestRekapNoPoFilter:
    def test_no_po_filter_returns_only_that_po(self, admin, seeded_po_bm):
        b, po, bm = seeded_po_bm
        r = admin.get(f"{API}/rekap/all-po", params={"no_po": po["no_po"]}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, "Filter should return at least the matching PO"
        # All returned rows must match the filter no_po
        for row in data:
            assert row["no_po"] == po["no_po"], f"Filter leaked: got no_po={row['no_po']}, expected {po['no_po']}"

    def test_no_po_filter_no_match_returns_empty(self, admin):
        r = admin.get(f"{API}/rekap/all-po", params={"no_po": "TEST_NON_EXISTENT_PO_XYZ"}, timeout=30)
        assert r.status_code == 200
        assert r.json() == [], "Non-existent no_po should return empty list"

    def test_no_filter_returns_all(self, admin):
        r = admin.get(f"{API}/rekap/all-po", timeout=30)
        assert r.status_code == 200
        # Should return multiple different PO rows
        pos = {row["no_po"] for row in r.json()}
        assert len(pos) >= 1


# ================== DELETE endpoints return 404 for missing id ==================
class TestDelete404:
    """Every DELETE endpoint should return 404 (not 200) when id doesn't exist."""
    FAKE_ID = "507f1f77bcf86cd799439011"  # valid ObjectId format but not in DB

    def test_delete_barang_404(self, admin):
        r = admin.delete(f"{API}/barang/{self.FAKE_ID}", timeout=30)
        assert r.status_code == 404
        assert "not found" in r.json().get("detail", "").lower()

    def test_delete_po_404(self, admin):
        r = admin.delete(f"{API}/po/{self.FAKE_ID}", timeout=30)
        assert r.status_code == 404
        assert "not found" in r.json().get("detail", "").lower()

    def test_delete_bm_404(self, admin):
        r = admin.delete(f"{API}/barang-masuk/{self.FAKE_ID}", timeout=30)
        assert r.status_code == 404
        assert "not found" in r.json().get("detail", "").lower()

    def test_delete_staffing_404(self, admin):
        r = admin.delete(f"{API}/staffing/{self.FAKE_ID}", timeout=30)
        assert r.status_code == 404
        assert "not found" in r.json().get("detail", "").lower()

    def test_delete_spk_404(self, admin):
        r = admin.delete(f"{API}/spk/{self.FAKE_ID}", timeout=30)
        assert r.status_code == 404

    def test_delete_user_404(self, admin):
        r = admin.delete(f"{API}/users/{self.FAKE_ID}", timeout=30)
        assert r.status_code == 404


# ================== Regression: iter1/iter2 core still works ==================
class TestRegression:
    def test_auth_still_works(self, admin, staff, guest):
        for s, expected_role in [(admin, "admin"), (staff, "staff"), (guest, "guest")]:
            r = s.get(f"{API}/auth/me", timeout=30)
            assert r.status_code == 200
            assert r.json()["role"] == expected_role

    def test_barang_crud_regression(self, admin):
        # Create
        b = admin.post(f"{API}/barang", json={
            "nama_barang": f"TEST_reg_{uuid.uuid4().hex[:6]}",
            "nama_pengrajin": "R", "spesifikasi": "r",
            "harga_pengrajin": 1.0, "harga_jual": 2.0
        }, timeout=30)
        assert b.status_code == 200
        bid = b.json()["_id"]
        # Read
        g = admin.get(f"{API}/barang/{bid}", timeout=30)
        assert g.status_code == 200
        # Update
        u = admin.put(f"{API}/barang/{bid}", json={
            "nama_barang": "TEST_reg_updated", "nama_pengrajin": "R2",
            "spesifikasi": "r2", "harga_pengrajin": 3.0, "harga_jual": 4.0
        }, timeout=30)
        assert u.status_code == 200
        # Delete
        d = admin.delete(f"{API}/barang/{bid}", timeout=30)
        assert d.status_code == 200

    def test_exports_regression(self, admin):
        # PDF PO
        r = admin.get(f"{API}/po", timeout=30).json()
        if r:
            p = admin.get(f"{API}/export/po/{r[0]['_id']}/pdf", timeout=60)
            assert p.status_code == 200
            assert p.content[:4] == b"%PDF"

    def test_rekap_endpoints_regression(self, admin):
        for path in ["/rekap/all-po", "/rekap/per-pengrajin", "/rekap/per-barang", "/rekap/progres", "/rekap/staffing-detail"]:
            r = admin.get(f"{API}{path}", timeout=30)
            assert r.status_code == 200, f"{path} failed with {r.status_code}"
