"""Iter21 tests: Rekap enhancements (no_po_list, pengrajin_names, barang_list, filters, sorting)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@agfdata.com", "password": "admin123"})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def seed(admin_client):
    ts = int(time.time())
    tag = f"ITER21_{ts}"

    # Create 2 pengrajin
    p_ids, p_namas = [], []
    for name in [f"{tag}_Aida", f"{tag}_Budi"]:
        r = admin_client.post(f"{API}/pengrajin", json={"nama": name})
        assert r.status_code == 200, r.text
        d = r.json()
        p_ids.append(d.get("_id") or d.get("id"))
        p_namas.append(d["nama"])

    # Barang
    r = admin_client.post(f"{API}/barang", json={
        "nama_barang": f"{tag}_Meja",
        "spesifikasi": "Kayu",
        "nama_pengrajin": "",
        "harga_pengrajin": 100,
        "harga_jual": 200,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    barang_id = d.get("_id") or d.get("id")
    barang_nama = d["nama_barang"]

    # PO qty 100
    no_po = f"{tag}_PO"
    r = admin_client.post(f"{API}/po", json={
        "no_po": no_po, "tanggal_terima": "2026-01-05", "nama_pemesan": "T",
        "items": [{"barang_id": barang_id, "nama_barang": barang_nama, "qty": 100}],
    })
    assert r.status_code == 200, r.text
    po_id = r.json().get("_id") or r.json().get("id")

    # 2 SPKs — one per pengrajin qty 60 & 40
    for pid, qty in zip(p_ids, [60, 40]):
        r = admin_client.post(f"{API}/spk", json={
            "no_spk": f"{tag}_SPK_{pid[-6:]}",
            "catatan_pembayaran": "cash", "owner_perusahaan": "AGF", "deadline": "2026-02-01",
            "items": [{
                "barang_id": barang_id, "nama_barang": barang_nama, "qty": qty,
                "no_po": no_po, "pengrajin_id": pid, "harga": 100,
            }],
        })
        assert r.status_code == 200, r.text

    # BM: pengrajin1 delivers 30, pengrajin2 delivers 20
    for pid, pnama, qty in zip(p_ids, p_namas, [30, 20]):
        r = admin_client.post(f"{API}/barang-masuk", json={
            "po_id": po_id, "no_po": no_po, "tanggal_masuk": "2026-01-10", "penerima": "T",
            "items": [{
                "barang_id": barang_id, "nama_barang": barang_nama,
                "pengrajin_id": pid, "pengrajin_nama": pnama, "qty_diterima": qty,
            }],
        })
        assert r.status_code == 200, r.text

    # Progres chain grinda->servis->finishing->packing qty=10 for pengrajin1
    for stage in ["grinda", "servis", "finishing", "packing"]:
        r = admin_client.post(f"{API}/progres", json={
            "po_id": po_id, "item_id": barang_id, "nama_barang": barang_nama,
            "pengrajin_id": p_ids[0], "pengrajin_nama": p_namas[0],
            "stage": stage, "qty": 10, "tanggal": "2026-01-11",
        })
        assert r.status_code == 200, f"progres {stage} failed: {r.status_code} {r.text}"

    return {"tag": tag, "no_po": no_po, "po_id": po_id, "barang_id": barang_id,
            "barang_nama": barang_nama, "p_ids": p_ids, "p_namas": p_namas}


# ---------- Rekap Per Barang ----------
class TestRekapPerBarang:
    def test_response_shape_and_aggregation(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/per-barang", params={"no_po": seed["no_po"]})
        assert r.status_code == 200
        rows = r.json()
        row = next(x for x in rows if x["barang_id"] == seed["barang_id"])
        assert isinstance(row["no_po_list"], list)
        assert isinstance(row["pengrajin_names"], list)
        assert row["pengrajin_names"] == sorted(row["pengrajin_names"])
        assert row["no_po_list"] == sorted(row["no_po_list"])
        assert row["no_po"] == ", ".join(row["no_po_list"])
        assert row["nama_pengrajin"] == ", ".join(row["pengrajin_names"])
        assert len(row["pengrajin_names"]) == 2, row["pengrajin_names"]
        assert row["qty_masuk"] == 50
        assert row["qty_packing"] == 10
        assert row["kurang"] == 40

    def test_sort_a_z(self, admin_client):
        r = admin_client.get(f"{API}/rekap/per-barang")
        assert r.status_code == 200
        names = [x.get("nama_barang", "").lower() for x in r.json()]
        assert names == sorted(names)

    def test_filter_barang_id(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/per-barang", params={"barang_id": seed["barang_id"]})
        assert r.status_code == 200
        for x in r.json():
            assert x["barang_id"] == seed["barang_id"]

    def test_filter_pengrajin_narrows(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/per-barang",
                             params={"no_po": seed["no_po"], "pengrajin_id": seed["p_ids"][0]})
        assert r.status_code == 200
        row = next(x for x in r.json() if x["barang_id"] == seed["barang_id"])
        assert row["qty_masuk"] == 30

    def test_filter_date_range_exclude(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/per-barang",
                             params={"no_po": seed["no_po"], "date_from": "2099-01-01"})
        assert r.status_code == 200
        assert all(x["barang_id"] != seed["barang_id"] for x in r.json())


# ---------- Rekap Per Pengrajin ----------
class TestRekapPerPengrajin:
    def test_response_shape(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/per-pengrajin", params={"no_po": seed["no_po"]})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 2, rows
        for row in rows:
            assert isinstance(row["no_po_list"], list)
            assert isinstance(row["barang_list"], list)
            assert row["no_po"] == ", ".join(row["no_po_list"])
            assert row["barang_dikerjakan"] == ", ".join(row["barang_list"])

    def test_sort_a_z(self, admin_client):
        r = admin_client.get(f"{API}/rekap/per-pengrajin")
        assert r.status_code == 200
        names = [x.get("pengrajin", "").lower() for x in r.json()]
        assert names == sorted(names)

    def test_filter_pengrajin_id(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/per-pengrajin", params={"pengrajin_id": seed["p_ids"][0]})
        assert r.status_code == 200
        for row in r.json():
            if row.get("pengrajin_id"):
                assert row["pengrajin_id"] == seed["p_ids"][0]


# ---------- Rekap Progres ----------
class TestRekapProgres:
    def test_no_nama_pengrajin(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/progres", params={"no_po": seed["no_po"]})
        assert r.status_code == 200
        for row in r.json():
            assert "nama_pengrajin" not in row, row

    def test_aggregate_packing(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/progres",
                             params={"no_po": seed["no_po"], "barang_id": seed["barang_id"]})
        assert r.status_code == 200
        rows = [x for x in r.json() if seed["tag"] in (x.get("nama_barang") or "")]
        assert len(rows) == 1, rows
        assert rows[0]["packing"] == 10
        assert rows[0]["qty_masuk"] == 50

    def test_filter_date_excludes(self, admin_client, seed):
        r = admin_client.get(f"{API}/rekap/progres", params={"date_from": "2099-01-01"})
        assert r.status_code == 200
        assert not any(seed["tag"] in (x.get("nama_barang") or "") for x in r.json())


# ---------- Regression ----------
class TestRekapRegression:
    def test_all_po(self, admin_client):
        r = admin_client.get(f"{API}/rekap/all-po")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_staffing_summary(self, admin_client):
        r = admin_client.get(f"{API}/rekap/staffing-summary")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestExportsRegression:
    @pytest.mark.parametrize("path", [
        "/export/staffing/pdf",
        "/export/staffing/excel",
        "/export/barang-masuk/pdf",
        "/export/barang-masuk/excel",
        "/export/progres/pdf",
    ])
    def test_export(self, admin_client, path):
        r = admin_client.get(f"{API}{path}")
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        assert len(r.content) > 500, f"{path}: size={len(r.content)}"
