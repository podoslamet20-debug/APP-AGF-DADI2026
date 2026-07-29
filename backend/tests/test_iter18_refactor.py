"""
Iter18 - Major refactor test suite
Sequential (do NOT run with xdist -n) because tests share state via class attrs.
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

_STAMP = str(int(time.time()))

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login {email}: {r.status_code} {r.text}"
    return s, r.json()


@pytest.fixture(scope="session")
def admin_sess():
    s, _ = _login("admin@agfdata.com", "admin123")
    return s


@pytest.fixture(scope="session")
def staff_sess():
    s, _ = _login("staff@agfdata.com", "staff123")
    return s


@pytest.fixture(scope="session")
def guest_sess():
    s, _ = _login("tamu@agfdata.com", "tamu123")
    return s


@pytest.fixture(scope="session")
def owner_sess():
    s, u = _login("owner@agfdata.com", "owner123")
    assert u.get("role") == "owner"
    return s


# module-level ctx for cross-test setup
CTX = {}


# ----- 01 Auth -----
def test_01_owner_role_login():
    _, u = _login("owner@agfdata.com", "owner123")
    assert u["role"] == "owner"


def test_02_admin_role_login():
    _, u = _login("admin@agfdata.com", "admin123")
    assert u["role"] == "admin"


# ----- 02 Activity Log RBAC -----
def test_03_admin_activity_log_200(admin_sess):
    r = admin_sess.get(f"{API}/activity-log")
    assert r.status_code == 200


def test_04_owner_activity_log_200(owner_sess):
    r = owner_sess.get(f"{API}/activity-log")
    assert r.status_code == 200, r.text


def test_05_staff_activity_log_403(staff_sess):
    r = staff_sess.get(f"{API}/activity-log")
    assert r.status_code == 403


def test_06_guest_activity_log_403(guest_sess):
    r = guest_sess.get(f"{API}/activity-log")
    assert r.status_code == 403


# ----- 03 Owner read-only -----
def test_07_owner_post_barang_403(owner_sess):
    r = owner_sess.post(f"{API}/barang", json={
        "nama_barang": "TEST_owner_barang", "spesifikasi": "x",
        "harga_pengrajin": 1, "harga_jual": 2
    })
    assert r.status_code == 403


def test_08_owner_post_pengrajin_403(owner_sess):
    r = owner_sess.post(f"{API}/pengrajin", json={"nama": "TEST_owner_p"})
    assert r.status_code == 403


def test_09_owner_post_po_403(owner_sess):
    r = owner_sess.post(f"{API}/po", json={
        "no_po": "TEST_OWNER_PO", "items": [], "catatan": ""
    })
    assert r.status_code == 403


def test_10_owner_post_spk_403(owner_sess):
    r = owner_sess.post(f"{API}/spk", json={
        "no_spk": "TEST_OWNER_SPK", "items": [],
        "catatan_pembayaran": "x", "owner_perusahaan": "y", "deadline": "2026-01-30"
    })
    assert r.status_code == 403, f"got {r.status_code}: {r.text}"


def test_11_owner_read_barang(owner_sess):
    assert owner_sess.get(f"{API}/barang").status_code == 200


def test_12_owner_read_pengrajin(owner_sess):
    assert owner_sess.get(f"{API}/pengrajin").status_code == 200


# ----- 04 Pengrajin CRUD -----
def test_13_get_pengrajin_all_roles(admin_sess, staff_sess, guest_sess, owner_sess):
    for s in (admin_sess, staff_sess, guest_sess, owner_sess):
        r = s.get(f"{API}/pengrajin")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_14_admin_create_pengrajin(admin_sess):
    r = admin_sess.post(f"{API}/pengrajin", json={
        "nama": "TEST_iter18_p_solo", "telepon": "0811",
        "alamat": "Jl Test", "rekening": "BCA 1", "catatan": "t"
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nama"] == "TEST_iter18_p_solo"
    CTX["solo_pid"] = data["_id"]

    r2 = admin_sess.get(f"{API}/pengrajin")
    found = [p for p in r2.json() if p["_id"] == CTX["solo_pid"]]
    assert len(found) == 1 and found[0]["telepon"] == "0811"


def test_15_staff_create_pengrajin_403(staff_sess):
    r = staff_sess.post(f"{API}/pengrajin", json={"nama": "TEST_staff_p"})
    assert r.status_code == 403


def test_16_missing_nama_400(admin_sess):
    r = admin_sess.post(f"{API}/pengrajin", json={"nama": ""})
    assert r.status_code == 400


def test_17_admin_update_pengrajin(admin_sess):
    pid = CTX["solo_pid"]
    r = admin_sess.put(f"{API}/pengrajin/{pid}", json={
        "nama": "TEST_iter18_p_solo_upd", "telepon": "0822",
        "alamat": "x", "rekening": "y", "catatan": "z"
    })
    assert r.status_code == 200
    r2 = admin_sess.get(f"{API}/pengrajin")
    upd = [p for p in r2.json() if p["_id"] == pid][0]
    assert upd["nama"] == "TEST_iter18_p_solo_upd"


def test_18_admin_delete_pengrajin(admin_sess):
    r = admin_sess.delete(f"{API}/pengrajin/{CTX['solo_pid']}")
    assert r.status_code == 200


# ----- 05 Setup for SPK/BM/Progres -----
def test_20_setup_barang_pengrajin_po(admin_sess):
    r = admin_sess.post(f"{API}/barang", json={
        "nama_barang": "TEST_iter18_barang", "spesifikasi": "spec",
        "harga_pengrajin": 100000, "harga_jual": 200000
    })
    assert r.status_code == 200, r.text
    CTX["barang_id"] = r.json()["_id"]

    r1 = admin_sess.post(f"{API}/pengrajin", json={"nama": "TEST_iter18_p1"})
    r2 = admin_sess.post(f"{API}/pengrajin", json={"nama": "TEST_iter18_p2"})
    assert r1.status_code == 200 and r2.status_code == 200
    CTX["p1"] = r1.json()
    CTX["p2"] = r2.json()

    r = admin_sess.post(f"{API}/po", json={
        "no_po": "TEST_ITER18_PO_1785297707",
        "items": [{"barang_id": CTX["barang_id"], "qty": 10, "catatan": ""}],
        "catatan": ""
    })
    assert r.status_code == 200, r.text
    po = r.json()
    CTX["po_id"] = po["_id"]
    CTX["no_po"] = po["no_po"]


def _spk_payload(no_spk, allocations, qty=10):
    return {
        "no_spk": no_spk, "catatan_pembayaran": "cash",
        "owner_perusahaan": "TestOwner", "deadline": "2026-02-01",
        "items": [{
            "no_po": CTX["no_po"], "barang_id": CTX["barang_id"],
            "nama_barang": "TEST_iter18_barang", "spesifikasi": "spec",
            "qty": qty, "allocations": allocations
        }]
    }


# ----- 06 SPK allocations -----
def test_21_spk_missing_allocations_400(admin_sess):
    r = admin_sess.post(f"{API}/spk", json=_spk_payload("TEST_SPK_NOALLOC_1785297707", []))
    assert r.status_code == 400, r.text
    assert "alokasi" in r.text.lower()


def test_22_spk_sum_mismatch_400(admin_sess):
    allocs = [
        {"pengrajin_id": CTX["p1"]["_id"], "pengrajin_nama": CTX["p1"]["nama"], "qty": 3},
        {"pengrajin_id": CTX["p2"]["_id"], "pengrajin_nama": CTX["p2"]["nama"], "qty": 3}
    ]
    r = admin_sess.post(f"{API}/spk", json=_spk_payload("TEST_SPK_MISMATCH_1785297707", allocs))
    assert r.status_code == 400, r.text


def test_23_spk_invalid_pengrajin_400(admin_sess):
    allocs = [{"pengrajin_id": "000000000000000000000000", "pengrajin_nama": "Fake", "qty": 10}]
    r = admin_sess.post(f"{API}/spk", json=_spk_payload("TEST_SPK_BADP_1785297707", allocs))
    assert r.status_code == 400


def test_24_spk_valid_multi_alloc(admin_sess):
    allocs = [
        {"pengrajin_id": CTX["p1"]["_id"], "pengrajin_nama": CTX["p1"]["nama"], "qty": 6},
        {"pengrajin_id": CTX["p2"]["_id"], "pengrajin_nama": CTX["p2"]["nama"], "qty": 4}
    ]
    r = admin_sess.post(f"{API}/spk", json=_spk_payload("TEST_ITER18_SPK_1785297707", allocs))
    assert r.status_code == 200, r.text
    spk = r.json()
    CTX["spk_id"] = spk["_id"]
    assert spk["items"][0]["allocations"][0]["qty"] == 6


# ----- 07 Barang Masuk pengrajin validation -----
def test_31_bm_no_pengrajin_400_or_allowed_legacy(admin_sess):
    """When pengrajin_id omitted, backend allows (legacy path). Should NOT 500."""
    payload = {
        "po_id": CTX["po_id"], "tanggal_masuk": "2026-01-17", "penerima": "T",
        "items": [{"barang_id": CTX["barang_id"], "qty_diterima": 1}]
    }
    r = admin_sess.post(f"{API}/barang-masuk", json=payload)
    # Legacy tolerant: 200 OK. Bookkeep the id if created.
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        CTX["bm_legacy_id"] = r.json()["_id"]


def test_32_bm_exceed_alloc_400(admin_sess):
    payload = {
        "po_id": CTX["po_id"], "tanggal_masuk": "2026-01-17", "penerima": "T",
        "items": [{
            "barang_id": CTX["barang_id"], "pengrajin_id": CTX["p1"]["_id"],
            "pengrajin_nama": CTX["p1"]["nama"], "qty_diterima": 7
        }]
    }
    r = admin_sess.post(f"{API}/barang-masuk", json=payload)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    body = r.text.lower()
    assert "alokasi" in body or "melebihi" in body


def test_33_bm_valid(admin_sess):
    payload = {
        "po_id": CTX["po_id"], "tanggal_masuk": "2026-01-18", "penerima": "T",
        "items": [{
            "barang_id": CTX["barang_id"], "pengrajin_id": CTX["p1"]["_id"],
            "pengrajin_nama": CTX["p1"]["nama"], "qty_diterima": 4
        }]
    }
    r = admin_sess.post(f"{API}/barang-masuk", json=payload)
    assert r.status_code == 200, r.text
    CTX["bm_id"] = r.json()["_id"]


# ----- 08 Progres per pengrajin (NOTE: POST /progres does NOT do per-pengrajin validation) -----
def test_41_grinda_exceed_bm_400(admin_sess):
    """BM total for barang = 4 (or 5 with legacy). Grinda 20 should fail."""
    r = admin_sess.post(f"{API}/progres", json={
        "po_id": CTX["po_id"], "item_id": CTX["barang_id"],
        "pengrajin_id": CTX["p1"]["_id"], "pengrajin_nama": CTX["p1"]["nama"],
        "stage": "grinda", "qty": 20
    })
    assert r.status_code == 400, r.text


def test_42_grinda_valid(admin_sess):
    r = admin_sess.post(f"{API}/progres", json={
        "po_id": CTX["po_id"], "item_id": CTX["barang_id"],
        "pengrajin_id": CTX["p1"]["_id"], "pengrajin_nama": CTX["p1"]["nama"],
        "stage": "grinda", "qty": 3
    })
    assert r.status_code == 200, r.text
    CTX["progres_id"] = r.json()["_id"]


def test_43_servis_exceed_grinda_400(admin_sess):
    r = admin_sess.post(f"{API}/progres", json={
        "po_id": CTX["po_id"], "item_id": CTX["barang_id"],
        "pengrajin_id": CTX["p1"]["_id"], "pengrajin_nama": CTX["p1"]["nama"],
        "stage": "servis", "qty": 10
    })
    assert r.status_code == 400


# ----- 09 Regression -----
def test_51_get_barang(admin_sess):
    assert admin_sess.get(f"{API}/barang").status_code == 200


def test_52_get_po(admin_sess):
    assert admin_sess.get(f"{API}/po").status_code == 200


def test_53_get_rekap_progres(admin_sess):
    assert admin_sess.get(f"{API}/rekap/progres").status_code == 200


def test_54_get_rekap_per_pengrajin(admin_sess):
    r = admin_sess.get(f"{API}/rekap/per-pengrajin")
    assert r.status_code == 200


# ----- 99 Cleanup -----
def test_99_cleanup(admin_sess):
    for path, key in [
        (f"{API}/progres/{CTX.get('progres_id','')}", "progres_id"),
        (f"{API}/barang-masuk/{CTX.get('bm_id','')}", "bm_id"),
        (f"{API}/barang-masuk/{CTX.get('bm_legacy_id','')}", "bm_legacy_id"),
        (f"{API}/spk/{CTX.get('spk_id','')}", "spk_id"),
        (f"{API}/po/{CTX.get('po_id','')}", "po_id"),
        (f"{API}/barang/{CTX.get('barang_id','')}", "barang_id"),
    ]:
        if CTX.get(key):
            admin_sess.delete(path)
    for pk in ("p1", "p2"):
        if CTX.get(pk):
            admin_sess.delete(f"{API}/pengrajin/{CTX[pk]['_id']}")
