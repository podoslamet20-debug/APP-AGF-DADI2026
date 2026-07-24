from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Header, Query, UploadFile, File, Depends
from fastapi.responses import StreamingResponse, FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import requests
from io import BytesIO
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.utils import ImageReader
from PIL import Image as PILImage
import pandas as pd
import xlsxwriter

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Object Storage Setup
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "agfdata"
storage_key = None

# JWT Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "agfdata-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ===== Object Storage Functions =====
def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        resp.raise_for_status()
        storage_key = resp.json()["storage_key"]
        logger.info("Storage initialized successfully")
        return storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        raise

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str) -> tuple[bytes, str]:
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ===== Auth Functions =====
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])}, {"password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ===== Models =====
class LoginRequest(BaseModel):
    email: str
    password: str

class BarangCreate(BaseModel):
    nama_barang: str
    nama_pengrajin: str
    spesifikasi: str
    harga_pengrajin: float
    harga_jual: float
    catatan: Optional[str] = ""
    gambar_path: Optional[str] = None

class POItemCreate(BaseModel):
    barang_id: str
    qty: int
    catatan: Optional[str] = ""

class POCreate(BaseModel):
    no_po: str
    items: List[POItemCreate]
    catatan: Optional[str] = ""

class BarangMasukCreate(BaseModel):
    po_id: str
    tanggal_masuk: str
    penerima: str
    items: List[Dict[str, Any]]

class StaffingCreate(BaseModel):
    po_id: str
    tanggal_keluar: str
    items: List[Dict[str, Any]]

class SPKCreate(BaseModel):
    no_spk: str
    items: List[Dict[str, Any]]
    catatan_pembayaran: str
    owner_perusahaan: str
    deadline: str

class ProgresUpdate(BaseModel):
    barang_masuk_id: str
    item_id: str
    grinda: Optional[int] = 0
    servis: Optional[int] = 0
    finishing: Optional[int] = 0
    packing: Optional[int] = 0

# ===== Startup Event =====
@app.on_event("startup")
async def startup_event():
    try:
        # Initialize storage
        init_storage()
        logger.info("Storage initialized")
        
        # Create indexes
        await db.users.create_index("email", unique=True)
        await db.barang.create_index("nama_barang")
        await db.po.create_index("no_po", unique=True)
        
        # Seed admin user
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@agfdata.com")
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
        existing_admin = await db.users.find_one({"email": admin_email})
        
        if not existing_admin:
            hashed = hash_password(admin_password)
            await db.users.insert_one({
                "email": admin_email,
                "password_hash": hashed,
                "name": "Admin",
                "role": "admin",
                "created_at": datetime.now(timezone.utc)
            })
            logger.info(f"Admin user created: {admin_email}")
        
        # Create test users
        staff_email = "staff@agfdata.com"
        if not await db.users.find_one({"email": staff_email}):
            await db.users.insert_one({
                "email": staff_email,
                "password_hash": hash_password("staff123"),
                "name": "Staff User",
                "role": "staff",
                "created_at": datetime.now(timezone.utc)
            })
        
        guest_email = "tamu@agfdata.com"
        if not await db.users.find_one({"email": guest_email}):
            await db.users.insert_one({
                "email": guest_email,
                "password_hash": hash_password("tamu123"),
                "name": "Tamu User",
                "role": "guest",
                "created_at": datetime.now(timezone.utc)
            })
        
        # Write credentials to file
        os.makedirs("/app/memory", exist_ok=True)
        with open("/app/memory/test_credentials.md", "w") as f:
            f.write("# AGFDATA Test Credentials\n\n")
            f.write(f"## Admin\n- Email: {admin_email}\n- Password: {admin_password}\n- Role: admin\n\n")
            f.write(f"## Staff\n- Email: staff@agfdata.com\n- Password: staff123\n- Role: staff\n\n")
            f.write(f"## Guest\n- Email: tamu@agfdata.com\n- Password: tamu123\n- Role: guest\n\n")
            f.write("## Endpoints\n- POST /api/auth/login\n- GET /api/auth/me\n- POST /api/auth/logout\n")
        
        logger.info("Startup completed successfully")
    except Exception as e:
        logger.error(f"Startup error: {e}")

# ===== Auth Routes =====
@api_router.post("/auth/login")
async def login(request: LoginRequest, response: Response):
    user = await db.users.find_one({"email": request.email.lower()})
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_id = str(user["_id"])
    token = create_access_token(user_id, user["email"], user["role"])
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=86400,
        path="/"
    )
    
    return {
        "_id": user_id,
        "email": user["email"],
        "name": user["name"],
        "role": user["role"]
    }

@api_router.get("/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    return user

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out successfully"}

# ===== File Upload =====
@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    path = f"{APP_NAME}/uploads/{uuid.uuid4()}.{ext}"
    data = await file.read()
    
    result = put_object(path, data, file.content_type or "application/octet-stream")
    
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result["size"],
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {"path": result["path"], "url": f"/api/files/{result['path']}"}

@api_router.get("/files/{path:path}")
async def download_file(path: str, auth: Optional[str] = Query(None)):
    try:
        data, content_type = get_object(path)
        return Response(content=data, media_type=content_type)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

# ===== Barang Routes =====
@api_router.post("/barang")
async def create_barang(barang: BarangCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    doc = barang.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["_id"]
    result = await db.barang.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@api_router.get("/barang")
async def get_barang(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["$or"] = [
            {"nama_barang": {"$regex": search, "$options": "i"}},
            {"nama_pengrajin": {"$regex": search, "$options": "i"}}
        ]
    
    items = await db.barang.find(query).to_list(1000)
    for item in items:
        item["_id"] = str(item["_id"])
    
    # Hide prices for staff and guest
    if user["role"] in ["staff", "guest"]:
        for item in items:
            item.pop("harga_pengrajin", None)
            item.pop("harga_jual", None)
    
    # Hide craftsman name for guest
    if user["role"] == "guest":
        for item in items:
            item.pop("nama_pengrajin", None)
    
    return items

@api_router.get("/barang/{barang_id}")
async def get_barang_by_id(barang_id: str, user: dict = Depends(get_current_user)):
    item = await db.barang.find_one({"_id": ObjectId(barang_id)})
    if item: item["_id"] = str(item["_id"])
    if not item:
        raise HTTPException(status_code=404, detail="Barang not found")
    
    if user["role"] in ["staff", "guest"]:
        item.pop("harga_pengrajin", None)
        item.pop("harga_jual", None)
    
    if user["role"] == "guest":
        item.pop("nama_pengrajin", None)
    
    return item

# ===== PO Routes =====
@api_router.post("/po")
async def create_po(po: POCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get barang details for each item
    items_with_details = []
    for item in po.items:
        barang = await db.barang.find_one({"_id": ObjectId(item.barang_id)}, {"_id": 0})
        if not barang:
            raise HTTPException(status_code=404, detail=f"Barang {item.barang_id} not found")
        
        items_with_details.append({
            "barang_id": item.barang_id,
            "nama_barang": barang["nama_barang"],
            "nama_pengrajin": barang["nama_pengrajin"],
            "spesifikasi": barang["spesifikasi"],
            "gambar_path": barang.get("gambar_path"),
            "harga_pengrajin": barang["harga_pengrajin"],
            "harga_jual": barang["harga_jual"],
            "qty": item.qty,
            "qty_diterima": 0,
            "catatan": item.catatan
        })
    
    doc = {
        "no_po": po.no_po,
        "items": items_with_details,
        "catatan": po.catatan,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"]
    }
    
    result = await db.po.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@api_router.get("/po")
async def get_po(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["no_po"] = {"$regex": search, "$options": "i"}
    
    pos = await db.po.find(query).to_list(1000)
    for po in pos:
        po["_id"] = str(po["_id"])
    
    # Hide prices for staff and guest
    if user["role"] in ["staff", "guest"]:
        for po in pos:
            for item in po.get("items", []):
                item.pop("harga_pengrajin", None)
                item.pop("harga_jual", None)
    
    # Hide craftsman for guest
    if user["role"] == "guest":
        for po in pos:
            for item in po.get("items", []):
                item.pop("nama_pengrajin", None)
    
    return pos

@api_router.get("/po/{po_id}")
async def get_po_by_id(po_id: str, user: dict = Depends(get_current_user)):
    po = await db.po.find_one({"_id": ObjectId(po_id)})
    if po: po["_id"] = str(po["_id"])
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    if user["role"] in ["staff", "guest"]:
        for item in po.get("items", []):
            item.pop("harga_pengrajin", None)
            item.pop("harga_jual", None)
    
    if user["role"] == "guest":
        for item in po.get("items", []):
            item.pop("nama_pengrajin", None)
    
    return po

@api_router.put("/po/{po_id}")
async def update_po(po_id: str, po: POCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    items_with_details = []
    for item in po.items:
        barang = await db.barang.find_one({"_id": ObjectId(item.barang_id)}, {"_id": 0})
        if not barang:
            raise HTTPException(status_code=404, detail=f"Barang {item.barang_id} not found")
        
        items_with_details.append({
            "barang_id": item.barang_id,
            "nama_barang": barang["nama_barang"],
            "nama_pengrajin": barang["nama_pengrajin"],
            "spesifikasi": barang["spesifikasi"],
            "gambar_path": barang.get("gambar_path"),
            "harga_pengrajin": barang["harga_pengrajin"],
            "harga_jual": barang["harga_jual"],
            "qty": item.qty,
            "qty_diterima": 0,
            "catatan": item.catatan
        })
    
    await db.po.update_one(
        {"_id": ObjectId(po_id)},
        {"$set": {"no_po": po.no_po, "items": items_with_details, "catatan": po.catatan}}
    )
    
    return {"message": "PO updated"}

# ===== Barang Masuk Routes =====
@api_router.post("/barang-masuk")
async def create_barang_masuk(bm: BarangMasukCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    po = await db.po.find_one({"_id": ObjectId(bm.po_id)})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    doc = {
        "po_id": bm.po_id,
        "no_po": po["no_po"],
        "tanggal_masuk": bm.tanggal_masuk,
        "penerima": bm.penerima,
        "items": bm.items,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"]
    }
    
    result = await db.barang_masuk.insert_one(doc)
    
    # Update qty_diterima in PO
    for item in bm.items:
        await db.po.update_one(
            {"_id": ObjectId(bm.po_id), "items.barang_id": item["barang_id"]},
            {"$inc": {"items.$.qty_diterima": item["qty_diterima"]}}
        )
    
    doc["_id"] = str(result.inserted_id)
    return doc

@api_router.get("/barang-masuk")
async def get_barang_masuk(user: dict = Depends(get_current_user)):
    items = await db.barang_masuk.find({}).to_list(1000)
    for item in items:
        item["_id"] = str(item["_id"])
    
    if user["role"] in ["staff", "guest"]:
        for bm in items:
            for item in bm.get("items", []):
                item.pop("harga_pengrajin", None)
                item.pop("harga_jual", None)
    
    if user["role"] == "guest":
        for bm in items:
            for item in bm.get("items", []):
                item.pop("nama_pengrajin", None)
    
    return items

# ===== Staffing Routes =====
@api_router.post("/staffing")
async def create_staffing(staffing: StaffingCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    po = await db.po.find_one({"_id": ObjectId(staffing.po_id)})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    doc = {
        "po_id": staffing.po_id,
        "no_po": po["no_po"],
        "tanggal_keluar": staffing.tanggal_keluar,
        "items": staffing.items,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"]
    }
    
    result = await db.staffing.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@api_router.get("/staffing")
async def get_staffing(tanggal: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if tanggal:
        query["tanggal_keluar"] = tanggal
    
    items = await db.staffing.find(query).to_list(1000)
    for item in items:
        item["_id"] = str(item["_id"])
    
    if user["role"] in ["staff", "guest"]:
        for st in items:
            for item in st.get("items", []):
                item.pop("harga_pengrajin", None)
                item.pop("harga_jual", None)
    
    if user["role"] == "guest":
        for st in items:
            for item in st.get("items", []):
                item.pop("nama_pengrajin", None)
    
    return items

# ===== SPK Routes =====
@api_router.post("/spk")
async def create_spk(spk: SPKCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    doc = spk.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["_id"]
    
    result = await db.spk.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@api_router.get("/spk")
async def get_spk(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["no_spk"] = {"$regex": search, "$options": "i"}
    
    items = await db.spk.find(query).to_list(1000)
    for item in items:
        item["_id"] = str(item["_id"])
    
    if user["role"] in ["staff", "guest"]:
        for spk in items:
            for item in spk.get("items", []):
                item.pop("harga_pengrajin", None)
                item.pop("harga_jual", None)
    
    if user["role"] == "guest":
        for spk in items:
            for item in spk.get("items", []):
                item.pop("nama_pengrajin", None)
    
    return items

@api_router.put("/spk/{spk_id}")
async def update_spk(spk_id: str, spk: SPKCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.spk.update_one(
        {"_id": ObjectId(spk_id)},
        {"$set": spk.model_dump()}
    )
    
    return {"message": "SPK updated"}

# ===== Progres Barang Routes =====
@api_router.post("/progres")
async def update_progres(progres: ProgresUpdate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if progres exists
    existing = await db.progres.find_one({
        "barang_masuk_id": progres.barang_masuk_id,
        "item_id": progres.item_id
    })
    
    doc = {
        "barang_masuk_id": progres.barang_masuk_id,
        "item_id": progres.item_id,
        "grinda": progres.grinda,
        "servis": progres.servis,
        "finishing": progres.finishing,
        "packing": progres.packing,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if existing:
        await db.progres.update_one(
            {"barang_masuk_id": progres.barang_masuk_id, "item_id": progres.item_id},
            {"$set": doc}
        )
    else:
        result = await db.progres.insert_one(doc)
    
    doc.pop("_id", None)
    return doc

@api_router.get("/progres")
async def get_progres(user: dict = Depends(get_current_user)):
    items = await db.progres.find({}).to_list(1000)
    for item in items:
        item["_id"] = str(item["_id"])
    return items

# ===== Rekap Data Routes =====
@api_router.get("/rekap/all-po")
async def get_rekap_all_po(user: dict = Depends(get_current_user)):
    pos = await db.po.find({}).to_list(1000)
    staffing = await db.staffing.find({}).to_list(1000)
    for p in pos: p["_id"] = str(p["_id"])
    for s in staffing: s["_id"] = str(s["_id"])
    
    # Calculate remaining items (PO - Staffing)
    result = []
    for po in pos:
        for item in po.get("items", []):
            staffing_qty = sum(
                si["qty"] for s in staffing if s.get("po_id") == po["_id"]
                for si in s.get("items", []) if si.get("barang_id") == item.get("barang_id")
            )
            remaining = item["qty"] - staffing_qty
            result.append({
                "no_po": po["no_po"],
                "nama_barang": item["nama_barang"],
                "nama_pengrajin": item.get("nama_pengrajin", ""),
                "qty_po": item["qty"],
                "qty_staffing": staffing_qty,
                "remaining": remaining,
                "gambar_path": item.get("gambar_path")
            })
    
    if user["role"] == "guest":
        for r in result:
            r.pop("nama_pengrajin", None)
    
    return result

@api_router.get("/rekap/per-pengrajin")
async def get_rekap_per_pengrajin(user: dict = Depends(get_current_user)):
    if user["role"] == "guest":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    spks = await db.spk.find({}).to_list(1000)
    barang_masuk = await db.barang_masuk.find({}).to_list(1000)
    for s in spks: s["_id"] = str(s["_id"])
    for b in barang_masuk: b["_id"] = str(b["_id"])
    
    result = {}
    for spk in spks:
        for item in spk.get("items", []):
            pengrajin = item.get("nama_pengrajin", "Unknown")
            if pengrajin not in result:
                result[pengrajin] = {"spk_qty": 0, "masuk_qty": 0}
            result[pengrajin]["spk_qty"] += item.get("qty", 0)
    
    for bm in barang_masuk:
        for item in bm.get("items", []):
            pengrajin = item.get("nama_pengrajin", "Unknown")
            if pengrajin in result:
                result[pengrajin]["masuk_qty"] += item.get("qty_diterima", 0)
    
    return [{"pengrajin": k, **v, "remaining": v["spk_qty"] - v["masuk_qty"]} for k, v in result.items()]

# ===== Export Routes =====
@api_router.get("/export/po/{po_id}/pdf")
async def export_po_pdf(po_id: str, user: dict = Depends(get_current_user)):
    po = await db.po.find_one({"_id": ObjectId(po_id)})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm)
    story = []
    styles = getSampleStyleSheet()
    
    story.append(Paragraph(f"<b>Purchase Order</b>", styles["Title"]))
    story.append(Paragraph(f"No PO: {po['no_po']}", styles["Normal"]))
    story.append(Spacer(1, 12))
    
    data = [["Nama Barang", "Spesifikasi", "Qty", "Pengrajin"]]
    for item in po.get("items", []):
        data.append([
            item["nama_barang"],
            item["spesifikasi"],
            str(item["qty"]),
            item.get("nama_pengrajin", "")
        ])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
    ]))
    story.append(table)
    
    doc.build(story)
    buffer.seek(0)
    
    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=po-{po['no_po']}.pdf"
    })

@api_router.get("/export/spk/{spk_id}/pdf")
async def export_spk_pdf(spk_id: str, user: dict = Depends(get_current_user)):
    spk = await db.spk.find_one({"_id": ObjectId(spk_id)})
    if not spk:
        raise HTTPException(status_code=404, detail="SPK not found")
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm)
    story = []
    styles = getSampleStyleSheet()
    
    story.append(Paragraph(f"<b>Surat Perintah Kerja (SPK)</b>", styles["Title"]))
    story.append(Paragraph(f"No SPK: {spk['no_spk']}", styles["Normal"]))
    story.append(Paragraph(f"Deadline: {spk['deadline']}", styles["Normal"]))
    story.append(Spacer(1, 12))
    
    data = [["Nama Barang", "Spesifikasi", "Qty", "Pengrajin"]]
    for item in spk.get("items", []):
        data.append([
            item["nama_barang"],
            item["spesifikasi"],
            str(item["qty"]),
            item.get("nama_pengrajin", "")
        ])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Catatan Pembayaran: {spk.get('catatan_pembayaran', '')}", styles["Normal"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Owner: {spk.get('owner_perusahaan', '')}", styles["Normal"]))
    
    doc.build(story)
    buffer.seek(0)
    
    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=spk-{spk['no_spk']}.pdf"
    })

@api_router.get("/export/barang-masuk/excel")
async def export_barang_masuk_excel(user: dict = Depends(get_current_user)):
    items = await db.barang_masuk.find({}).to_list(1000)
    
    data = []
    for bm in items:
        for item in bm.get("items", []):
            data.append({
                "No PO": bm.get("no_po", ""),
                "Tanggal Masuk": bm.get("tanggal_masuk", ""),
                "Penerima": bm.get("penerima", ""),
                "Nama Barang": item.get("nama_barang", ""),
                "Qty Diterima": item.get("qty_diterima", 0)
            })
    
    if not data:
        data = [{"No PO": "", "Tanggal Masuk": "", "Penerima": "", "Nama Barang": "", "Qty Diterima": 0}]
    df = pd.DataFrame(data)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Barang Masuk')
    buffer.seek(0)
    
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": "attachment; filename=barang-masuk.xlsx"
    })

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
