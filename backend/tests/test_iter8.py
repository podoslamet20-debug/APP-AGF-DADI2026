"""
Iteration 8 backend tests - Progres Barang changes:
1. POST /api/progres clamps ALL 4 stages (grinda/servis/finishing/packing) at qty_masuk
   (previously only packing was clamped)
2. POST /api/progres accepts tanggal and persists; default = today
3. GET /api/progres/by-po items include 'tanggal' field
4. Progres.packing → PO.qty_ready sync
5. Manual mode: po_id=None + metadata fields (nama_barang, nama_pengrajin, spesifikasi, gambar_path)
6. Regression: N10036 napeleon scenario
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
GUEST = {"email": "tamu@agfdata.com", "password": "tamu123"}


@pytest.fixture(scope="session")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def guest_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=GUEST, timeout=30)
    if r.status_code != 200:
        pytest.skip("guest login failed")
    return s


# ---------- helpers ----------
def _create_barang(client, tag):
    payload = {
        "nama_barang": f"TEST_ITER8_barang_{tag}",
        "nama_pengrajin": f"Pengrajin_{tag}",
        "spesifikasi": "spec-iter8",
        "harga_pengrajin": 10000,
        "harga_jual": 15000,
    }
    r = client.post(f"{API}/barang", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_po(client, barang_id, no_po, qty=10):
    payload = {"no_po": no_po, "items": [{"barang_id": barang_id, "qty": qty, "catatan": ""}], "catatan": "iter8"}
    r = client.post(f"{API}/po", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _add_barang_masuk(client, po_id, barang_id, qty_diterima):
    payload = {
        "po_id": po_id, "tanggal_masuk": "2026-01-20", "penerima": "IT8",
        "items": [{"barang_id": barang_id, "qty_diterima": qty_diterima, "nama_barang": "T"}],
    }
    r = client.post(f"{API}/barang-masuk", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _get_po(client, po_id):
    r = client.get(f"{API}/po/{po_id}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================
# TEST GROUP 1: All 4 stages capped at qty_masuk (iter8 core change)
# ================================================================
class TestAllStagesCappedByQtyMasuk:

    @pytest.fixture(scope="class")
    def scenario(self, admin_client):
        """PO qty=500, BM qty_diterima=400 => qty_masuk=400."""
        b = _create_barang(admin_client, f"cap_{int(time.time())}")
        po = _create_po(admin_client, b["_id"], f"TEST_ITER8_CAP_{int(time.time())}", qty=500)
        po_id = po.get("_id") or po.get("id")
        _add_barang_masuk(admin_client, po_id, b["_id"], 400)
        return {"barang_id": b["_id"], "po_id": po_id, "qty_masuk": 400}

    def test_grinda_clamped_to_qty_masuk(self, admin_client, scenario):
        """POST grinda=99999, qty_masuk=400 => stored grinda=400."""
        payload = {
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "grinda": 99999, "servis": 0, "finishing": 0, "packing": 0,
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc.get("grinda") == 400, f"grinda not clamped: {doc.get('grinda')} (expected 400)"

    def test_servis_clamped_to_qty_masuk(self, admin_client, scenario):
        payload = {
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "grinda": 400, "servis": 99999, "finishing": 0, "packing": 0,
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        assert r.json().get("servis") == 400, f"servis not clamped: {r.json().get('servis')}"

    def test_finishing_clamped_to_qty_masuk(self, admin_client, scenario):
        payload = {
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "grinda": 400, "servis": 400, "finishing": 99999, "packing": 0,
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        assert r.json().get("finishing") == 400

    def test_packing_clamped_to_qty_masuk(self, admin_client, scenario):
        payload = {
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "grinda": 400, "servis": 400, "finishing": 400, "packing": 99999,
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        assert r.json().get("packing") == 400

    def test_all_four_over_at_once(self, admin_client, scenario):
        payload = {
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "grinda": 5000, "servis": 5000, "finishing": 5000, "packing": 5000,
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert d.get("grinda") == 400 and d.get("servis") == 400 and d.get("finishing") == 400 and d.get("packing") == 400, d


# ================================================================
# TEST GROUP 2: tanggal support
# ================================================================
class TestTanggalPersistence:

    @pytest.fixture(scope="class")
    def scenario(self, admin_client):
        b = _create_barang(admin_client, f"tgl_{int(time.time())}")
        po = _create_po(admin_client, b["_id"], f"TEST_ITER8_TGL_{int(time.time())}", qty=30)
        po_id = po.get("_id") or po.get("id")
        _add_barang_masuk(admin_client, po_id, b["_id"], 20)
        return {"barang_id": b["_id"], "po_id": po_id}

    def test_tanggal_saved_and_returned_from_post(self, admin_client, scenario):
        payload = {
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "grinda": 5, "servis": 0, "finishing": 0, "packing": 0,
            "tanggal": "2026-02-08",
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        assert r.json().get("tanggal") == "2026-02-08"

    def test_tanggal_default_to_today_when_omitted(self, admin_client):
        # Fresh barang/PO so no existing progres record
        b = _create_barang(admin_client, f"tgl2_{int(time.time())}")
        po = _create_po(admin_client, b["_id"], f"TEST_ITER8_TGL2_{int(time.time())}", qty=10)
        po_id = po.get("_id") or po.get("id")
        _add_barang_masuk(admin_client, po_id, b["_id"], 5)
        payload = {
            "po_id": po_id, "item_id": b["_id"],
            "grinda": 1, "servis": 0, "finishing": 0, "packing": 0,
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert r.json().get("tanggal") == today, f"expected today={today} got {r.json().get('tanggal')}"

    def test_by_po_includes_tanggal_field(self, admin_client, scenario):
        # Set tanggal via post
        admin_client.post(f"{API}/progres", json={
            "po_id": scenario["po_id"], "item_id": scenario["barang_id"],
            "grinda": 3, "packing": 0, "tanggal": "2026-02-10"
        }, timeout=30)
        r = admin_client.get(f"{API}/progres/by-po", timeout=30)
        assert r.status_code == 200
        target_po = next((p for p in r.json() if p["po_id"] == scenario["po_id"]), None)
        assert target_po is not None, "PO not in by-po response"
        item = next((i for i in target_po["items"] if i["barang_id"] == scenario["barang_id"]), None)
        assert item is not None
        assert "tanggal" in item, f"'tanggal' missing in by-po item: {item.keys()}"
        assert item["tanggal"] == "2026-02-10", f"tanggal wrong: {item.get('tanggal')}"


# ================================================================
# TEST GROUP 3: Progres.packing -> PO.qty_ready sync
# ================================================================
class TestProgresStaffingSync:

    def test_packing_reflects_as_qty_ready(self, admin_client):
        b = _create_barang(admin_client, f"sync_{int(time.time())}")
        po = _create_po(admin_client, b["_id"], f"TEST_ITER8_SYNC_{int(time.time())}", qty=50)
        po_id = po.get("_id") or po.get("id")
        _add_barang_masuk(admin_client, po_id, b["_id"], 30)

        # Set packing=25
        r = admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "packing": 25
        }, timeout=30)
        assert r.status_code in (200, 201)

        # GET /api/po -> qty_ready should be 25
        po_get = _get_po(admin_client, po_id)
        item = next(i for i in po_get["items"] if i["barang_id"] == b["_id"])
        assert item.get("qty_ready") == 25, f"qty_ready sync failed: {item.get('qty_ready')}"

        # Update packing=15
        admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": b["_id"], "packing": 15
        }, timeout=30)
        po_get2 = _get_po(admin_client, po_id)
        item2 = next(i for i in po_get2["items"] if i["barang_id"] == b["_id"])
        assert item2.get("qty_ready") == 15, f"qty_ready update failed: {item2.get('qty_ready')}"


# ================================================================
# TEST GROUP 4: Manual mode (po_id=None + metadata)
# ================================================================
class TestManualMode:

    def test_manual_progres_no_po_saves_metadata(self, admin_client):
        b = _create_barang(admin_client, f"man_{int(time.time())}")
        payload = {
            "po_id": None,
            "item_id": b["_id"],
            "grinda": 5, "servis": 3, "finishing": 2, "packing": 1,
            "tanggal": "2026-02-05",
            "nama_barang": "Manual_Override_Name",
            "nama_pengrajin": "Manual_Pengrajin",
            "spesifikasi": "Manual_Spec",
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        # In manual mode qty_masuk=0 => stages clamped to 0
        # Server behavior: qty_masuk=0 when po_id empty -> _cap returns 0
        assert doc.get("tanggal") == "2026-02-05"
        # Metadata preserved
        assert doc.get("nama_barang") == "Manual_Override_Name"
        assert doc.get("nama_pengrajin") == "Manual_Pengrajin"
        assert doc.get("spesifikasi") == "Manual_Spec"

    def test_manual_progres_stages_zeroed_when_no_po(self, admin_client):
        """In manual mode qty_masuk=0 so all stages get clamped to 0 (current behavior)."""
        b = _create_barang(admin_client, f"manzero_{int(time.time())}")
        payload = {
            "po_id": None, "item_id": b["_id"],
            "grinda": 10, "servis": 10, "finishing": 10, "packing": 10,
        }
        r = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        # All zeroed because qty_masuk=0 in manual/no-po mode
        assert d.get("grinda") == 0 and d.get("packing") == 0, f"manual clamp behavior: {d}"


# ================================================================
# TEST GROUP 5: N10036 napeleon scenario
# ================================================================
class TestN10036Scenario:

    def test_n10036_grinda_clamp_and_qty_ready_flow(self, admin_client):
        """Verify seed PO N10036 napeleon: qty_masuk=400 => grinda clamped at 400."""
        r = admin_client.get(f"{API}/po", timeout=30)
        assert r.status_code == 200
        pos = r.json()
        target = next((p for p in pos if p.get("no_po") == "N10036"), None)
        if not target:
            pytest.skip("N10036 not present in DB")
        napo = next((i for i in target.get("items", []) if "napeleon" in i.get("nama_barang", "").lower()), None)
        if not napo:
            pytest.skip("N10036 has no napeleon")
        po_id = target["_id"]
        barang_id = napo["barang_id"]

        # Capture existing state to restore later
        orig_packing = None
        try:
            rr = admin_client.get(f"{API}/progres", timeout=30)
            for p in rr.json():
                if p.get("po_id") == po_id and p.get("item_id") == barang_id:
                    orig_packing = p.get("packing", 0)
                    orig_grinda = p.get("grinda", 0)
                    orig_servis = p.get("servis", 0)
                    orig_finishing = p.get("finishing", 0)
                    orig_tanggal = p.get("tanggal", "")
                    break
        except Exception:
            pass

        # POST grinda=99999 -> clamped at qty_masuk
        payload = {"po_id": po_id, "item_id": barang_id, "grinda": 99999,
                   "servis": 0, "finishing": 0, "packing": 0}
        r2 = admin_client.post(f"{API}/progres", json=payload, timeout=30)
        assert r2.status_code in (200, 201), r2.text
        clamped = r2.json().get("grinda")
        qty_masuk = r2.json().get("qty_masuk")
        assert clamped == qty_masuk, f"grinda={clamped} qty_masuk={qty_masuk}"
        assert clamped > 0, f"expected clamp>0 got {clamped}"

        # Restore original values if we had them
        if orig_packing is not None:
            admin_client.post(f"{API}/progres", json={
                "po_id": po_id, "item_id": barang_id,
                "grinda": orig_grinda, "servis": orig_servis,
                "finishing": orig_finishing, "packing": orig_packing,
                "tanggal": orig_tanggal,
            }, timeout=30)


# ================================================================
# TEST GROUP 6: Regression - other iter7 features still work
# ================================================================
class TestRegression:

    def test_all_rekap_5_tabs_load(self, admin_client):
        for path in ("/rekap/all-po", "/rekap/per-barang", "/rekap/progres",
                     "/rekap/per-pengrajin", "/staffing"):
            r = admin_client.get(f"{API}{path}", timeout=30)
            assert r.status_code == 200, f"{path} failed: {r.status_code}"

    def test_staffing_still_capped_by_qty_ready(self, admin_client):
        b = _create_barang(admin_client, f"reg_{int(time.time())}")
        po = _create_po(admin_client, b["_id"], f"TEST_ITER8_REG_{int(time.time())}", qty=20)
        po_id = po.get("_id") or po.get("id")
        _add_barang_masuk(admin_client, po_id, b["_id"], 15)
        admin_client.post(f"{API}/progres", json={"po_id": po_id, "item_id": b["_id"], "packing": 10}, timeout=30)
        # staffing qty=15 > qty_ready=10 -> 400
        r = admin_client.post(f"{API}/staffing", json={
            "po_id": po_id, "tanggal_keluar": "2026-01-21",
            "items": [{"barang_id": b["_id"], "qty": 15, "nama_barang": "T"}]
        }, timeout=30)
        assert r.status_code == 400
        assert "Ready" in r.json().get("detail", "") or "ready" in r.json().get("detail", "").lower()

    def test_guest_no_pengrajin_on_barang(self, guest_client, admin_client):
        r = guest_client.get(f"{API}/barang", timeout=30)
        assert r.status_code == 200
        for it in r.json()[:5]:
            assert "nama_pengrajin" not in it, f"guest sees nama_pengrajin: {it}"


# ================================================================
# CLEANUP: Delete TEST_ITER8_* records
# ================================================================
def test_zzz_cleanup_test_iter8_records(admin_client):
    """Delete TEST_ITER8_* POs and barang. Runs last due to zzz prefix."""
    # Delete progres records for TEST_ITER8 POs
    r_pos = admin_client.get(f"{API}/po", timeout=30)
    test_po_ids = [p["_id"] for p in r_pos.json() if p.get("no_po", "").startswith("TEST_ITER8_")]
    # Delete POs (which also cleans dependent BM/staffing via cascade if any, but progres remains)
    for po_id in test_po_ids:
        admin_client.delete(f"{API}/po/{po_id}", timeout=30)
    # Delete barang
    r_b = admin_client.get(f"{API}/barang", timeout=30)
    for b in r_b.json():
        if b.get("nama_barang", "").startswith("TEST_ITER8_"):
            admin_client.delete(f"{API}/barang/{b['_id']}", timeout=30)
    assert True
