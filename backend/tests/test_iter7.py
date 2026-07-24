"""
Iteration 7 backend tests:
1. Staffing limit by qty_ready (packing sum from progres) on POST /api/staffing
2. Valid staffing (qty <= qty_ready) succeeds and increments po.qty_staffed
3. PUT /api/staffing/{id} cap by qty_ready
4. GET /api/po and GET /api/po/{id} inject qty_ready per item
5. BarangCreate/update supports pengrajin_list
6. Guest role must NOT see pengrajin_list on GET /api/barang
7. Regression: iter6 fixes still work (update_po preserves counters, sisa validation)
"""
import os
import time
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
GUEST = {"email": "tamu@agfdata.com", "password": "tamu123"}
STAFF = {"email": "staff@agfdata.com", "password": "staff123"}


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
def _create_barang(client, tag, pengrajin_list=None):
    payload = {
        "nama_barang": f"TEST_ITER7_barang_{tag}",
        "nama_pengrajin": f"PrimaryPengrajin_{tag}",
        "spesifikasi": "spec-iter7",
        "harga_pengrajin": 10000,
        "harga_jual": 15000,
    }
    if pengrajin_list is not None:
        payload["pengrajin_list"] = pengrajin_list
    r = client.post(f"{API}/barang", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_po(client, barang_id, no_po, qty=10):
    payload = {
        "no_po": no_po,
        "items": [{"barang_id": barang_id, "qty": qty, "catatan": ""}],
        "catatan": "iter7",
    }
    r = client.post(f"{API}/po", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _add_barang_masuk(client, po_id, barang_id, qty_diterima):
    payload = {
        "po_id": po_id, "tanggal_masuk": "2026-01-20", "penerima": "IT7",
        "items": [{"barang_id": barang_id, "qty_diterima": qty_diterima, "nama_barang": "T"}],
    }
    r = client.post(f"{API}/barang-masuk", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _set_progres(client, po_id, barang_id, packing):
    payload = {"po_id": po_id, "item_id": barang_id, "grinda": 0, "servis": 0, "finishing": 0, "packing": packing}
    r = client.post(f"{API}/progres", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _get_po(client, po_id):
    r = client.get(f"{API}/po/{po_id}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================
# TEST GROUP 1: Staffing limited by qty_ready (from progres.packing)
# ================================================================
class TestStaffingLimitByReady:

    @pytest.fixture(scope="class")
    def scenario(self, admin_client):
        """Create PO qty=20, BM qty_diterima=15, progres.packing=10 -> qty_ready=10."""
        b = _create_barang(admin_client, f"ready_{int(time.time())}")
        no_po = f"TEST_ITER7_READY_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=20)
        po_id = po.get("_id") or po.get("id")
        _add_barang_masuk(admin_client, po_id, b["_id"], 15)
        _set_progres(admin_client, po_id, b["_id"], 10)
        return {"barang_id": b["_id"], "po_id": po_id}

    def test_po_get_returns_qty_ready(self, admin_client, scenario):
        po = _get_po(admin_client, scenario["po_id"])
        item = next(i for i in po["items"] if i["barang_id"] == scenario["barang_id"])
        assert "qty_ready" in item, "GET /api/po/{id} must include qty_ready"
        assert item["qty_ready"] == 10, f"expected qty_ready=10 got {item.get('qty_ready')}"

    def test_po_list_returns_qty_ready(self, admin_client, scenario):
        r = admin_client.get(f"{API}/po", timeout=30)
        assert r.status_code == 200
        pos = r.json()
        target = next(p for p in pos if p["_id"] == scenario["po_id"])
        item = next(i for i in target["items"] if i["barang_id"] == scenario["barang_id"])
        assert item.get("qty_ready") == 10, f"list GET /api/po qty_ready wrong: {item.get('qty_ready')}"

    def test_staffing_qty_exceeds_ready_returns_400(self, admin_client, scenario):
        """qty=15 > qty_ready=10 -> 400 with 'Ready:' and 'sisa'."""
        payload = {
            "po_id": scenario["po_id"], "tanggal_keluar": "2026-01-21",
            "items": [{"barang_id": scenario["barang_id"], "qty": 15, "nama_barang": "T"}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Ready:" in detail or "ready:" in detail.lower(), f"expected 'Ready:' in detail: {detail}"
        assert "sisa" in detail.lower(), f"expected 'sisa' in detail: {detail}"

        # Verify po.qty_staffed still 0 (not corrupted)
        po = _get_po(admin_client, scenario["po_id"])
        item = next(i for i in po["items"] if i["barang_id"] == scenario["barang_id"])
        assert item.get("qty_staffed", 0) == 0, f"po.qty_staffed corrupted: {item.get('qty_staffed')}"

    def test_staffing_valid_qty_succeeds_and_increments(self, admin_client, scenario):
        """qty=5 <= qty_ready=10 -> success + qty_staffed=5."""
        payload = {
            "po_id": scenario["po_id"], "tanggal_keluar": "2026-01-22",
            "items": [{"barang_id": scenario["barang_id"], "qty": 5, "nama_barang": "T"}],
        }
        r = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        st_id = r.json().get("_id")

        po = _get_po(admin_client, scenario["po_id"])
        item = next(i for i in po["items"] if i["barang_id"] == scenario["barang_id"])
        assert item.get("qty_staffed") == 5, f"expected qty_staffed=5 got {item.get('qty_staffed')}"

        # cleanup this staffing
        admin_client.delete(f"{API}/staffing/{st_id}", timeout=30)

    def test_staffing_update_exceeds_ready_returns_400(self, admin_client, scenario):
        """PUT /api/staffing/{id} to qty > (qty_ready - other_staffed) must return 400 without corrupting counter."""
        # Create valid staffing qty=3
        p1 = {
            "po_id": scenario["po_id"], "tanggal_keluar": "2026-01-23",
            "items": [{"barang_id": scenario["barang_id"], "qty": 3, "nama_barang": "T"}],
        }
        r1 = admin_client.post(f"{API}/staffing", json=p1, timeout=30)
        assert r1.status_code in (200, 201), r1.text
        st_id = r1.json()["_id"]

        # Confirm baseline
        po = _get_po(admin_client, scenario["po_id"])
        item = next(i for i in po["items"] if i["barang_id"] == scenario["barang_id"])
        baseline_staffed = item.get("qty_staffed")
        assert baseline_staffed == 3, f"baseline qty_staffed expected 3 got {baseline_staffed}"

        # PUT to invalid qty=50 > qty_ready=10
        p2 = {
            "po_id": scenario["po_id"], "tanggal_keluar": "2026-01-23",
            "items": [{"barang_id": scenario["barang_id"], "qty": 50, "nama_barang": "T"}],
        }
        r2 = admin_client.put(f"{API}/staffing/{st_id}", json=p2, timeout=30)
        assert r2.status_code == 400, f"expected 400 got {r2.status_code}: {r2.text}"
        detail = r2.json().get("detail", "")
        assert "Ready:" in detail or "ready" in detail.lower(), f"expected 'Ready' in detail: {detail}"

        # po.qty_staffed should NOT be corrupted (still 3)
        po_after = _get_po(admin_client, scenario["po_id"])
        item_after = next(i for i in po_after["items"] if i["barang_id"] == scenario["barang_id"])
        assert item_after.get("qty_staffed") == 3, (
            f"BUG: po.qty_staffed was corrupted by failed PUT. expected 3 got {item_after.get('qty_staffed')}"
        )

        admin_client.delete(f"{API}/staffing/{st_id}", timeout=30)


# ================================================================
# TEST GROUP 2: N10036 napeleon scenario from user prompt (if exists)
# ================================================================
class TestExistingN10036:
    """Verifies the specific scenario mentioned by main agent (best effort - may skip)."""

    def test_n10036_staffing_over_ready(self, admin_client):
        r = admin_client.get(f"{API}/po", timeout=30)
        assert r.status_code == 200
        pos = r.json()
        target = next((p for p in pos if p.get("no_po") == "N10036"), None)
        if not target:
            pytest.skip("N10036 not present in DB")
        napo = next((i for i in target.get("items", []) if "napeleon" in i.get("nama_barang", "").lower()), None)
        if not napo:
            pytest.skip("N10036 has no napeleon item")
        qty_ready = napo.get("qty_ready", 0)
        # Post qty=qty_ready + 50 -> 400 with 'Ready:'
        payload = {
            "po_id": target["_id"], "tanggal_keluar": "2026-01-24",
            "items": [{"barang_id": napo["barang_id"], "qty": qty_ready + 50, "nama_barang": napo["nama_barang"]}],
        }
        r2 = admin_client.post(f"{API}/staffing", json=payload, timeout=30)
        assert r2.status_code == 400, f"expected 400 got {r2.status_code}: {r2.text}"
        detail = r2.json().get("detail", "")
        assert f"Ready: {qty_ready}" in detail or "Ready:" in detail, f"expected 'Ready: {qty_ready}' in detail: {detail}"


# ================================================================
# TEST GROUP 3: Barang pengrajin_list support
# ================================================================
class TestBarangPengrajinList:

    def test_create_barang_with_pengrajin_list_persists(self, admin_client):
        b = _create_barang(admin_client, f"pl_{int(time.time())}", pengrajin_list=["Budi", "Cici"])
        bid = b["_id"]
        assert b.get("pengrajin_list") == ["Budi", "Cici"], f"create response pengrajin_list wrong: {b.get('pengrajin_list')}"

        # GET should return pengrajin_list
        r = admin_client.get(f"{API}/barang/{bid}", timeout=30)
        assert r.status_code == 200
        got = r.json()
        assert got.get("pengrajin_list") == ["Budi", "Cici"], f"GET pengrajin_list wrong: {got.get('pengrajin_list')}"

    def test_update_barang_pengrajin_list(self, admin_client):
        b = _create_barang(admin_client, f"plup_{int(time.time())}", pengrajin_list=["A"])
        bid = b["_id"]
        upd = {
            "nama_barang": b["nama_barang"],
            "nama_pengrajin": b["nama_pengrajin"],
            "spesifikasi": b["spesifikasi"],
            "harga_pengrajin": b["harga_pengrajin"],
            "harga_jual": b["harga_jual"],
            "pengrajin_list": ["A", "B", "C"],
        }
        r = admin_client.put(f"{API}/barang/{bid}", json=upd, timeout=30)
        assert r.status_code == 200, r.text
        r2 = admin_client.get(f"{API}/barang/{bid}", timeout=30)
        assert r2.json().get("pengrajin_list") == ["A", "B", "C"]

    def test_guest_cannot_see_pengrajin_list(self, guest_client, admin_client):
        # Create barang w/ pengrajin_list via admin
        b = _create_barang(admin_client, f"plguest_{int(time.time())}", pengrajin_list=["Hidden1", "Hidden2"])
        bid = b["_id"]
        # Guest GETs the barang list
        r = guest_client.get(f"{API}/barang", timeout=30)
        assert r.status_code == 200
        target = next((it for it in r.json() if it["_id"] == bid), None)
        assert target is not None, "guest could not see the barang"
        assert "pengrajin_list" not in target, f"guest sees pengrajin_list: {target}"
        assert "nama_pengrajin" not in target, "guest should not see nama_pengrajin"

    def test_admin_can_see_pengrajin_list_on_list(self, admin_client):
        b = _create_barang(admin_client, f"pladm_{int(time.time())}", pengrajin_list=["Xx", "Yy"])
        r = admin_client.get(f"{API}/barang", timeout=30)
        target = next((it for it in r.json() if it["_id"] == b["_id"]), None)
        assert target is not None
        assert target.get("pengrajin_list") == ["Xx", "Yy"]


# ================================================================
# TEST GROUP 4: Regression - iter6 fixes still work
# ================================================================
class TestRegression:

    def test_update_po_preserves_counters(self, admin_client):
        b = _create_barang(admin_client, f"regupd_{int(time.time())}")
        no_po = f"TEST_ITER7_REGUPD_{int(time.time())}"
        po = _create_po(admin_client, b["_id"], no_po, qty=20)
        po_id = po.get("_id") or po.get("id")
        _add_barang_masuk(admin_client, po_id, b["_id"], 5)

        # Update PO qty to 25
        upd = {"no_po": no_po, "items": [{"barang_id": b["_id"], "qty": 25, "catatan": ""}], "catatan": ""}
        r = admin_client.put(f"{API}/po/{po_id}", json=upd, timeout=30)
        assert r.status_code == 200

        po_after = _get_po(admin_client, po_id)
        item = next(i for i in po_after["items"] if i["barang_id"] == b["_id"])
        assert item["qty"] == 25
        assert item.get("qty_diterima") == 5, f"BUG: qty_diterima reset: {item.get('qty_diterima')}"

    def test_bm_sisa_validation(self, admin_client):
        b = _create_barang(admin_client, f"regbm_{int(time.time())}")
        po = _create_po(admin_client, b["_id"], f"TEST_ITER7_REGBM_{int(time.time())}", qty=5)
        po_id = po.get("_id") or po.get("id")
        payload = {
            "po_id": po_id, "tanggal_masuk": "2026-01-15", "penerima": "T",
            "items": [{"barang_id": b["_id"], "qty_diterima": 999, "nama_barang": "T"}],
        }
        r = admin_client.post(f"{API}/barang-masuk", json=payload, timeout=30)
        assert r.status_code == 400
        assert "sisa" in r.json().get("detail", "").lower()

    def test_rekap_all_po_has_status_flags(self, admin_client):
        r = admin_client.get(f"{API}/rekap/all-po", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        if rows:
            for k in ("komplit_spk", "komplit_terkirim", "komplit_pengrajin", "ready"):
                assert k in rows[0]

    def test_all_rekap_endpoints_load(self, admin_client):
        for path in ("/rekap/all-po", "/rekap/per-barang", "/rekap/progres", "/rekap/per-pengrajin"):
            r = admin_client.get(f"{API}{path}", timeout=30)
            assert r.status_code == 200, f"{path} failed: {r.status_code}"


# ================================================================
# TEST GROUP 5: Cleanup TEST_ITER7_* records (best-effort)
# ================================================================
def test_cleanup_test_iter7_records(admin_client):
    """Delete leftover TEST_ITER7_* PO and barang records."""
    r = admin_client.get(f"{API}/po", timeout=30)
    for po in r.json():
        if po.get("no_po", "").startswith("TEST_ITER7_"):
            admin_client.delete(f"{API}/po/{po['_id']}", timeout=30)
    r = admin_client.get(f"{API}/barang", timeout=30)
    for b in r.json():
        if b.get("nama_barang", "").startswith("TEST_ITER7_"):
            admin_client.delete(f"{API}/barang/{b['_id']}", timeout=30)
    assert True
