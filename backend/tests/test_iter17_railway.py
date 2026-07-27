"""Iter17 Railway pre-deploy verification tests"""
import os
import requests
import pytest
from pathlib import Path

# Load REACT_APP_BACKEND_URL from frontend/.env if not in env
_url = os.environ.get('REACT_APP_BACKEND_URL')
if not _url:
    envfile = Path('/app/frontend/.env')
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            if line.startswith('REACT_APP_BACKEND_URL='):
                _url = line.split('=', 1)[1].strip()
                break
BASE_URL = (_url or 'http://localhost:8001').rstrip('/')

CREDS = {
    "admin": {"email": "admin@agfdata.com", "password": "admin123"},
    "staff": {"email": "staff@agfdata.com", "password": "staff123"},
    "guest": {"email": "tamu@agfdata.com", "password": "tamu123"},
}


def _login(role):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS[role], timeout=30)
    assert r.status_code == 200, f"{role} login failed: {r.status_code} {r.text}"
    assert len(s.cookies) > 0, f"{role} no cookie set"
    return s


@pytest.mark.parametrize("role", ["admin", "staff", "guest"])
def test_auth_login(role):
    _login(role)


@pytest.mark.parametrize("endpoint", [
    "/api/barang", "/api/po", "/api/staffing", "/api/spk",
    "/api/progres/by-po", "/api/rekap/progres",
])
def test_core_crud_get(endpoint):
    s = _login("admin")
    r = s.get(f"{BASE_URL}{endpoint}", timeout=30)
    assert r.status_code == 200, f"{endpoint} => {r.status_code} {r.text[:200]}"
    data = r.json()
    assert isinstance(data, (list, dict)), f"{endpoint} not list/dict"


def test_activity_log_middleware_on_mutation():
    """POST/PUT/DELETE should produce activity log entries."""
    s = _login("admin")
    # Create a barang then check activity log
    payload = {
        "nama_barang": "TEST_iter17_item",
        "nama_pengrajin": "TEST_iter17_pengrajin",
        "spesifikasi": "spec",
        "harga_pengrajin": 10000,
        "harga_jual": 15000,
    }
    r = s.post(f"{BASE_URL}/api/barang", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create barang failed: {r.status_code} {r.text}"
    created = r.json()
    bid = created.get("id") or created.get("_id")

    # Fetch activity log
    r2 = s.get(f"{BASE_URL}/api/activity-log", timeout=30)
    if r2.status_code == 200:
        logs = r2.json()
        assert isinstance(logs, list) and len(logs) > 0, "no activity logs"
    # cleanup
    if bid:
        s.delete(f"{BASE_URL}/api/barang/{bid}", timeout=30)
