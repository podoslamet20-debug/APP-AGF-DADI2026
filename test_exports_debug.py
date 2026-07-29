#!/usr/bin/env python3
"""Debug export endpoints to see actual error messages"""
import requests
import json

BASE_URL = "https://11a03a0d-d98a-445f-8f6d-5eb650bd3fb5.preview.emergentagent.com/api"

# Login as admin
session = requests.Session()
login_resp = session.post(f"{BASE_URL}/auth/login", json={
    "email": "admin@agfdata.com",
    "password": "admin123"
})

if login_resp.status_code != 200:
    print("Login failed!")
    exit(1)

print("Login successful\n")

# Test each export endpoint
endpoints = [
    ("staffing PDF", "/export/staffing/pdf"),
    ("staffing Excel", "/export/staffing/excel"),
    ("barang-masuk PDF", "/export/barang-masuk/pdf"),
    ("barang-masuk Excel", "/export/barang-masuk/excel"),
]

for name, endpoint in endpoints:
    print(f"Testing {name}: POST {endpoint}")
    resp = session.post(f"{BASE_URL}{endpoint}", json={})
    print(f"  Status: {resp.status_code}")
    print(f"  Content-Type: {resp.headers.get('content-type', 'N/A')}")
    
    if resp.headers.get('content-type', '').startswith('application/json'):
        try:
            error_data = resp.json()
            print(f"  Response: {json.dumps(error_data, indent=2)}")
        except Exception as e:
            print(f"  Response (text): {resp.text[:500]}")
    else:
        print(f"  Response size: {len(resp.content)} bytes")
    
    print()
