#!/usr/bin/env python3
"""
Additional GridFS tests - verify byte integrity and larger files
"""
import requests
import io
from PIL import Image
import hashlib

BASE_URL = "https://11a03a0d-d98a-445f-8f6d-5eb650bd3fb5.preview.emergentagent.com/api"

def create_test_image(size=(100, 100), color=(255, 0, 0), format="PNG"):
    """Create a test image in memory"""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf

def login_admin():
    """Login as admin"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@agfdata.com",
        "password": "admin123"
    })
    if resp.status_code == 200:
        return session
    return None

print("="*60)
print("ADDITIONAL GRIDFS INTEGRITY TESTS")
print("="*60)

session = login_admin()
if not session:
    print("❌ Failed to login as admin")
    exit(1)

print("✅ Logged in as admin\n")

# Test 1: Verify byte integrity (upload and download should match)
print("Test 1: Byte integrity check")
test_img = create_test_image(size=(300, 300), color=(128, 64, 192), format="PNG")
original_bytes = test_img.read()
original_hash = hashlib.md5(original_bytes).hexdigest()
test_img.seek(0)

files = {"file": ("integrity_test.png", test_img, "image/png")}
upload_resp = session.post(f"{BASE_URL}/upload", files=files)

if upload_resp.status_code == 200:
    path = upload_resp.json()["path"]
    print(f"  ✅ Uploaded: {path}")
    
    # Download and verify
    download_resp = requests.get(f"{BASE_URL}/files/{path}")
    if download_resp.status_code == 200:
        downloaded_bytes = download_resp.content
        downloaded_hash = hashlib.md5(downloaded_bytes).hexdigest()
        
        if original_hash == downloaded_hash:
            print(f"  ✅ Byte integrity verified: {original_hash}")
        else:
            print(f"  ❌ Byte mismatch! Original: {original_hash}, Downloaded: {downloaded_hash}")
    else:
        print(f"  ❌ Download failed: {download_resp.status_code}")
else:
    print(f"  ❌ Upload failed: {upload_resp.status_code}")

# Test 2: Larger file (~1MB)
print("\nTest 2: Large file upload (~1MB)")
large_img = create_test_image(size=(2000, 2000), color=(255, 128, 0), format="PNG")
large_bytes = large_img.read()
large_size_mb = len(large_bytes) / (1024 * 1024)
large_img.seek(0)

files = {"file": ("large_test.png", large_img, "image/png")}
upload_resp = session.post(f"{BASE_URL}/upload", files=files)

if upload_resp.status_code == 200:
    path = upload_resp.json()["path"]
    print(f"  ✅ Uploaded large file: {large_size_mb:.2f} MB")
    
    # Download and verify size
    download_resp = requests.get(f"{BASE_URL}/files/{path}")
    if download_resp.status_code == 200:
        downloaded_size_mb = len(download_resp.content) / (1024 * 1024)
        print(f"  ✅ Downloaded: {downloaded_size_mb:.2f} MB")
        
        if len(large_bytes) == len(download_resp.content):
            print(f"  ✅ Size match verified")
        else:
            print(f"  ❌ Size mismatch! Original: {len(large_bytes)}, Downloaded: {len(download_resp.content)}")
    else:
        print(f"  ❌ Download failed: {download_resp.status_code}")
else:
    print(f"  ❌ Upload failed: {upload_resp.status_code}")

# Test 3: Multiple uploads (overwrite test)
print("\nTest 3: Multiple uploads with same filename pattern")
for i in range(3):
    test_img = create_test_image(size=(100, 100), color=(i*50, i*50, i*50), format="PNG")
    files = {"file": (f"multi_test_{i}.png", test_img, "image/png")}
    upload_resp = session.post(f"{BASE_URL}/upload", files=files)
    
    if upload_resp.status_code == 200:
        path = upload_resp.json()["path"]
        print(f"  ✅ Upload {i+1}: {path}")
    else:
        print(f"  ❌ Upload {i+1} failed: {upload_resp.status_code}")

# Test 4: JPEG format
print("\nTest 4: JPEG format upload/download")
jpeg_img = create_test_image(size=(400, 400), color=(0, 128, 255), format="JPEG")
jpeg_bytes = jpeg_img.read()
jpeg_hash = hashlib.md5(jpeg_bytes).hexdigest()
jpeg_img.seek(0)

files = {"file": ("test.jpg", jpeg_img, "image/jpeg")}
upload_resp = session.post(f"{BASE_URL}/upload", files=files)

if upload_resp.status_code == 200:
    path = upload_resp.json()["path"]
    print(f"  ✅ Uploaded JPEG: {path}")
    
    download_resp = requests.get(f"{BASE_URL}/files/{path}")
    if download_resp.status_code == 200:
        content_type = download_resp.headers.get("content-type", "")
        downloaded_hash = hashlib.md5(download_resp.content).hexdigest()
        
        print(f"  ✅ Content-Type: {content_type}")
        if jpeg_hash == downloaded_hash:
            print(f"  ✅ JPEG integrity verified")
        else:
            print(f"  ❌ JPEG byte mismatch")
    else:
        print(f"  ❌ Download failed: {download_resp.status_code}")
else:
    print(f"  ❌ Upload failed: {upload_resp.status_code}")

print("\n" + "="*60)
print("ADDITIONAL TESTS COMPLETE")
print("="*60)
