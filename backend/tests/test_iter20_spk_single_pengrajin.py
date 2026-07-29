"""
Iter20 - SPK single-pengrajin-per-item + cross-SPK aggregate validation
+ Rekap/Staffing filters + Export staffing PDF/Excel with filters.
Sequential (state shared via CTX).
"""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

_TS = str(int(time.time()))
CTX = {}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@agfdata.com", "admin123")


# ---------- Setup: create barang, 4 pengrajin, PO qty=400 ----------

def test_00_setup_barang(admin):
    r = admin.post(f"{API}/barang", json={
        "nama_barang": f"ITER20_Napoleon_{_TS}",
        "spesifikasi": "Test spec",
        "nama_pengrajin": "",
        "harga_pengrajin": 100000,
        "harga_jual": 200000,
    })
    assert r.status_code == 200, r.text
    b = r.json()
    CTX["barang_id"] = b.get("_id") or b.get("id")
    CTX["barang_nama"] = b["nama_barang"]
    assert CTX["barang_id"]


def test_01_setup_pengrajin(admin):
    ids = []
    for name in ["ITER20_Kemat", "ITER20_Roni", "ITER20_Marten", "ITER20_Extra"]:
        r = admin.post(f"{API}/pengrajin", json={"nama": f"{name}_{_TS}"})
        assert r.status_code == 200, r.text
        p = r.json()
        ids.append(p.get("_id") or p.get("id"))
    CTX["p1"], CTX["p2"], CTX["p3"], CTX["p4"] = ids


def test_02_setup_po(admin):
    no_po = f"ITER20_PO_{_TS}"
    CTX["no_po"] = no_po
    r = admin.post(f"{API}/po", json={
        "no_po": no_po,
        "tanggal_terima": "2026-01-01",
        "nama_pemesan": "TEST",
        "items": [{
            "barang_id": CTX["barang_id"],
            "nama_barang": CTX["barang_nama"],
            "qty": 400,
        }],
    })
    assert r.status_code == 200, r.text
    po = r.json()
    CTX["po_id"] = po.get("_id") or po.get("id")
    assert CTX["po_id"]


# ---------- SPK create with single-pengrajin ----------

def _spk_payload(no_spk, pengrajin_id, qty):
    return {
        "no_spk": no_spk,
        "catatan_pembayaran": "cash",
        "owner_perusahaan": "AGF",
        "deadline": "2026-02-01",
        "items": [{
            "barang_id": CTX["barang_id"],
            "nama_barang": CTX["barang_nama"],
            "qty": qty,
            "no_po": CTX["no_po"],
            "pengrajin_id": pengrajin_id,
            "harga": 100000,
        }],
    }


def test_10_spk_create_single_pengrajin_success(admin):
    r = admin.post(f"{API}/spk", json=_spk_payload(f"ITER20_SPK001_{_TS}", CTX["p1"], 300))
    assert r.status_code == 200, r.text
    doc = r.json()
    CTX["spk1_id"] = doc.get("_id") or doc.get("id")
    it = doc["items"][0]
    # Auto-populate pengrajin_nama from DB
    assert it.get("pengrajin_nama"), f"pengrajin_nama should be auto-populated, got: {it}"
    assert "ITER20_Kemat" in it["pengrajin_nama"]


def test_11_spk_create_second_pengrajin_success(admin):
    r = admin.post(f"{API}/spk", json=_spk_payload(f"ITER20_SPK002_{_TS}", CTX["p2"], 50))
    assert r.status_code == 200, r.text
    CTX["spk2_id"] = r.json().get("_id")


def test_12_spk_create_third_reach_po_qty(admin):
    r = admin.post(f"{API}/spk", json=_spk_payload(f"ITER20_SPK003_{_TS}", CTX["p3"], 50))
    assert r.status_code == 200, r.text
    CTX["spk3_id"] = r.json().get("_id")


def test_13_spk_create_over_po_qty_400(admin):
    r = admin.post(f"{API}/spk", json=_spk_payload(f"ITER20_SPK004_{_TS}", CTX["p4"], 1))
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    msg = body.get("detail", "")
    assert "melebihi qty PO" in msg, f"missing 'melebihi qty PO': {msg}"
    assert "Sudah dialokasikan" in msg, f"missing 'Sudah dialokasikan': {msg}"
    assert "Sisa alokasi: 0" in msg, f"missing 'Sisa alokasi: 0': {msg}"


# ---------- SPK edit with exclude_spk_id ----------

def test_20_spk_edit_over_po_qty(admin):
    # SPK1 was 300, try to bump to 350 → total would be 350+50+50=450 > 400 → 400
    r = admin.put(f"{API}/spk/{CTX['spk1_id']}", json=_spk_payload(f"ITER20_SPK001_{_TS}", CTX["p1"], 350))
    assert r.status_code == 400, f"Expected 400 on over-quota edit: {r.status_code} {r.text}"


def test_21_spk_edit_under_po_qty(admin):
    # SPK1 300 → 200: total 200+50+50=300 < 400 → OK
    r = admin.put(f"{API}/spk/{CTX['spk1_id']}", json=_spk_payload(f"ITER20_SPK001_{_TS}", CTX["p1"], 200))
    assert r.status_code == 200, f"Expected 200 on under-quota edit: {r.status_code} {r.text}"
    # restore to 300 for later tests
    r = admin.put(f"{API}/spk/{CTX['spk1_id']}", json=_spk_payload(f"ITER20_SPK001_{_TS}", CTX["p1"], 300))
    assert r.status_code == 200


# ---------- SPK validation ----------

def test_30_spk_missing_pengrajin_id(admin):
    payload = _spk_payload(f"ITER20_BAD1_{_TS}", CTX["p1"], 1)
    payload["items"][0]["pengrajin_id"] = None
    r = admin.post(f"{API}/spk", json=payload)
    assert r.status_code == 400, r.text


def test_31_spk_invalid_pengrajin_id(admin):
    payload = _spk_payload(f"ITER20_BAD2_{_TS}", "507f1f77bcf86cd799439011", 1)  # bogus objectid
    r = admin.post(f"{API}/spk", json=payload)
    assert r.status_code == 400, r.text
    assert "tidak ditemukan" in r.json().get("detail", "")


# ---------- Rekap filters ----------

def test_40_rekap_all_po_filter_no_po(admin):
    r = admin.get(f"{API}/rekap/all-po", params={"no_po": CTX["no_po"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert all(row["no_po"] == CTX["no_po"] for row in data), data


def test_41_rekap_all_po_filter_barang_and_pengrajin(admin):
    r = admin.get(f"{API}/rekap/all-po", params={
        "no_po": CTX["no_po"], "barang_id": CTX["barang_id"], "pengrajin_id": CTX["p1"],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    # p1 has SPK on this barang so row should be present
    assert len(data) >= 1, data


def test_42_rekap_all_po_filter_pengrajin_not_alloc(admin):
    # p4 has NO SPK for this PO+barang → filtered out
    r = admin.get(f"{API}/rekap/all-po", params={
        "no_po": CTX["no_po"], "barang_id": CTX["barang_id"], "pengrajin_id": CTX["p4"],
    })
    assert r.status_code == 200, r.text
    assert r.json() == [], r.json()


def test_43_rekap_per_pengrajin_filter(admin):
    r = admin.get(f"{API}/rekap/per-pengrajin", params={
        "no_po": CTX["no_po"], "pengrajin_id": CTX["p1"],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    # Should have exactly 1 pengrajin group (p1) with spk_qty=300
    assert len(data) >= 1
    p1_rows = [d for d in data if d.get("pengrajin_id") == CTX["p1"]]
    assert p1_rows, data
    assert p1_rows[0]["spk_qty"] == 300


# ---------- Staffing filter ----------

def test_50_staffing_filter_params_accepted(admin):
    # Verify that all filter params are accepted (200) and returns a list.
    # (Not creating a staffing here because it requires "Ready" packing.)
    r = admin.get(f"{API}/staffing", params={
        "no_po": CTX["no_po"],
        "date_from": "2026-01-01",
        "date_to": "2026-01-31",
        "pengrajin_id": CTX["p1"],
        "barang_id": CTX["barang_id"],
    })
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_51_staffing_filter_pengrajin_none(admin):
    r = admin.get(f"{API}/staffing", params={
        "no_po": CTX["no_po"],
        "pengrajin_id": CTX["p4"],  # no staffing for p4
    })
    assert r.status_code == 200, r.text
    assert r.json() == []


# ---------- Export staffing PDF/Excel with filters ----------

def test_60_export_staffing_pdf_with_filter(admin):
    r = admin.get(f"{API}/export/staffing/pdf", params={
        "no_po": CTX["no_po"], "pengrajin_id": CTX["p1"],
    })
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 500


def test_61_export_staffing_excel_with_filter(admin):
    r = admin.get(f"{API}/export/staffing/excel", params={
        "no_po": CTX["no_po"], "pengrajin_id": CTX["p1"],
    })
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "spreadsheet" in ct or "excel" in ct or "octet-stream" in ct, ct
    assert len(r.content) > 500


# ---------- BM aggregated qty per pengrajin across multiple SPKs ----------
# Uses fresh barang + PO to avoid state pollution
def test_70_bm_aggregates_across_spks(admin):
    barang_r = admin.post(f"{API}/barang", json={
        "nama_barang": f"ITER20_BM_{_TS}", "spesifikasi": "", "nama_pengrajin": "",
        "harga_pengrajin": 1, "harga_jual": 1,
    })
    assert barang_r.status_code == 200
    barang = barang_r.json()
    bid = barang.get("_id") or barang.get("id")
    no_po2 = f"ITER20_PO2_{_TS}"
    po_r = admin.post(f"{API}/po", json={
        "no_po": no_po2, "tanggal_terima": "2026-01-01", "nama_pemesan": "T",
        "items": [{"barang_id": bid, "nama_barang": barang["nama_barang"], "qty": 200}],
    })
    assert po_r.status_code == 200, po_r.text
    po_id = po_r.json().get("_id")

    # SPK A: p1 qty=100
    a = admin.post(f"{API}/spk", json={
        "no_spk": f"ITER20_BM_SPKA_{_TS}", "catatan_pembayaran": "c", "owner_perusahaan": "o",
        "deadline": "2026-02-01",
        "items": [{"barang_id": bid, "nama_barang": barang["nama_barang"], "qty": 100,
                   "no_po": no_po2, "pengrajin_id": CTX["p1"], "harga": 1}],
    })
    assert a.status_code == 200, a.text
    # SPK B: p1 qty=50 (same pengrajin, same barang) — should be OK since 100+50=150 ≤ 200
    b = admin.post(f"{API}/spk", json={
        "no_spk": f"ITER20_BM_SPKB_{_TS}", "catatan_pembayaran": "c", "owner_perusahaan": "o",
        "deadline": "2026-02-01",
        "items": [{"barang_id": bid, "nama_barang": barang["nama_barang"], "qty": 50,
                   "no_po": no_po2, "pengrajin_id": CTX["p1"], "harga": 1}],
    })
    assert b.status_code == 200, b.text

    # BM for p1 qty=150 (aggregated across both SPKs)
    bm = admin.post(f"{API}/barang-masuk", json={
        "po_id": po_id, "no_po": no_po2, "tanggal_masuk": "2026-01-20", "penerima": "T",
        "items": [{"barang_id": bid, "nama_barang": barang["nama_barang"],
                   "qty_diterima": 150, "pengrajin_id": CTX["p1"], "pengrajin_nama": "p1"}],
    })
    assert bm.status_code == 200, f"BM should accept aggregated 150 for p1: {bm.status_code} {bm.text}"


# ---------- Regression: legacy iter18 SPK-allocations shape still works ----------

def test_80_legacy_allocations_flatten(admin):
    """allocations[] with single alloc should be accepted and flattened to pengrajin_id."""
    barang_r = admin.post(f"{API}/barang", json={
        "nama_barang": f"ITER20_LEG_{_TS}", "spesifikasi": "", "nama_pengrajin": "",
        "harga_pengrajin": 1, "harga_jual": 1,
    })
    bid = barang_r.json().get("_id")
    no_po3 = f"ITER20_LEG_{_TS}"
    admin.post(f"{API}/po", json={
        "no_po": no_po3, "tanggal_terima": "2026-01-01", "nama_pemesan": "T",
        "items": [{"barang_id": bid, "nama_barang": barang_r.json()["nama_barang"], "qty": 10}],
    })
    r = admin.post(f"{API}/spk", json={
        "no_spk": f"ITER20_LEG_SPK_{_TS}", "catatan_pembayaran": "c", "owner_perusahaan": "o",
        "deadline": "2026-02-01",
        "items": [{
            "barang_id": bid, "nama_barang": barang_r.json()["nama_barang"], "qty": 5,
            "no_po": no_po3, "harga": 1,
            "allocations": [{"pengrajin_id": CTX["p1"], "pengrajin_nama": "p1", "qty": 5}],
        }],
    })
    assert r.status_code == 200, r.text
