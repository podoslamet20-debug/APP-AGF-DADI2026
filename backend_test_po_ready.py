#!/usr/bin/env python3
"""
AGFDATA Backend API Test Suite - PO Ready-to-Ship Notification Feature
Tests new endpoints: GET /api/dashboard/po-ready, POST mark-shipped, POST unmark-shipped
"""
import requests
import json
from datetime import datetime, timedelta

# Backend URL from frontend/.env
BASE_URL = "https://11a03a0d-d98a-445f-8f6d-5eb650bd3fb5.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
CREDENTIALS = {
    "admin": {"email": "admin@agfdata.com", "password": "admin123"},
    "staff": {"email": "staff@agfdata.com", "password": "staff123"},
    "owner": {"email": "owner@agfdata.com", "password": "owner123"},
    "guest": {"email": "tamu@agfdata.com", "password": "tamu123"},
}

# Test results tracking
test_results = []

def log_test(name, status, note=""):
    """Log test result"""
    result = f"{'✅ PASS' if status else '❌ FAIL'}: {name}"
    if note:
        result += f" - {note}"
    print(result)
    test_results.append({"name": name, "status": status, "note": note})
    return status

def login(role):
    """Login and return session with cookies"""
    session = requests.Session()
    creds = CREDENTIALS[role]
    resp = session.post(f"{BASE_URL}/auth/login", json=creds)
    if resp.status_code == 200:
        return session, resp.json()
    return None, None

def test_po_ready_feature():
    """
    Test PO Ready-to-Ship notification feature following the A-N test flow:
    A. Login admin. Create pengrajin. Create barang. Create PO with 1 item qty=5.
    B. GET /api/dashboard/po-ready — new PO should NOT appear yet (no progres yet).
    C. Create SPK for this PO/barang/pengrajin qty=5.
    D. POST /api/barang-masuk with qty_diterima=5.
    E. Add progres entries: grinda qty=5, servis qty=5, finishing qty=5, packing qty=5.
    F. GET /api/dashboard/po-ready — PO should appear with total_ready=5.
    G. Verify auth on GET /po-ready: 401 unauth, 200 for all roles.
    H. Test partial-ready case: create PO with 2 items, only fill packing for 1 item.
    I. POST mark-shipped as admin. Verify PO disappears.
    J. POST mark-shipped as staff/guest/owner → 403.
    K. mark-shipped again (idempotent) → 200 OK.
    L. Invalid po_id → 400. Non-existent po_id → 404.
    M. POST unmark-shipped as admin. Verify PO reappears.
    N. Regression: verify existing endpoints still work.
    """
    print("\n" + "="*80)
    print("TESTING PO READY-TO-SHIP NOTIFICATION FEATURE")
    print("="*80)
    
    # A. Login admin and create test data
    print("\n=== STEP A: Create Test Data (Pengrajin, Barang, PO) ===")
    admin_session, admin_user = login("admin")
    if not admin_session:
        log_test("Step A: Admin login", False, "CRITICAL - cannot proceed")
        return
    log_test("Step A: Admin login", True)
    
    # Create pengrajin
    timestamp = datetime.now().strftime("%H%M%S")
    pengrajin_data = {
        "nama": f"Pak Joko {timestamp}",
        "telepon": "081234567890",
        "alamat": "Jl. Mebel No. 123",
        "rekening": "1234567890",
        "catatan": "Test pengrajin for PO Ready"
    }
    pengrajin_resp = admin_session.post(f"{BASE_URL}/pengrajin", json=pengrajin_data)
    if pengrajin_resp.status_code != 200:
        log_test("Step A: Create pengrajin", False, f"status {pengrajin_resp.status_code}")
        return
    pengrajin = pengrajin_resp.json()
    pengrajin_id = pengrajin["_id"]
    pengrajin_nama = pengrajin_data["nama"]
    log_test("Step A: Create pengrajin", True, f"id={pengrajin_id}")
    
    # Create barang with nama_pengrajin
    barang_data = {
        "nama_barang": f"Kursi Jati {timestamp}",
        "nama_pengrajin": pengrajin_nama,
        "spesifikasi": "Kayu jati solid",
        "harga_pengrajin": 500000,
        "harga_jual": 750000,
        "catatan": "Test barang for PO Ready"
    }
    barang_resp = admin_session.post(f"{BASE_URL}/barang", json=barang_data)
    if barang_resp.status_code != 200:
        log_test("Step A: Create barang", False, f"status {barang_resp.status_code}")
        return
    barang = barang_resp.json()
    barang_id = barang["_id"]
    log_test("Step A: Create barang", True, f"id={barang_id}")
    
    # Create PO with 1 item qty=5
    po_data = {
        "no_po": f"PO-READY-TEST-{timestamp}",
        "items": [
            {"barang_id": barang_id, "qty": 5, "catatan": "Test PO Ready"}
        ],
        "catatan": "Test PO for Ready-to-Ship notification"
    }
    po_resp = admin_session.post(f"{BASE_URL}/po", json=po_data)
    if po_resp.status_code != 200:
        log_test("Step A: Create PO", False, f"status {po_resp.status_code}: {po_resp.text}")
        return
    po = po_resp.json()
    po_id = po["_id"]
    no_po = po["no_po"]
    log_test("Step A: Create PO", True, f"id={po_id}, no_po={no_po}")
    
    # B. GET /api/dashboard/po-ready — should NOT appear yet (no progres)
    print("\n=== STEP B: Verify PO NOT Ready (no progres yet) ===")
    po_ready_resp = admin_session.get(f"{BASE_URL}/dashboard/po-ready")
    if po_ready_resp.status_code != 200:
        log_test("Step B: GET /po-ready", False, f"status {po_ready_resp.status_code}")
        return
    po_ready_data = po_ready_resp.json()
    baseline_count = po_ready_data.get("count", 0)
    po_ids_before = [p["po_id"] for p in po_ready_data.get("pos", [])]
    if po_id in po_ids_before:
        log_test("Step B: PO should NOT appear yet", False, "PO appeared before progres")
        return
    log_test("Step B: GET /po-ready baseline", True, f"count={baseline_count}, new PO not in list")
    
    # C. Create SPK for this PO/barang/pengrajin qty=5
    print("\n=== STEP C: Create SPK ===")
    deadline = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    spk_data = {
        "no_spk": f"SPK-READY-TEST-{timestamp}",
        "items": [{
            "barang_id": barang_id,
            "nama_barang": barang_data["nama_barang"],
            "spesifikasi": barang_data["spesifikasi"],
            "qty": 5,
            "no_po": no_po,
            "pengrajin_id": pengrajin_id,
            "pengrajin_nama": pengrajin_nama,
            "harga": barang_data["harga_pengrajin"],
            "catatan": "Test SPK"
        }],
        "catatan_pembayaran": "Test payment",
        "owner_perusahaan": "PT Test",
        "deadline": deadline
    }
    spk_resp = admin_session.post(f"{BASE_URL}/spk", json=spk_data)
    if spk_resp.status_code != 200:
        log_test("Step C: Create SPK", False, f"status {spk_resp.status_code}: {spk_resp.text}")
        return
    spk = spk_resp.json()
    log_test("Step C: Create SPK", True, f"id={spk['_id']}")
    
    # D. POST /api/barang-masuk with qty_diterima=5
    print("\n=== STEP D: Create Barang Masuk ===")
    bm_data = {
        "po_id": po_id,
        "tanggal_masuk": datetime.now().strftime("%Y-%m-%d"),
        "penerima": "Admin Test",
        "items": [{
            "barang_id": barang_id,
            "qty_diterima": 5,
            "pengrajin_id": pengrajin_id,
            "pengrajin_nama": pengrajin_nama
        }]
    }
    bm_resp = admin_session.post(f"{BASE_URL}/barang-masuk", json=bm_data)
    if bm_resp.status_code != 200:
        log_test("Step D: Create barang-masuk", False, f"status {bm_resp.status_code}: {bm_resp.text}")
        return
    log_test("Step D: Create barang-masuk", True, f"qty_diterima=5")
    
    # E. Add progres entries: grinda, servis, finishing, packing (each qty=5)
    print("\n=== STEP E: Add Progres Entries (grinda → servis → finishing → packing) ===")
    stages = ["grinda", "servis", "finishing", "packing"]
    for stage in stages:
        progres_data = {
            "po_id": po_id,
            "item_id": barang_id,
            "stage": stage,
            "qty": 5,
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "pengrajin_id": pengrajin_id,
            "pengrajin_nama": pengrajin_nama,
            "nama_barang": barang_data["nama_barang"]
        }
        progres_resp = admin_session.post(f"{BASE_URL}/progres", json=progres_data)
        if progres_resp.status_code != 200:
            log_test(f"Step E: Create progres {stage}", False, f"status {progres_resp.status_code}: {progres_resp.text}")
            return
        log_test(f"Step E: Create progres {stage}", True, f"qty=5")
    
    # F. GET /api/dashboard/po-ready — PO should now appear with total_ready=5
    print("\n=== STEP F: Verify PO IS Ready (all stages complete) ===")
    po_ready_resp = admin_session.get(f"{BASE_URL}/dashboard/po-ready")
    if po_ready_resp.status_code != 200:
        log_test("Step F: GET /po-ready after progres", False, f"status {po_ready_resp.status_code}")
        return
    po_ready_data = po_ready_resp.json()
    new_count = po_ready_data.get("count", 0)
    ready_pos = po_ready_data.get("pos", [])
    
    # Find our PO in the list
    our_po = None
    for p in ready_pos:
        if p["po_id"] == po_id:
            our_po = p
            break
    
    if not our_po:
        log_test("Step F: PO should appear in ready list", False, f"PO {po_id} not found in {len(ready_pos)} ready POs")
        return
    
    # Verify structure
    if our_po.get("total_ready") != 5:
        log_test("Step F: PO total_ready", False, f"expected 5, got {our_po.get('total_ready')}")
        return
    if our_po.get("total_qty") != 5:
        log_test("Step F: PO total_qty", False, f"expected 5, got {our_po.get('total_qty')}")
        return
    if len(our_po.get("items", [])) != 1:
        log_test("Step F: PO items count", False, f"expected 1 item, got {len(our_po.get('items', []))}")
        return
    
    item = our_po["items"][0]
    if item.get("qty_ready") != 5:
        log_test("Step F: Item qty_ready", False, f"expected 5, got {item.get('qty_ready')}")
        return
    if item.get("qty") != 5:
        log_test("Step F: Item qty", False, f"expected 5, got {item.get('qty')}")
        return
    
    log_test("Step F: PO appears in ready list", True, f"count={new_count}, total_ready=5, items[0].qty_ready=5")
    
    # G. Verify auth on GET /po-ready: 401 unauth, 200 for all roles
    print("\n=== STEP G: Verify Auth on GET /po-ready ===")
    
    # Unauthenticated should get 401
    unauth_resp = requests.get(f"{BASE_URL}/dashboard/po-ready")
    log_test("Step G: Unauthenticated GET /po-ready", unauth_resp.status_code == 401, f"status={unauth_resp.status_code}")
    
    # All authenticated roles should get 200
    for role in ["admin", "staff", "owner", "guest"]:
        session, _ = login(role)
        if session:
            resp = session.get(f"{BASE_URL}/dashboard/po-ready")
            log_test(f"Step G: {role} GET /po-ready", resp.status_code == 200, f"status={resp.status_code}")
    
    # H. Test partial-ready case: create PO with 2 items, only fill packing for 1 item
    print("\n=== STEP H: Test Partial-Ready Case (2 items, only 1 ready) ===")
    
    # Create second barang
    barang2_data = {
        "nama_barang": f"Meja Jati {timestamp}",
        "nama_pengrajin": pengrajin_nama,
        "spesifikasi": "Meja kayu jati",
        "harga_pengrajin": 600000,
        "harga_jual": 900000,
        "catatan": "Test barang 2"
    }
    barang2_resp = admin_session.post(f"{BASE_URL}/barang", json=barang2_data)
    if barang2_resp.status_code != 200:
        log_test("Step H: Create barang 2", False, f"status {barang2_resp.status_code}")
        return
    barang2 = barang2_resp.json()
    barang2_id = barang2["_id"]
    log_test("Step H: Create barang 2", True, f"id={barang2_id}")
    
    # Create PO with 2 items
    po2_data = {
        "no_po": f"PO-PARTIAL-{timestamp}",
        "items": [
            {"barang_id": barang_id, "qty": 3, "catatan": "Item 1"},
            {"barang_id": barang2_id, "qty": 4, "catatan": "Item 2"}
        ],
        "catatan": "Test partial ready"
    }
    po2_resp = admin_session.post(f"{BASE_URL}/po", json=po2_data)
    if po2_resp.status_code != 200:
        log_test("Step H: Create PO with 2 items", False, f"status {po2_resp.status_code}")
        return
    po2 = po2_resp.json()
    po2_id = po2["_id"]
    no_po2 = po2["no_po"]
    log_test("Step H: Create PO with 2 items", True, f"id={po2_id}")
    
    # Create SPK for both items
    spk2_data = {
        "no_spk": f"SPK-PARTIAL-{timestamp}",
        "items": [
            {
                "barang_id": barang_id,
                "nama_barang": barang_data["nama_barang"],
                "spesifikasi": barang_data["spesifikasi"],
                "qty": 3,
                "no_po": no_po2,
                "pengrajin_id": pengrajin_id,
                "pengrajin_nama": pengrajin_nama,
                "harga": barang_data["harga_pengrajin"]
            },
            {
                "barang_id": barang2_id,
                "nama_barang": barang2_data["nama_barang"],
                "spesifikasi": barang2_data["spesifikasi"],
                "qty": 4,
                "no_po": no_po2,
                "pengrajin_id": pengrajin_id,
                "pengrajin_nama": pengrajin_nama,
                "harga": barang2_data["harga_pengrajin"]
            }
        ],
        "catatan_pembayaran": "Test payment",
        "owner_perusahaan": "PT Test",
        "deadline": deadline
    }
    spk2_resp = admin_session.post(f"{BASE_URL}/spk", json=spk2_data)
    if spk2_resp.status_code != 200:
        log_test("Step H: Create SPK for 2 items", False, f"status {spk2_resp.status_code}")
        return
    log_test("Step H: Create SPK for 2 items", True)
    
    # Create barang-masuk for both items
    bm2_data = {
        "po_id": po2_id,
        "tanggal_masuk": datetime.now().strftime("%Y-%m-%d"),
        "penerima": "Admin Test",
        "items": [
            {"barang_id": barang_id, "qty_diterima": 3, "pengrajin_id": pengrajin_id, "pengrajin_nama": pengrajin_nama},
            {"barang_id": barang2_id, "qty_diterima": 4, "pengrajin_id": pengrajin_id, "pengrajin_nama": pengrajin_nama}
        ]
    }
    bm2_resp = admin_session.post(f"{BASE_URL}/barang-masuk", json=bm2_data)
    if bm2_resp.status_code != 200:
        log_test("Step H: Create barang-masuk for 2 items", False, f"status {bm2_resp.status_code}")
        return
    log_test("Step H: Create barang-masuk for 2 items", True)
    
    # Add progres for ONLY first item (all stages)
    for stage in stages:
        progres_data = {
            "po_id": po2_id,
            "item_id": barang_id,
            "stage": stage,
            "qty": 3,
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "pengrajin_id": pengrajin_id,
            "pengrajin_nama": pengrajin_nama,
            "nama_barang": barang_data["nama_barang"]
        }
        progres_resp = admin_session.post(f"{BASE_URL}/progres", json=progres_data)
        if progres_resp.status_code != 200:
            log_test(f"Step H: Progres {stage} item 1", False, f"status {progres_resp.status_code}")
            return
    log_test("Step H: Add progres for item 1 only", True, "all stages qty=3")
    
    # Verify PO2 does NOT appear in ready list (item 2 not ready)
    po_ready_resp = admin_session.get(f"{BASE_URL}/dashboard/po-ready")
    if po_ready_resp.status_code != 200:
        log_test("Step H: GET /po-ready after partial", False, f"status {po_ready_resp.status_code}")
        return
    po_ready_data = po_ready_resp.json()
    ready_pos = po_ready_data.get("pos", [])
    po2_in_list = any(p["po_id"] == po2_id for p in ready_pos)
    log_test("Step H: Partial PO should NOT appear", not po2_in_list, f"PO2 in list: {po2_in_list}")
    
    # I. POST mark-shipped as admin. Verify PO disappears.
    print("\n=== STEP I: Mark PO as Shipped (Admin) ===")
    mark_resp = admin_session.post(f"{BASE_URL}/dashboard/po-ready/{po_id}/mark-shipped")
    if mark_resp.status_code != 200:
        log_test("Step I: POST mark-shipped", False, f"status {mark_resp.status_code}: {mark_resp.text}")
        return
    mark_data = mark_resp.json()
    if not mark_data.get("ok"):
        log_test("Step I: mark-shipped response", False, f"ok={mark_data.get('ok')}")
        return
    if mark_data.get("po_id") != po_id:
        log_test("Step I: mark-shipped po_id", False, f"expected {po_id}, got {mark_data.get('po_id')}")
        return
    log_test("Step I: POST mark-shipped", True, f"ok=True, po_id={po_id}")
    
    # Verify PO disappears from list
    po_ready_resp = admin_session.get(f"{BASE_URL}/dashboard/po-ready")
    if po_ready_resp.status_code != 200:
        log_test("Step I: GET /po-ready after mark-shipped", False, f"status {po_ready_resp.status_code}")
        return
    po_ready_data = po_ready_resp.json()
    ready_pos = po_ready_data.get("pos", [])
    po_in_list = any(p["po_id"] == po_id for p in ready_pos)
    log_test("Step I: PO disappears after mark-shipped", not po_in_list, f"PO in list: {po_in_list}")
    
    # J. POST mark-shipped as staff/guest/owner → 403
    print("\n=== STEP J: Mark-Shipped Auth (Staff/Guest/Owner should get 403) ===")
    for role in ["staff", "guest", "owner"]:
        session, _ = login(role)
        if session:
            resp = session.post(f"{BASE_URL}/dashboard/po-ready/{po_id}/mark-shipped")
            log_test(f"Step J: {role} mark-shipped denied", resp.status_code == 403, f"status={resp.status_code}")
    
    # K. mark-shipped again (idempotent) → 200 OK
    print("\n=== STEP K: Mark-Shipped Idempotent ===")
    mark2_resp = admin_session.post(f"{BASE_URL}/dashboard/po-ready/{po_id}/mark-shipped")
    log_test("Step K: mark-shipped idempotent", mark2_resp.status_code == 200, f"status={mark2_resp.status_code}")
    
    # L. Invalid po_id → 400. Non-existent po_id → 404.
    print("\n=== STEP L: Mark-Shipped Error Cases ===")
    
    # Invalid ObjectId
    invalid_resp = admin_session.post(f"{BASE_URL}/dashboard/po-ready/not-a-valid-id/mark-shipped")
    log_test("Step L: Invalid po_id → 400", invalid_resp.status_code == 400, f"status={invalid_resp.status_code}")
    
    # Valid ObjectId but non-existent
    fake_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format
    notfound_resp = admin_session.post(f"{BASE_URL}/dashboard/po-ready/{fake_id}/mark-shipped")
    log_test("Step L: Non-existent po_id → 404", notfound_resp.status_code == 404, f"status={notfound_resp.status_code}")
    
    # M. POST unmark-shipped as admin. Verify PO reappears.
    print("\n=== STEP M: Unmark PO as Shipped (Admin) ===")
    unmark_resp = admin_session.post(f"{BASE_URL}/dashboard/po-ready/{po_id}/unmark-shipped")
    if unmark_resp.status_code != 200:
        log_test("Step M: POST unmark-shipped", False, f"status {unmark_resp.status_code}: {unmark_resp.text}")
        return
    unmark_data = unmark_resp.json()
    log_test("Step M: POST unmark-shipped", True, f"ok={unmark_data.get('ok')}")
    
    # Verify PO reappears in list
    po_ready_resp = admin_session.get(f"{BASE_URL}/dashboard/po-ready")
    if po_ready_resp.status_code != 200:
        log_test("Step M: GET /po-ready after unmark", False, f"status {po_ready_resp.status_code}")
        return
    po_ready_data = po_ready_resp.json()
    ready_pos = po_ready_data.get("pos", [])
    po_in_list = any(p["po_id"] == po_id for p in ready_pos)
    log_test("Step M: PO reappears after unmark-shipped", po_in_list, f"PO in list: {po_in_list}")
    
    # Test unmark-shipped auth (staff/guest/owner → 403)
    print("\n=== STEP M: Unmark-Shipped Auth (Staff/Guest/Owner should get 403) ===")
    for role in ["staff", "guest", "owner"]:
        session, _ = login(role)
        if session:
            resp = session.post(f"{BASE_URL}/dashboard/po-ready/{po_id}/unmark-shipped")
            log_test(f"Step M: {role} unmark-shipped denied", resp.status_code == 403, f"status={resp.status_code}")

def test_regression():
    """N. Regression: verify existing endpoints still work"""
    print("\n=== STEP N: Regression Tests ===")
    
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("Regression: Admin login", False)
        return
    
    # Test auth endpoints
    for role in ["admin", "staff", "owner", "guest"]:
        session, user = login(role)
        if session and user:
            me_resp = session.get(f"{BASE_URL}/auth/me")
            log_test(f"Regression: {role} auth/me", me_resp.status_code == 200)
    
    # Test barang endpoint
    barang_resp = admin_session.get(f"{BASE_URL}/barang")
    log_test("Regression: GET /barang", barang_resp.status_code == 200)
    
    # Test PO endpoint
    po_resp = admin_session.get(f"{BASE_URL}/po")
    log_test("Regression: GET /po", po_resp.status_code == 200)
    
    # Test dashboard/kinerja-pengrajin
    month = datetime.now().strftime("%Y-%m")
    kinerja_resp = admin_session.get(f"{BASE_URL}/dashboard/kinerja-pengrajin?month={month}")
    log_test("Regression: GET /dashboard/kinerja-pengrajin", kinerja_resp.status_code == 200)

def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY - PO READY-TO-SHIP NOTIFICATION")
    print("="*80)
    
    passed = sum(1 for r in test_results if r["status"])
    failed = sum(1 for r in test_results if not r["status"])
    total = len(test_results)
    
    print(f"\nTotal: {total} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for r in test_results:
            if not r["status"]:
                print(f"  - {r['name']}: {r['note']}")
    else:
        print("\n✅ ALL TESTS PASSED!")
    
    print("\n" + "="*80)

def main():
    """Run all tests"""
    print("="*80)
    print("AGFDATA Backend API Test Suite")
    print("PO Ready-to-Ship Notification Feature")
    print("="*80)
    
    # Test PO Ready feature (steps A-M)
    test_po_ready_feature()
    
    # Test regression (step N)
    test_regression()
    
    # Print summary
    print_summary()

if __name__ == "__main__":
    main()
