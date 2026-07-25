"""Iteration 11: Activity Log audit trail tests"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://agf-production.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@agfdata.com", "password": "admin123"}
STAFF = {"email": "staff@agfdata.com", "password": "staff123"}
GUEST = {"email": "tamu@agfdata.com", "password": "tamu123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def staff_session():
    return _login(STAFF)


@pytest.fixture(scope="module")
def guest_session():
    return _login(GUEST)


# ---------- Endpoint existence (KNOWN FAILING) ----------
class TestActivityLogEndpoints:
    def test_get_activity_log_exists(self, admin_session):
        r = admin_session.get(f"{API}/activity-log", timeout=15)
        assert r.status_code == 200, f"GET /api/activity-log missing (got {r.status_code}): {r.text[:200]}"
        assert isinstance(r.json(), list)

    def test_get_activity_log_forbidden_for_staff(self, staff_session):
        r = staff_session.get(f"{API}/activity-log", timeout=15)
        assert r.status_code == 403, f"expected 403 got {r.status_code}"

    def test_get_activity_log_forbidden_for_guest(self, guest_session):
        r = guest_session.get(f"{API}/activity-log", timeout=15)
        assert r.status_code == 403

    def test_purge_requires_before_param(self, admin_session):
        r = admin_session.delete(f"{API}/activity-log/purge", timeout=15)
        assert r.status_code == 400, f"expected 400 got {r.status_code}"

    def test_purge_forbidden_for_staff(self, staff_session):
        r = staff_session.delete(f"{API}/activity-log/purge?before=2025-01-01", timeout=15)
        assert r.status_code == 403


# ---------- Login/logout/failed-login logs (verify via GET endpoint) ----------
class TestAuthLogging:
    def test_login_creates_log_entry(self, admin_session):
        r = admin_session.get(f"{API}/activity-log?action=login", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert any(e.get("user_email") == "admin@agfdata.com" for e in data)

    def test_failed_login_creates_log_entry(self, admin_session):
        # Trigger a failed login
        requests.post(f"{API}/auth/login", json={"email": "admin@agfdata.com", "password": "wrong"}, timeout=15)
        r = admin_session.get(f"{API}/activity-log?action=login_failed", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert any(e.get("status_code") == 401 for e in data)


# ---------- Middleware create/update/delete logging ----------
class TestMutationMiddleware:
    def test_barang_crud_creates_log_entries(self, admin_session):
        # CREATE
        payload = {
            "nama_barang": "TEST_iter11_log", "nama_pengrajin": "P",
            "spesifikasi": "s", "harga_pengrajin": 100, "harga_jual": 200,
        }
        c = admin_session.post(f"{API}/barang", json=payload, timeout=15)
        assert c.status_code == 200
        bid = c.json().get("_id")
        assert bid
        # UPDATE
        payload["harga_jual"] = 250
        u = admin_session.put(f"{API}/barang/{bid}", json=payload, timeout=15)
        assert u.status_code == 200
        # DELETE
        d = admin_session.delete(f"{API}/barang/{bid}", timeout=15)
        assert d.status_code == 200

        # Verify entries via GET /api/activity-log
        r = admin_session.get(f"{API}/activity-log?resource=barang", timeout=15)
        assert r.status_code == 200
        data = r.json()
        actions = [e["action"] for e in data if e.get("resource_id") == bid or e.get("path", "").endswith(bid)]
        # Expect at least create + update + delete referencing this bid
        assert "delete" in actions
        assert "update" in actions
        # Create won't have resource_id in path; check by timestamp order
        assert any(e["action"] == "create" and e.get("resource") == "barang" for e in data)


# ---------- Regression: iter10 features ----------
class TestRegressionIter10:
    def test_barang_list_works(self, admin_session):
        r = admin_session.get(f"{API}/barang", timeout=15)
        assert r.status_code == 200

    def test_po_list_works(self, admin_session):
        r = admin_session.get(f"{API}/po", timeout=15)
        assert r.status_code == 200

    def test_progres_summary_works(self, admin_session):
        r = admin_session.get(f"{API}/progres/summary", timeout=15)
        assert r.status_code == 200
