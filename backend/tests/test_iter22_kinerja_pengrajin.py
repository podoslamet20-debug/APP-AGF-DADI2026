"""Iter22 - Dashboard Kinerja Pengrajin ranking tests"""
import os
import pytest
import requests
from datetime import datetime, timezone

def _load_url():
    v = os.environ.get('REACT_APP_BACKEND_URL')
    if v: return v
    try:
        with open('/app/frontend/.env') as f:
            for ln in f:
                if ln.startswith('REACT_APP_BACKEND_URL='):
                    return ln.split('=', 1)[1].strip()
    except Exception:
        pass
    return ''
BASE_URL = _load_url().rstrip('/')
API = f"{BASE_URL}/api"


def login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return login("admin@agfdata.com", "admin123")


@pytest.fixture(scope="module")
def guest():
    return login("tamu@agfdata.com", "tamu123")


def test_guest_forbidden(guest):
    r = guest.get(f"{API}/dashboard/kinerja-pengrajin?month=2026-02")
    assert r.status_code == 403


def test_default_month_current(admin):
    r = admin.get(f"{API}/dashboard/kinerja-pengrajin")
    assert r.status_code == 200
    data = r.json()
    current = datetime.now(timezone.utc).strftime("%Y-%m")
    assert data["month"] == current
    assert "pengrajin" in data
    assert isinstance(data["pengrajin"], list)


def test_response_shape(admin):
    r = admin.get(f"{API}/dashboard/kinerja-pengrajin?month=2026-02")
    assert r.status_code == 200
    data = r.json()
    assert data["month"] == "2026-02"
    assert isinstance(data["pengrajin"], list)
    for p in data["pengrajin"]:
        for k in ["pengrajin_id", "pengrajin_nama", "qty_selesai", "qty_masuk",
                  "spk_qty_month", "on_time_count", "total_spk_month",
                  "on_time_rate", "rank", "badge"]:
            assert k in p, f"missing key {k} in {p}"
        assert p["badge"] in ["MVP", "Produktif", "Perlu Improvement", "Belum ada aktivitas"]


def test_sorted_and_ranked(admin):
    r = admin.get(f"{API}/dashboard/kinerja-pengrajin?month=2026-02")
    data = r.json()
    lst = data["pengrajin"]
    for i, p in enumerate(lst):
        assert p["rank"] == i + 1
    # Sort validation: qty_selesai desc, then on_time_rate desc
    for i in range(len(lst) - 1):
        a, b = lst[i], lst[i + 1]
        if a["qty_selesai"] == b["qty_selesai"]:
            ra = a["on_time_rate"] or 0
            rb = b["on_time_rate"] or 0
            assert ra >= rb
        else:
            assert a["qty_selesai"] >= b["qty_selesai"]


def test_on_time_rate_scenario(admin):
    """Seed 1 pengrajin, 1 SPK (deadline 2026-02-28 qty=10) + packing entries totalling 10 by 2026-02-27 -> on_time_rate=100"""
    import uuid
    tag = uuid.uuid4().hex[:8]
    month = "2026-02"
    # Create pengrajin
    pj = admin.post(f"{API}/pengrajin", json={"nama": f"TEST_ITER22_PJ_{tag}", "telepon": "0812", "alamat": "x"})
    assert pj.status_code in (200, 201), pj.text
    pj_id = pj.json().get("_id") or pj.json().get("id")

    # Create barang
    br = admin.post(f"{API}/barang", json={
        "nama_barang": f"TEST_ITER22_BR_{tag}", "spesifikasi": "spec",
        "harga_pengrajin": 1000, "harga_jual": 2000
    })
    assert br.status_code in (200, 201), br.text
    br_id = br.json().get("_id") or br.json().get("id")

    no_po = f"TEST_ITER22_PO_{tag}"
    no_spk = f"TEST_ITER22_SPK_{tag}"
    # Create PO with this barang
    po_payload = {
        "no_po": no_po,
        "items": [{"barang_id": br_id, "qty": 10}],
    }
    po = admin.post(f"{API}/po", json=po_payload)
    assert po.status_code in (200, 201), po.text
    po_id = po.json().get("_id") or po.json().get("id")

    # Create SPK
    spk_payload = {
        "no_spk": no_spk,
        "catatan_pembayaran": "-",
        "owner_perusahaan": "TestCo",
        "deadline": "2026-02-28",
        "items": [{
            "no_po": no_po, "barang_id": br_id, "nama_barang": f"TEST_ITER22_BR_{tag}",
            "pengrajin_id": pj_id, "pengrajin_nama": f"TEST_ITER22_PJ_{tag}", "qty": 10
        }],
    }
    spk = admin.post(f"{API}/spk", json=spk_payload)
    assert spk.status_code in (200, 201), spk.text
    spk_id = spk.json().get("_id") or spk.json().get("id")

    # Create barang_masuk so stages can be advanced
    bm = admin.post(f"{API}/barang-masuk", json={
        "po_id": po_id, "tanggal_masuk": "2026-02-05", "penerima": "admin",
        "items": [{"barang_id": br_id, "qty_diterima": 10,
                    "pengrajin_id": pj_id, "pengrajin_nama": f"TEST_ITER22_PJ_{tag}"}]
    })
    assert bm.status_code in (200, 201), bm.text
    bm_id = bm.json().get("_id") or bm.json().get("id")

    # Create packing progres - must go through all stages first (grinda->servis->finishing->packing)
    for stage in ["grinda", "servis", "finishing"]:
        pr = admin.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": br_id, "pengrajin_id": pj_id,
            "stage": stage, "qty": 10, "tanggal": "2026-02-15"
        })
        assert pr.status_code in (200, 201), f"{stage}: {pr.text}"
    for tgl, qty in [("2026-02-20", 6), ("2026-02-27", 4)]:
        pr = admin.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": br_id, "pengrajin_id": pj_id,
            "stage": "packing", "qty": qty, "tanggal": tgl
        })
        assert pr.status_code in (200, 201), pr.text

    # Query kinerja
    r = admin.get(f"{API}/dashboard/kinerja-pengrajin?month={month}")
    assert r.status_code == 200
    data = r.json()
    row = next((p for p in data["pengrajin"] if p["pengrajin_id"] == pj_id), None)
    assert row is not None, f"pengrajin {pj_id} not in result"

    try:
        assert row["qty_selesai"] == 10, f"expected 10 got {row['qty_selesai']}"
        assert row["total_spk_month"] == 1
        assert row["on_time_count"] == 1
        assert row["on_time_rate"] == 100.0 or row["on_time_rate"] == 100
        # rank 1 (highest qty_selesai) and badge = MVP (top3)
        assert row["rank"] == 1
        assert row["badge"] == "MVP"
    finally:
        # cleanup
        admin.delete(f"{API}/spk/{spk_id}")
        try:
            admin.delete(f"{API}/barang-masuk/{bm_id}")
        except Exception:
            pass
        admin.delete(f"{API}/po/{po_id}")
        admin.delete(f"{API}/pengrajin/{pj_id}")
        admin.delete(f"{API}/barang/{br_id}")
        # delete progres entries - best effort via list+delete
        try:
            prs = admin.get(f"{API}/progres").json()
            for p in prs:
                if p.get("pengrajin_id") == pj_id:
                    pid = p.get("_id") or p.get("id")
                    admin.delete(f"{API}/progres/{pid}")
        except Exception:
            pass


def test_badge_logic(admin):
    r = admin.get(f"{API}/dashboard/kinerja-pengrajin?month=2026-02")
    data = r.json()
    lst = data["pengrajin"]
    total = len(lst)
    for p in lst:
        if p["qty_selesai"] == 0 and (p["on_time_rate"] or 0) == 0:
            assert p["badge"] == "Belum ada aktivitas"
        elif p["rank"] <= 3:
            assert p["badge"] == "MVP"
        elif p["rank"] <= max(3, total // 2):
            assert p["badge"] == "Produktif"
        else:
            assert p["badge"] == "Perlu Improvement"
