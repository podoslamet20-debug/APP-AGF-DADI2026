#!/usr/bin/env python3
"""
AGFDATA Backend API Test Suite
Tests GridFS storage backend + full regression after storage migration
"""
import requests
import json
import io
from PIL import Image
from datetime import datetime

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

def create_test_image(size=(100, 100), color=(255, 0, 0), format="PNG"):
    """Create a test image in memory"""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf

def login(role):
    """Login and return session with cookies"""
    session = requests.Session()
    creds = CREDENTIALS[role]
    resp = session.post(f"{BASE_URL}/auth/login", json=creds)
    if resp.status_code == 200:
        return session, resp.json()
    return None, None

def test_auth():
    """Test authentication for all roles"""
    print("\n=== TESTING AUTH ===")
    
    for role in ["admin", "staff", "owner", "guest"]:
        session, user = login(role)
        if session and user:
            # Test /api/auth/me
            me_resp = session.get(f"{BASE_URL}/auth/me")
            if me_resp.status_code == 200 and me_resp.json().get("role") == role:
                log_test(f"Auth: {role} login + /me", True, f"role={role}")
            else:
                log_test(f"Auth: {role} login + /me", False, f"me endpoint failed")
            
            # Test logout
            logout_resp = session.post(f"{BASE_URL}/auth/logout")
            log_test(f"Auth: {role} logout", logout_resp.status_code == 200)
        else:
            log_test(f"Auth: {role} login", False, "login failed")

def test_file_upload_download():
    """PRIORITY 1: Test file upload/download with GridFS"""
    print("\n=== TESTING FILE UPLOAD/DOWNLOAD (GridFS) ===")
    
    # Test 1: Admin can upload
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("File Upload: admin login", False, "CRITICAL - cannot test upload")
        return None
    
    # Create test PNG image
    test_img = create_test_image(size=(200, 200), color=(0, 255, 0), format="PNG")
    files = {"file": ("test_image.png", test_img, "image/png")}
    
    upload_resp = admin_session.post(f"{BASE_URL}/upload", files=files)
    if upload_resp.status_code == 200:
        upload_data = upload_resp.json()
        if "path" in upload_data and "url" in upload_data:
            log_test("File Upload: admin POST /upload", True, f"path={upload_data['path']}")
            uploaded_path = upload_data["path"]
        else:
            log_test("File Upload: admin POST /upload", False, "CRITICAL - missing path/url in response")
            return None
    else:
        log_test("File Upload: admin POST /upload", False, f"CRITICAL - status {upload_resp.status_code}")
        return None
    
    # Test 2: Download uploaded file (public endpoint)
    download_resp = requests.get(f"{BASE_URL}/files/{uploaded_path}")
    if download_resp.status_code == 200:
        content_type = download_resp.headers.get("content-type", "")
        if "image/png" in content_type.lower():
            log_test("File Download: GET /files/{path}", True, f"content-type={content_type}, size={len(download_resp.content)} bytes")
        else:
            log_test("File Download: GET /files/{path}", False, f"wrong content-type: {content_type}")
    else:
        log_test("File Download: GET /files/{path}", False, f"CRITICAL - status {download_resp.status_code}")
        return None
    
    # Test 3: Upload JPG
    test_jpg = create_test_image(size=(150, 150), color=(0, 0, 255), format="JPEG")
    files_jpg = {"file": ("test_image.jpg", test_jpg, "image/jpeg")}
    upload_jpg_resp = admin_session.post(f"{BASE_URL}/upload", files=files_jpg)
    log_test("File Upload: JPG format", upload_jpg_resp.status_code == 200)
    
    # Test 4: Staff cannot upload (403)
    staff_session, _ = login("staff")
    if staff_session:
        test_img2 = create_test_image(size=(50, 50), color=(255, 255, 0), format="PNG")
        files2 = {"file": ("staff_test.png", test_img2, "image/png")}
        staff_upload = staff_session.post(f"{BASE_URL}/upload", files=files2)
        log_test("File Upload: staff denied (403)", staff_upload.status_code == 403)
    
    # Test 5: Guest cannot upload (403)
    guest_session, _ = login("guest")
    if guest_session:
        test_img3 = create_test_image(size=(50, 50), color=(255, 0, 255), format="PNG")
        files3 = {"file": ("guest_test.png", test_img3, "image/png")}
        guest_upload = guest_session.post(f"{BASE_URL}/upload", files=files3)
        log_test("File Upload: guest denied (403)", guest_upload.status_code == 403)
    
    # Test 6: Unauthenticated upload (401)
    test_img4 = create_test_image(size=(50, 50), color=(128, 128, 128), format="PNG")
    files4 = {"file": ("unauth_test.png", test_img4, "image/png")}
    unauth_upload = requests.post(f"{BASE_URL}/upload", files=files4)
    log_test("File Upload: unauthenticated denied (401)", unauth_upload.status_code == 401)
    
    return uploaded_path

def test_barang_with_image(image_path):
    """Test creating Barang with uploaded image"""
    print("\n=== TESTING BARANG WITH IMAGE ===")
    
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("Barang: admin login", False)
        return None
    
    # Create barang with image
    barang_data = {
        "nama_barang": f"Test Furniture {datetime.now().strftime('%H%M%S')}",
        "spesifikasi": "Test spec with image",
        "harga_pengrajin": 100000,
        "harga_jual": 150000,
        "gambar_path": image_path,
        "catatan": "Test barang with GridFS image"
    }
    
    create_resp = admin_session.post(f"{BASE_URL}/barang", json=barang_data)
    if create_resp.status_code == 200:
        barang = create_resp.json()
        if barang.get("gambar_path") == image_path:
            log_test("Barang: create with gambar_path", True, f"barang_id={barang.get('_id')}")
            return barang.get("_id")
        else:
            log_test("Barang: create with gambar_path", False, "gambar_path not saved")
    else:
        log_test("Barang: create with gambar_path", False, f"status {create_resp.status_code}")
    
    return None

def test_barang_crud():
    """Test Barang CRUD operations"""
    print("\n=== TESTING BARANG CRUD ===")
    
    admin_session, _ = login("admin")
    staff_session, _ = login("staff")
    
    if not admin_session:
        log_test("Barang CRUD: admin login", False)
        return
    
    # Admin can create
    barang_data = {
        "nama_barang": f"Kursi Kayu {datetime.now().strftime('%H%M%S')}",
        "spesifikasi": "Kayu jati",
        "harga_pengrajin": 200000,
        "harga_jual": 300000,
        "catatan": "Test CRUD"
    }
    create_resp = admin_session.post(f"{BASE_URL}/barang", json=barang_data)
    if create_resp.status_code == 200:
        barang_id = create_resp.json().get("_id")
        log_test("Barang CRUD: admin create", True, f"id={barang_id}")
    else:
        log_test("Barang CRUD: admin create", False, f"status {create_resp.status_code}")
        return
    
    # Admin can read
    get_resp = admin_session.get(f"{BASE_URL}/barang/{barang_id}")
    log_test("Barang CRUD: admin read by ID", get_resp.status_code == 200)
    
    # Admin can list
    list_resp = admin_session.get(f"{BASE_URL}/barang")
    log_test("Barang CRUD: admin list", list_resp.status_code == 200 and len(list_resp.json()) > 0)
    
    # Staff cannot create
    if staff_session:
        staff_create = staff_session.post(f"{BASE_URL}/barang", json=barang_data)
        log_test("Barang CRUD: staff create denied (403)", staff_create.status_code == 403)

def test_pengrajin_crud():
    """Test Pengrajin CRUD"""
    print("\n=== TESTING PENGRAJIN CRUD ===")
    
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("Pengrajin CRUD: admin login", False)
        return
    
    # Create pengrajin
    pengrajin_data = {
        "nama": f"Pak Budi {datetime.now().strftime('%H%M%S')}",
        "telepon": "081234567890",
        "alamat": "Jl. Test No. 123",
        "rekening": "1234567890",
        "catatan": "Test pengrajin"
    }
    create_resp = admin_session.post(f"{BASE_URL}/pengrajin", json=pengrajin_data)
    if create_resp.status_code == 200:
        pengrajin_id = create_resp.json().get("_id")
        log_test("Pengrajin CRUD: create", True, f"id={pengrajin_id}")
    else:
        log_test("Pengrajin CRUD: create", False, f"status {create_resp.status_code}")
        return
    
    # List pengrajin
    list_resp = admin_session.get(f"{BASE_URL}/pengrajin")
    log_test("Pengrajin CRUD: list", list_resp.status_code == 200 and len(list_resp.json()) > 0)

def test_po_crud():
    """Test PO CRUD"""
    print("\n=== TESTING PO CRUD ===")
    
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("PO CRUD: admin login", False)
        return
    
    # Get a barang for PO item
    barang_list = admin_session.get(f"{BASE_URL}/barang").json()
    if not barang_list:
        log_test("PO CRUD: no barang available", False, "create barang first")
        return
    
    barang_id = barang_list[0]["_id"]
    
    # Create PO
    po_data = {
        "no_po": f"PO-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "items": [
            {"barang_id": barang_id, "qty": 10, "catatan": "Test item"}
        ],
        "catatan": "Test PO"
    }
    create_resp = admin_session.post(f"{BASE_URL}/po", json=po_data)
    if create_resp.status_code == 200:
        po_id = create_resp.json().get("_id")
        log_test("PO CRUD: create", True, f"id={po_id}")
    else:
        log_test("PO CRUD: create", False, f"status {create_resp.status_code}")
        return
    
    # List PO
    list_resp = admin_session.get(f"{BASE_URL}/po")
    log_test("PO CRUD: list", list_resp.status_code == 200)

def test_exports():
    """PRIORITY 2: Test PDF/Excel exports (use GridFS via _fetch_image_flowable)"""
    print("\n=== TESTING EXPORTS (PDF/Excel with GridFS) ===")
    
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("Exports: admin login", False)
        return
    
    # Test staffing PDF export (GET request)
    pdf_resp = admin_session.get(f"{BASE_URL}/export/staffing/pdf")
    log_test("Exports: staffing PDF", pdf_resp.status_code == 200, 
             f"content-type={pdf_resp.headers.get('content-type', '')}, size={len(pdf_resp.content)} bytes")
    
    # Test staffing Excel export (GET request)
    excel_resp = admin_session.get(f"{BASE_URL}/export/staffing/excel")
    log_test("Exports: staffing Excel", excel_resp.status_code == 200,
             f"content-type={excel_resp.headers.get('content-type', '')}, size={len(excel_resp.content)} bytes")
    
    # Test barang-masuk PDF export (GET request)
    bm_pdf_resp = admin_session.get(f"{BASE_URL}/export/barang-masuk/pdf")
    log_test("Exports: barang-masuk PDF", bm_pdf_resp.status_code == 200,
             f"content-type={bm_pdf_resp.headers.get('content-type', '')}, size={len(bm_pdf_resp.content)} bytes")
    
    # Test barang-masuk Excel export (GET request)
    bm_excel_resp = admin_session.get(f"{BASE_URL}/export/barang-masuk/excel")
    log_test("Exports: barang-masuk Excel", bm_excel_resp.status_code == 200,
             f"content-type={bm_excel_resp.headers.get('content-type', '')}, size={len(bm_excel_resp.content)} bytes")

def test_rekap_endpoints():
    """Test Rekap endpoints"""
    print("\n=== TESTING REKAP ENDPOINTS ===")
    
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("Rekap: admin login", False)
        return
    
    # Test all rekap endpoints
    endpoints = [
        "/rekap/all-po",
        "/rekap/per-barang",
        "/rekap/progres",
        "/rekap/per-pengrajin"
    ]
    
    for endpoint in endpoints:
        resp = admin_session.get(f"{BASE_URL}{endpoint}")
        log_test(f"Rekap: GET {endpoint}", resp.status_code == 200)

def test_dashboard():
    """Test Dashboard endpoint"""
    print("\n=== TESTING DASHBOARD ===")
    
    admin_session, _ = login("admin")
    if not admin_session:
        log_test("Dashboard: admin login", False)
        return
    
    # Test kinerja pengrajin
    month = datetime.now().strftime("%Y-%m")
    resp = admin_session.get(f"{BASE_URL}/dashboard/kinerja-pengrajin?month={month}")
    log_test("Dashboard: kinerja-pengrajin", resp.status_code == 200)

def test_activity_log():
    """Test Activity Log endpoint"""
    print("\n=== TESTING ACTIVITY LOG ===")
    
    admin_session, _ = login("admin")
    owner_session, _ = login("owner")
    staff_session, _ = login("staff")
    
    if not admin_session:
        log_test("Activity Log: admin login", False)
        return
    
    # Admin can access
    admin_resp = admin_session.get(f"{BASE_URL}/activity-log")
    log_test("Activity Log: admin access", admin_resp.status_code == 200)
    
    # Owner can access
    if owner_session:
        owner_resp = owner_session.get(f"{BASE_URL}/activity-log")
        log_test("Activity Log: owner access", owner_resp.status_code == 200)
    
    # Staff cannot access
    if staff_session:
        staff_resp = staff_session.get(f"{BASE_URL}/activity-log")
        log_test("Activity Log: staff denied (403)", staff_resp.status_code == 403)

def print_summary():
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in test_results if r["status"])
    failed = sum(1 for r in test_results if not r["status"])
    total = len(test_results)
    
    print(f"\nTotal: {total} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for r in test_results:
            if not r["status"]:
                print(f"  - {r['name']}: {r['note']}")
    
    print("\n" + "="*60)

def main():
    """Run all tests"""
    print("="*60)
    print("AGFDATA Backend API Test Suite")
    print("Testing GridFS storage backend + full regression")
    print("="*60)
    
    # PRIORITY 1: File upload/download (the bug fix)
    test_auth()
    uploaded_path = test_file_upload_download()
    
    if uploaded_path:
        test_barang_with_image(uploaded_path)
    
    # PRIORITY 2: Regression tests
    test_barang_crud()
    test_pengrajin_crud()
    test_po_crud()
    
    # PRIORITY 2: Exports (use GridFS)
    test_exports()
    
    # PRIORITY 3: Other endpoints
    test_rekap_endpoints()
    test_dashboard()
    test_activity_log()
    
    # Print summary
    print_summary()

if __name__ == "__main__":
    main()
