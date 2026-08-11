from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Header, Query, UploadFile, File, Depends
from fastapi.responses import StreamingResponse, FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from gridfs import GridFS
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

# MongoDB connection (async for FastAPI endpoints)
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# Sync MongoDB + GridFS for file storage (used by sync helpers like ReportLab PDF gen)
_sync_client = MongoClient(mongo_url)
_sync_db = _sync_client[db_name]
fs = GridFS(_sync_db)

# App name (used as path prefix for uploaded files)
APP_NAME = "agfdata"

# JWT Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "agfdata-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"

# Create the main app
app = FastAPI()

# ===== CORS Middleware =====
default_origins = (
    "https://app.agfdata.com,"
    "https://app-agf-dadi2026-frontend-production.up.railway.app,"
    "http://localhost:3000,"
    "http://localhost:8080"
)
cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Credentials Header Middleware =====
@app.middleware("http")
async def add_credentials_header_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")
    response = await call_next(request)
    if origin in cors_origins:
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

api_router = APIRouter(prefix="/api")

# ===== Health Check =====
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/health")
async def health_check_api():
    """Health check with /api prefix (used by Railway healthcheck + Kubernetes ingress)."""
    return {"status": "ok", "service": "agfdata-backend"}

# ===== Activity Log Middleware =====
# Descriptions for common endpoints to make logs readable
RESOURCE_LABEL = {
    "barang": "Database Barang",
    "po": "PO",
    "barang-masuk": "Barang Masuk",
    "staffing": "Staffing",
    "spk": "SPK",
    "progres": "Progres Barang",
    "users": "User Management",
    "user": "User Management",
    "auth": "Auth",
    "rekap": "Rekap Data",
    "upload": "File Upload",
    "export": "Export",
    "files": "Files",
    "activity-log": "Activity Log",
}

def _decode_token_safe(token: Optional[str]) -> Optional[dict]:
    if not token: return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access": return None
        return payload
    except Exception:
        return None


@app.middleware("http")
async def activity_log_middleware(request: Request, call_next):
    # Capture path early
    method = request.method
    path = request.url.path
    response = await call_next(request)
    try:
        # Only log successful mutating calls on /api/ (skip GETs, uploads, exports, and the log itself)
        if (
            method in ("POST", "PUT", "DELETE", "PATCH")
            and path.startswith("/api/")
            and response.status_code < 400
            and "/activity-log" not in path
            and "/upload" not in path
        ):
            token = request.cookies.get("access_token")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            payload = _decode_token_safe(token)
            
            # For login endpoint, response body may include user; but we can't easily read here — login endpoint logs explicitly
            if path == "/api/auth/login":
                # skip; handled explicitly in login()
                return response
            
            # Skip logout too (handled explicitly for symmetry)
            if path == "/api/auth/logout":
                return response
            
            user_id = payload.get("sub", "") if payload else ""
            user_email = payload.get("email", "") if payload else "anonymous"
            user_role = payload.get("role", "") if payload else ""
            
            # Extract resource + optional id from path
            parts = path.replace("/api/", "").split("/")
            resource_key = parts[0] if parts else ""
            resource_id = parts[1] if len(parts) > 1 else ""
            action_map = {"POST": "create", "PUT": "update", "DELETE": "delete", "PATCH": "update"}
            
            await db.activity_log.insert_one({
                "user_id": user_id,
                "user_email": user_email,
                "user_role": user_role,
                "action": action_map.get(method, method.lower()),
                "resource": resource_key,
                "resource_label": RESOURCE_LABEL.get(resource_key, resource_key),
                "resource_id": resource_id,
                "path": path,
                "method": method,
                "status_code": response.status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ip": request.client.host if request.client else "",
            })
    except Exception as e:
        try: logger.warning(f"activity_log middleware error: {e}")
        except Exception: pass
    return response


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ===== Object Storage Functions (MongoDB GridFS) =====
# Portable storage that works on Emergent, Railway, or any MongoDB deployment.
# Files are stored inside MongoDB (in `fs.files` + `fs.chunks` collections).
def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Upload bytes to GridFS. Overwrites any existing file with the same path (filename)."""
    try:
        # Remove any previous versions with the same filename (path)
        for existing in fs.find({"filename": path}):
            fs.delete(existing._id)
        fs.put(data, filename=path, contentType=content_type or "application/octet-stream")
        return {"path": path, "size": len(data)}
    except Exception as e:
        logger.error(f"GridFS put_object failed for {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Upload gagal: {e}")

def get_object(path: str) -> tuple[bytes, str]:
    """Fetch bytes + content_type from GridFS by path (filename)."""
    grid_file = fs.find_one({"filename": path})
    if not grid_file:
        raise FileNotFoundError(f"File not found in storage: {path}")
    content_type = getattr(grid_file, "contentType", None) or getattr(grid_file, "content_type", None) or "application/octet-stream"
    return grid_file.read(), content_type

def delete_object(path: str) -> bool:
    """Delete a file from GridFS. Returns True if deleted, False if not found."""
    found = False
    try:
        for existing in fs.find({"filename": path}):
            fs.delete(existing._id)
            found = True
    except Exception as e:
        logger.warning(f"GridFS delete_object failed for {path}: {e}")
    return found

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
    nama_pengrajin: Optional[str] = ""  # DEPRECATED — kept for legacy display only
    spesifikasi: str
    harga_pengrajin: float
    harga_jual: float
    catatan: Optional[str] = ""
    gambar_path: Optional[str] = None
    pengrajin_list: Optional[List[str]] = []  # DEPRECATED — legacy field

class PengrajinCreate(BaseModel):
    nama: str
    telepon: Optional[str] = ""
    alamat: Optional[str] = ""
    rekening: Optional[str] = ""
    catatan: Optional[str] = ""

class POItemCreate(BaseModel):
    barang_id: str
    qty: int
    catatan: Optional[str] = ""

class POCreate(BaseModel):
    no_po: str
    items: List[POItemCreate]
    catatan: Optional[str] = ""

class BarangMasukItem(BaseModel):
    barang_id: str
    qty_diterima: int = Field(ge=0)
    pengrajin_id: Optional[str] = None
    pengrajin_nama: Optional[str] = None
    # Optional passthrough metadata (frontend may include these; ignored server-side for validation)
    nama_barang: Optional[str] = None
    nama_pengrajin: Optional[str] = None
    spesifikasi: Optional[str] = None
    gambar_path: Optional[str] = None
    harga_pengrajin: Optional[float] = None
    harga_jual: Optional[float] = None
    qty: Optional[int] = None
    catatan: Optional[str] = None

class BarangMasukCreate(BaseModel):
    po_id: str
    tanggal_masuk: str
    penerima: str
    items: List[BarangMasukItem]

class StaffingItem(BaseModel):
    barang_id: str
    qty: int = Field(ge=0)
    # Optional passthrough metadata
    nama_barang: Optional[str] = None
    nama_pengrajin: Optional[str] = None
    spesifikasi: Optional[str] = None
    gambar_path: Optional[str] = None
    harga_pengrajin: Optional[float] = None
    harga_jual: Optional[float] = None
    qty_diterima: Optional[int] = None
    catatan: Optional[str] = None

class StaffingCreate(BaseModel):
    po_id: str
    tanggal_keluar: str
    items: List[StaffingItem]

class SPKAllocation(BaseModel):
    pengrajin_id: str
    pengrajin_nama: Optional[str] = ""
    qty: int = Field(ge=1)

class SPKItem(BaseModel):
    barang_id: Optional[str] = None
    nama_barang: str
    spesifikasi: Optional[str] = ""
    qty: int = Field(ge=1)
    no_po: Optional[str] = ""
    # NEW single-pengrajin-per-line model (recommended):
    pengrajin_id: Optional[str] = None
    pengrajin_nama: Optional[str] = ""
    # DEPRECATED fields (kept for legacy display):
    nama_pengrajin: Optional[str] = ""
    pengrajin_list: Optional[List[str]] = Field(default_factory=list)
    allocations: List[SPKAllocation] = Field(default_factory=list)  # legacy multi-alloc
    harga: Optional[float] = 0
    gambar_path: Optional[str] = None
    catatan: Optional[str] = ""

class SPKCreate(BaseModel):
    no_spk: str
    items: List[SPKItem]
    catatan_pembayaran: str
    owner_perusahaan: str
    deadline: str

class ProgresEntry(BaseModel):
    po_id: Optional[str] = None
    item_id: str
    stage: str  # "grinda" | "servis" | "finishing" | "packing"
    qty: int = Field(ge=1)
    tanggal: Optional[str] = None
    pengrajin_id: Optional[str] = None  # NEW: which pengrajin's allocation
    pengrajin_nama: Optional[str] = None
    # Optional metadata (denormalized for display when item isn't from PO)
    nama_barang: Optional[str] = None
    nama_pengrajin: Optional[str] = None
    spesifikasi: Optional[str] = None
    gambar_path: Optional[str] = None
    # NEW: 5 Finishing Catatan Columns
    catatan_finishing_1: Optional[str] = None
    catatan_finishing_2: Optional[str] = None
    catatan_finishing_3: Optional[str] = None
    catatan_finishing_4: Optional[str] = None
    catatan_finishing_5: Optional[str] = None

VALID_STAGES = ["grinda", "servis", "finishing", "packing"]
PREV_STAGE = {"grinda": None, "servis": "grinda", "finishing": "servis", "packing": "finishing"}

# ===== Startup Event =====
@app.on_event("startup")
async def startup_event():
    try:
        # Storage: using MongoDB GridFS — no external service required (works on Railway + Emergent)
        try:
            logger.info(f"Storage backend: MongoDB GridFS on DB '{db_name}' (files stored in fs.files / fs.chunks)")
        except Exception as e:
            logger.warning(f"Storage log failed (non-fatal): {e}")
        
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
        
        # Seed owner user
        owner_email = "owner@agfdata.com"
        if not await db.users.find_one({"email": owner_email}):
            await db.users.insert_one({
                "email": owner_email,
                "password_hash": hash_password("owner123"),
                "name": "Owner",
                "role": "owner",
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
            f.write(f"## Owner\n- Email: owner@agfdata.com\n- Password: owner123\n- Role: owner (view-all incl. prices & activity log, no edit)\n\n")
            f.write("## Endpoints\n- POST /api/auth/login\n- GET /api/auth/me\n- POST /api/auth/logout\n")
        
        # Migration: convert legacy cumulative progres docs to stage entries.
        try:
            legacy_count = await db.progres.count_documents({"stage": {"$exists": False}, "$or": [{"grinda": {"$gt": 0}}, {"servis": {"$gt": 0}}, {"finishing": {"$gt": 0}}, {"packing": {"$gt": 0}}]})
            if legacy_count > 0:
                logger.info(f"Migrating {legacy_count} legacy progres docs to stage entries…")
                async for old in db.progres.find({"stage": {"$exists": False}}):
                    po_id = old.get("po_id", "") or ""
                    item_id = old.get("item_id", "")
                    tgl = old.get("tanggal") or (old.get("updated_at", "")[:10] if old.get("updated_at") else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
                    meta = {mk: old.get(mk) for mk in ("nama_barang", "nama_pengrajin", "spesifikasi", "gambar_path") if old.get(mk)}
                    for stage in ["grinda", "servis", "finishing", "packing"]:
                        qty = int(old.get(stage, 0) or 0)
                        if qty > 0:
                            await db.progres.insert_one({
                                "po_id": po_id,
                                "item_id": item_id,
                                "stage": stage,
                                "qty": qty,
                                "tanggal": tgl,
                                "created_at": old.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                                "created_by": "migration",
                                **meta,
                            })
                # Remove old cumulative docs after migration
                await db.progres.delete_many({"stage": {"$exists": False}})
                logger.info(f"Migration complete: {legacy_count} legacy docs converted.")
        except Exception as e:
            logger.error(f"Progres migration error: {e}")
        
        # Index for progres entries
        await db.progres.create_index([("po_id", 1), ("item_id", 1), ("stage", 1)])
        await db.progres.create_index([("tanggal", -1)])
        
        # Index for activity_log
        await db.activity_log.create_index([("timestamp", -1)])
        await db.activity_log.create_index([("user_id", 1)])
        await db.activity_log.create_index([("resource", 1)])
        
        # Rebalance legacy progres: for each PO+barang, ensure downstream stage sums ≤ upstream.
        # Guarded by a marker doc in db.migrations so it only runs once per DB.
        try:
            marker = await db.migrations.find_one({"name": "progres_rebalance_v1"})
            if marker:
                logger.info("Progres rebalance already applied (skipping).")
            else:
                pipeline = [
                    {"$match": {"stage": {"$in": VALID_STAGES}}},
                    {"$group": {"_id": {"po_id": "$po_id", "item_id": "$item_id", "stage": "$stage"}, "total": {"$sum": "$qty"}}},
                ]
                grouped: Dict[tuple, Dict[str, int]] = {}
                async for r in db.progres.aggregate(pipeline):
                    _id = r["_id"]
                    k = (_id.get("po_id", ""), _id.get("item_id", ""))
                    grouped.setdefault(k, {s: 0 for s in VALID_STAGES})
                    grouped[k][_id["stage"]] = int(r.get("total", 0) or 0)
                
                rebalanced = 0
                for (po_id, item_id), stage_sums in grouped.items():
                    qty_masuk = 0
                    if po_id:
                        async for bm in db.barang_masuk.find({"po_id": po_id}):
                            for it in bm.get("items", []):
                                if it.get("barang_id") == item_id:
                                    qty_masuk += it.get("qty_diterima", 0) or 0
                    for stage in VALID_STAGES:
                        upstream = qty_masuk if stage == "grinda" else stage_sums[PREV_STAGE[stage]]
                        excess = stage_sums[stage] - upstream
                        if excess > 0:
                            remaining = excess
                            async for e in db.progres.find({"po_id": po_id, "item_id": item_id, "stage": stage}).sort([("created_at", -1)]):
                                if remaining <= 0: break
                                eq = int(e.get("qty", 0) or 0)
                                if eq <= remaining:
                                    await db.progres.delete_one({"_id": e["_id"]})
                                    remaining -= eq
                                else:
                                    await db.progres.update_one({"_id": e["_id"]}, {"$set": {"qty": eq - remaining, "rebalanced": True}})
                                    remaining = 0
                            stage_sums[stage] = upstream
                            rebalanced += 1
                await db.migrations.insert_one({"name": "progres_rebalance_v1", "ran_at": datetime.now(timezone.utc).isoformat(), "groups_fixed": rebalanced})
                logger.info(f"Progres rebalance v1 applied: fixed {rebalanced} inconsistent PO+barang stage sums.")
        except Exception as e:
            logger.error(f"Progres rebalance error: {e}")
        
        # Migration: clean legacy progres records with empty po_id
        try:
            legacy = await db.progres.count_documents({"po_id": ""})
            if legacy > 0:
                await db.progres.delete_many({"po_id": ""})
                logger.info(f"Migrated: removed {legacy} legacy progres records with empty po_id")
        except Exception as e:
            logger.warning(f"Migration warning: {e}")
        
        logger.info("Startup completed successfully")
    except Exception as e:
        logger.error(f"Startup error: {e}")

# ===== Auth Routes =====
@api_router.post("/auth/login")
async def login(request: LoginRequest, req: Request, response: Response):
    user = await db.users.find_one({"email": request.email.lower()})
    if not user or not verify_password(request.password, user["password_hash"]):
        # Log failed attempt
        try:
            await db.activity_log.insert_one({
                "user_id": "", "user_email": request.email.lower(), "user_role": "",
                "action": "login_failed", "resource": "auth", "resource_label": "Auth",
                "resource_id": "", "path": "/api/auth/login", "method": "POST",
                "status_code": 401, "timestamp": datetime.now(timezone.utc).isoformat(),
                "ip": req.client.host if req.client else "",
            })
        except Exception: pass
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_id = str(user["_id"])
    token = create_access_token(user_id, user["email"], user["role"])
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=True,
        samesite="none", max_age=86400, path="/"
    )
    
    # Log successful login
    try:
        await db.activity_log.insert_one({
            "user_id": user_id, "user_email": user["email"], "user_role": user["role"],
            "action": "login", "resource": "auth", "resource_label": "Auth",
            "resource_id": user_id, "path": "/api/auth/login", "method": "POST",
            "status_code": 200, "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip": req.client.host if req.client else "",
            "detail": f"{user['name']} ({user['role']}) login",
        })
    except Exception: pass
    
    # Include the token in the response body as well. Mobile browsers (iOS Safari,
    # some Android webviews) can be inconsistent about persisting Set-Cookie
    # headers, especially across cross-site/cross-subdomain requests. Returning
    # the token lets the frontend store it in localStorage and fall back to
    # sending it via the Authorization header on subsequent requests.
    return {
        "_id": user_id, "email": user["email"], "name": user["name"], "role": user["role"],
        "access_token": token,
    }

@api_router.get("/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    return user

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    # Log logout
    try:
        token = request.cookies.get("access_token")
        payload = _decode_token_safe(token)
        if payload:
            await db.activity_log.insert_one({
                "user_id": payload.get("sub", ""), "user_email": payload.get("email", ""),
                "user_role": payload.get("role", ""), "action": "logout",
                "resource": "auth", "resource_label": "Auth", "resource_id": "",
                "path": "/api/auth/logout", "method": "POST", "status_code": 200,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ip": request.client.host if request.client else "",
            })
    except Exception: pass
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
            item.pop("pengrajin_list", None)
    
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
        item.pop("pengrajin_list", None)
    
    return item

# ===== Helper: aggregate packing (ready) qty per PO+barang from progres entries =====
async def _get_packing_map(po_id: Optional[str] = None) -> Dict[str, int]:
    """Return { f"{po_id}_{barang_id}": packing_total } via MongoDB $group over new-format stage entries."""
    match: Dict[str, Any] = {"stage": "packing"}
    if po_id:
        match["po_id"] = po_id
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"po_id": "$po_id", "item_id": "$item_id"}, "total": {"$sum": "$qty"}}},
    ]
    m: Dict[str, int] = {}
    async for r in db.progres.aggregate(pipeline):
        _id = r.get("_id", {})
        k = f"{_id.get('po_id','')}_{_id.get('item_id','')}"
        m[k] = int(r.get("total", 0) or 0)
    return m

async def _get_stage_sums(po_id: str, item_id: str) -> Dict[str, int]:
    """Return {'grinda':X, 'servis':Y, 'finishing':Z, 'packing':W} sum of entries for this PO+barang."""
    pipeline = [
        {"$match": {"po_id": po_id, "item_id": item_id, "stage": {"$in": VALID_STAGES}}},
        {"$group": {"_id": "$stage", "total": {"$sum": "$qty"}}},
    ]
    sums = {s: 0 for s in VALID_STAGES}
    async for r in db.progres.aggregate(pipeline):
        sums[r["_id"]] = int(r.get("total", 0) or 0)
    return sums

async def _get_qty_masuk(po_id: str, item_id: str) -> int:
    """Sum of qty_diterima for this PO+barang across all barang_masuk records."""
    pipeline = [
        {"$match": {"po_id": po_id}},
        {"$unwind": "$items"},
        {"$match": {"items.barang_id": item_id}},
        {"$group": {"_id": None, "total": {"$sum": "$items.qty_diterima"}}},
    ]
    async for r in db.barang_masuk.aggregate(pipeline):
        return int(r.get("total", 0) or 0)
    return 0

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
            "qty_staffed": 0,
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
    
    # Enrich items with qty_ready (packing sum from progres per PO+barang)
    packing_map = await _get_packing_map()
    for po in pos:
        for item in po.get("items", []):
            k = f"{po['_id']}_{item.get('barang_id','')}"
            item["qty_ready"] = packing_map.get(k, 0)
    
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
                item.pop("pengrajin_list", None)
    
    return pos

@api_router.get("/po/{po_id}")
async def get_po_by_id(po_id: str, user: dict = Depends(get_current_user)):
    po = await db.po.find_one({"_id": ObjectId(po_id)})
    if po: po["_id"] = str(po["_id"])
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    packing_map = await _get_packing_map(po_id)
    for item in po.get("items", []):
        k = f"{po_id}_{item.get('barang_id','')}"
        item["qty_ready"] = packing_map.get(k, 0)
    
    if user["role"] in ["staff", "guest"]:
        for item in po.get("items", []):
            item.pop("harga_pengrajin", None)
            item.pop("harga_jual", None)
    
    if user["role"] == "guest":
        for item in po.get("items", []):
            item.pop("nama_pengrajin", None)
            item.pop("pengrajin_list", None)
    
    return po

@api_router.put("/po/{po_id}")
async def update_po(po_id: str, po: POCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Fetch existing PO to preserve cumulative counters (qty_staffed, qty_diterima)
    existing_po = await db.po.find_one({"_id": ObjectId(po_id)})
    if not existing_po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    existing_counters = {
        it.get("barang_id"): {
            "qty_diterima": it.get("qty_diterima", 0) or 0,
            "qty_staffed": it.get("qty_staffed", 0) or 0,
        }
        for it in existing_po.get("items", [])
    }
    
    items_with_details = []
    for item in po.items:
        barang = await db.barang.find_one({"_id": ObjectId(item.barang_id)}, {"_id": 0})
        if not barang:
            raise HTTPException(status_code=404, detail=f"Barang {item.barang_id} not found")
        
        prev = existing_counters.get(item.barang_id, {"qty_diterima": 0, "qty_staffed": 0})
        items_with_details.append({
            "barang_id": item.barang_id,
            "nama_barang": barang["nama_barang"],
            "nama_pengrajin": barang["nama_pengrajin"],
            "pengrajin_list": barang.get("pengrajin_list", []) or [],
            "spesifikasi": barang["spesifikasi"],
            "gambar_path": barang.get("gambar_path"),
            "harga_pengrajin": barang["harga_pengrajin"],
            "harga_jual": barang["harga_jual"],
            "qty": item.qty,
            "qty_diterima": prev["qty_diterima"],
            "qty_staffed": prev["qty_staffed"],
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
    
    # Validate: qty_diterima ≤ (SPK-alloc - already received for this pengrajin) if pengrajin_id present;
    # else fallback to PO-level (qty_po - qty_diterima).
    po_items_map = {it.get("barang_id"): it for it in po.get("items", [])}
    items_dicts = []
    for it in bm.items:
        po_item = po_items_map.get(it.barang_id)
        if not po_item:
            raise HTTPException(status_code=400, detail=f"Barang {it.barang_id} tidak ada di PO ini")
        if it.pengrajin_id:
            alloc = await _get_spk_allocation(bm.po_id, it.barang_id, it.pengrajin_id)
            if alloc <= 0:
                raise HTTPException(status_code=400, detail=f"Belum ada alokasi SPK untuk pengrajin ini pada '{po_item.get('nama_barang','')}'. Buat SPK dulu.")
            already = await _get_bm_qty_per_pengrajin(bm.po_id, it.barang_id, it.pengrajin_id)
            sisa = alloc - already
            if it.qty_diterima > sisa:
                raise HTTPException(status_code=400, detail=f"Qty diterima ({it.qty_diterima}) untuk '{po_item.get('nama_barang','')}' pengrajin '{it.pengrajin_nama or ''}' melebihi sisa alokasi (alokasi: {alloc}, sudah diterima: {already}, sisa: {max(sisa,0)})")
        else:
            sisa = (po_item.get("qty", 0) or 0) - (po_item.get("qty_diterima", 0) or 0)
            if it.qty_diterima > sisa:
                raise HTTPException(status_code=400, detail=f"Qty diterima untuk {po_item.get('nama_barang','')} melebihi sisa PO (sisa: {sisa}, diminta: {it.qty_diterima})")
        items_dicts.append({
            **it.model_dump(exclude_none=True),
            "nama_barang": po_item.get("nama_barang", ""),
            "nama_pengrajin": it.pengrajin_nama or po_item.get("nama_pengrajin", ""),
            "spesifikasi": po_item.get("spesifikasi", ""),
            "gambar_path": po_item.get("gambar_path"),
        })
    
    doc = {
        "po_id": bm.po_id,
        "no_po": po["no_po"],
        "tanggal_masuk": bm.tanggal_masuk,
        "penerima": bm.penerima,
        "items": items_dicts,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"]
    }
    
    result = await db.barang_masuk.insert_one(doc)
    
    # Update qty_diterima in PO
    for item in items_dicts:
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
    
    # Validate: qty cannot exceed remaining (qty_po - qty_staffed_current) AND (qty_ready - qty_staffed_current)
    po_items_map = {it.get("barang_id"): it for it in po.get("items", [])}
    packing_map = await _get_packing_map(staffing.po_id)
    items_dicts = []
    for it in staffing.items:
        po_item = po_items_map.get(it.barang_id)
        if not po_item:
            raise HTTPException(status_code=400, detail=f"Barang {it.barang_id} tidak ada di PO ini")
        qty_staffed = po_item.get("qty_staffed", 0) or 0
        qty_ready = packing_map.get(f"{staffing.po_id}_{it.barang_id}", 0)
        sisa_po = (po_item.get("qty", 0) or 0) - qty_staffed
        sisa_ready = qty_ready - qty_staffed
        sisa = min(sisa_po, sisa_ready)
        if it.qty > sisa:
            raise HTTPException(
                status_code=400,
                detail=f"Qty staffing untuk {po_item.get('nama_barang','')} melebihi sisa yang siap (Ready: {qty_ready}, sudah dikirim: {qty_staffed}, sisa: {max(sisa,0)}, diminta: {it.qty})"
            )
        items_dicts.append({
            **it.model_dump(exclude_none=True),
            "nama_barang": po_item.get("nama_barang", ""),
            "nama_pengrajin": po_item.get("nama_pengrajin", ""),
            "spesifikasi": po_item.get("spesifikasi", ""),
            "gambar_path": po_item.get("gambar_path"),
        })
    
    doc = {
        "po_id": staffing.po_id,
        "no_po": po["no_po"],
        "tanggal_keluar": staffing.tanggal_keluar,
        "items": items_dicts,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"]
    }
    
    result = await db.staffing.insert_one(doc)
    
    # Update qty_staffed in PO
    for item in items_dicts:
        await db.po.update_one(
            {"_id": ObjectId(staffing.po_id), "items.barang_id": item["barang_id"]},
            {"$inc": {"items.$.qty_staffed": item["qty"]}}
        )
    
    doc["_id"] = str(result.inserted_id)
    return doc

@api_router.get("/staffing")
async def get_staffing(
    tanggal: Optional[str] = None,
    no_po: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pengrajin_id: Optional[str] = None,
    barang_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query: Dict[str, Any] = {}
    if tanggal:
        query["tanggal_keluar"] = tanggal
    elif date_from or date_to:
        query["tanggal_keluar"] = {}
        if date_from: query["tanggal_keluar"]["$gte"] = date_from
        if date_to: query["tanggal_keluar"]["$lte"] = date_to
    if no_po:
        query["no_po"] = {"$regex": no_po, "$options": "i"}
    
    items = await db.staffing.find(query).to_list(1000)
    for item in items:
        item["_id"] = str(item["_id"])
    
    # In-memory filter by barang_id/pengrajin_id (items are nested)
    if barang_id or pengrajin_id:
        filtered = []
        for st in items:
            keep = False
            for it in st.get("items", []):
                if barang_id and it.get("barang_id") != barang_id: continue
                if pengrajin_id and (it.get("pengrajin_id") or "") != pengrajin_id: continue
                keep = True; break
            if keep:
                filtered.append(st)
        items = filtered
    
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
async def _get_po_qty_by_barang(no_po: str, barang_id: str) -> int:
    """Get PO qty for a specific (no_po, barang_id)."""
    po = await db.po.find_one({"no_po": no_po})
    if not po:
        return 0
    for it in po.get("items", []):
        if it.get("barang_id") == barang_id:
            return int(it.get("qty", 0) or 0)
    return 0


async def _get_spk_used_qty(no_po: str, barang_id: str, exclude_spk_id: Optional[str] = None) -> int:
    """Sum qty across all SPK items for (no_po, barang_id), optionally excluding one SPK."""
    total = 0
    async for spk in db.spk.find({"items.no_po": no_po}):
        if exclude_spk_id and str(spk.get("_id")) == exclude_spk_id:
            continue
        for it in spk.get("items", []):
            if it.get("no_po") == no_po and it.get("barang_id") == barang_id:
                total += int(it.get("qty", 0) or 0)
    return total


async def _validate_spk_items(items, exclude_spk_id: Optional[str] = None):
    """Validate: each item has pengrajin_id, and cumulative SPK qty per (no_po, barang_id) ≤ PO qty."""
    # Aggregate qty within this payload per (no_po, barang_id)
    payload_agg: Dict[tuple, int] = {}
    for it in items:
        # Accept legacy allocations by flattening (each allocation becomes an implicit line)
        if not it.pengrajin_id and it.allocations:
            it.pengrajin_id = it.allocations[0].pengrajin_id
            it.pengrajin_nama = it.allocations[0].pengrajin_nama
        if not it.pengrajin_id:
            raise HTTPException(status_code=400, detail=f"Item '{it.nama_barang}' wajib pilih pengrajin")
        # Validate pengrajin exists
        try:
            p = await db.pengrajin.find_one({"_id": ObjectId(it.pengrajin_id)})
        except Exception:
            p = None
        if not p:
            raise HTTPException(status_code=400, detail=f"Pengrajin '{it.pengrajin_nama or it.pengrajin_id}' tidak ditemukan untuk '{it.nama_barang}'")
        # Sync pengrajin_nama from DB (source of truth)
        it.pengrajin_nama = p.get("nama", it.pengrajin_nama or "")
        # Require no_po and barang_id for cross-SPK checks
        if not it.no_po or not it.barang_id:
            continue  # skip cross-check when info missing (manual entry)
        key = (it.no_po, it.barang_id)
        payload_agg[key] = payload_agg.get(key, 0) + int(it.qty)
    
    # Compare cumulative (payload + other SPKs) ≤ PO qty
    for (no_po, barang_id), payload_qty in payload_agg.items():
        po_qty = await _get_po_qty_by_barang(no_po, barang_id)
        if po_qty == 0:
            raise HTTPException(status_code=400, detail=f"PO {no_po} tidak punya barang tersebut, atau qty PO = 0")
        other_used = await _get_spk_used_qty(no_po, barang_id, exclude_spk_id=exclude_spk_id)
        if payload_qty + other_used > po_qty:
            sisa = max(po_qty - other_used, 0)
            raise HTTPException(status_code=400, detail=f"Total alokasi SPK untuk barang di PO {no_po} melebihi qty PO ({po_qty}). Sudah dialokasikan di SPK lain: {other_used}. Sisa alokasi: {sisa}. Diminta: {payload_qty}")


@api_router.post("/spk")
async def create_spk(spk: SPKCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    await _validate_spk_items(spk.items)
    
    doc = spk.model_dump()
    # Backward-compat: ensure allocations mirror single pengrajin for legacy readers
    for it in doc.get("items", []):
        if it.get("pengrajin_id") and not it.get("allocations"):
            it["allocations"] = [{"pengrajin_id": it["pengrajin_id"], "pengrajin_nama": it.get("pengrajin_nama", ""), "qty": it["qty"]}]
        if it.get("pengrajin_nama") and not it.get("nama_pengrajin"):
            it["nama_pengrajin"] = it["pengrajin_nama"]
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
    await _validate_spk_items(spk.items, exclude_spk_id=spk_id)
    doc = spk.model_dump()
    for it in doc.get("items", []):
        if it.get("pengrajin_id") and not it.get("allocations"):
            it["allocations"] = [{"pengrajin_id": it["pengrajin_id"], "pengrajin_nama": it.get("pengrajin_nama", ""), "qty": it["qty"]}]
        if it.get("pengrajin_nama") and not it.get("nama_pengrajin"):
            it["nama_pengrajin"] = it["pengrajin_nama"]
    
    await db.spk.update_one(
        {"_id": ObjectId(spk_id)},
        {"$set": spk.model_dump()}
    )
    
    return {"message": "SPK updated"}

# ===== Progres Barang Routes (Stage-based entries) =====
@api_router.post("/progres")
async def create_progres_entry(entry: ProgresEntry, user: dict = Depends(get_current_user)):
    """Create a NEW progres entry (per date, per stage). Pipeline-limited:
       - grinda: qty ≤ (qty_masuk - grinda_sum)
       - servis: qty ≤ (grinda_sum - servis_sum)
       - finishing: qty ≤ (servis_sum - finishing_sum)
       - packing: qty ≤ (finishing_sum - packing_sum)
    """
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if entry.stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Stage tidak valid. Pilih: {', '.join(VALID_STAGES)}")
    
    po_id = entry.po_id or ""
    is_manual = not po_id
    pengrajin_id = entry.pengrajin_id or ""
    
    # Compute stage sums + qty_masuk for validation
    if not is_manual and pengrajin_id:
        # Per-pengrajin scope: use SPK-alloc pipeline
        qty_masuk = await _get_bm_qty_per_pengrajin(po_id, entry.item_id, pengrajin_id)
        sums = {s: await _get_progres_stage_per_pengrajin(po_id, entry.item_id, pengrajin_id, s) for s in VALID_STAGES}
    elif is_manual:
        # Manual mode: only enforce internal pipeline (no qty_masuk)
        sums = await _get_stage_sums("", entry.item_id) if entry.item_id else {s: 0 for s in VALID_STAGES}
        qty_masuk = 0
    else:
        sums = await _get_stage_sums(po_id, entry.item_id)
        qty_masuk = await _get_qty_masuk(po_id, entry.item_id)
    
    # Determine cap (upstream sisa)
    if entry.stage == "grinda":
        upstream = qty_masuk if not is_manual else float('inf')
        upstream_label = "Barang Masuk"
    else:
        prev = PREV_STAGE[entry.stage]
        upstream = sums[prev]
        upstream_label = prev.capitalize()
    
    already_at_stage = sums[entry.stage]
    sisa_before = (upstream - already_at_stage) if upstream != float('inf') else float('inf')
    
    if not is_manual and entry.qty > sisa_before:
        scope = f" untuk pengrajin '{entry.pengrajin_nama or ''}'" if pengrajin_id else ""
        raise HTTPException(
            status_code=400,
            detail=f"Qty {entry.stage} ({entry.qty}){scope} melebihi sisa dari {upstream_label} ({upstream} - {already_at_stage} = {max(int(sisa_before),0)})"
        )
    
    # Validate finishing stage qty doesn't exceed servis qty
    if entry.stage == "finishing":
        servis_qty = 0
        async for e in db.progres.find({"po_id": po_id, "item_id": entry.item_id, "stage": "servis"}):
            servis_qty += e.get("qty", 0) or 0
        
        if entry.qty > servis_qty:
            raise HTTPException(
                status_code=400,
                detail=f"Finishing qty ({entry.qty}) cannot exceed servis qty ({servis_qty})"
            )
    
    doc = {
        "po_id": po_id,
        "item_id": entry.item_id,
        "stage": entry.stage,
        "qty": entry.qty,
        "tanggal": entry.tanggal or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pengrajin_id": pengrajin_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"],
    }
    for meta_key in (
        "nama_barang", "nama_pengrajin", "pengrajin_nama", "spesifikasi", "gambar_path",
        "catatan_finishing_1", "catatan_finishing_2", "catatan_finishing_3",
        "catatan_finishing_4", "catatan_finishing_5",
    ):
        val = getattr(entry, meta_key, None)
        if val:
            doc[meta_key] = val
    
    result = await db.progres.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    
    # Return with computed sisa_after for UX
    doc["sisa_setelah_input"] = (upstream - already_at_stage - entry.qty) if not is_manual else None
    doc["upstream_label"] = upstream_label
    doc["upstream_qty"] = upstream if not is_manual else None
    return doc


@api_router.get("/progres/entries")
async def get_progres_entries(po_id: Optional[str] = None, item_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Return progres entry history for a PO+barang, sorted by tanggal desc."""
    query: Dict[str, Any] = {}
    if po_id is not None:
        query["po_id"] = po_id
    if item_id is not None:
        query["item_id"] = item_id
    entries = await db.progres.find(query).sort([("tanggal", -1), ("created_at", -1)]).to_list(2000)
    for e in entries:
        e["_id"] = str(e["_id"])
    return entries


@api_router.put("/progres/{entry_id}")
async def update_progres_entry(entry_id: str, entry: ProgresEntry, user: dict = Depends(get_current_user)):
    """Update an existing progres entry (qty/tanggal/stage). Pipeline validation excludes self."""
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if entry.stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Stage tidak valid. Pilih: {', '.join(VALID_STAGES)}")
    
    old = await db.progres.find_one({"_id": ObjectId(entry_id)})
    if not old:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    po_id = entry.po_id or ""
    is_manual = not po_id
    pengrajin_id = entry.pengrajin_id or ""
    
    if not is_manual and pengrajin_id:
        qty_masuk = await _get_bm_qty_per_pengrajin(po_id, entry.item_id, pengrajin_id)
        sums = {s: await _get_progres_stage_per_pengrajin(po_id, entry.item_id, pengrajin_id, s, exclude_entry_id=entry_id) for s in VALID_STAGES}
        # sums already exclude self, so skip the manual subtract below
        old_stage = None  # signal: don't subtract again
    elif is_manual:
        sums = await _get_stage_sums("", entry.item_id) if entry.item_id else {s: 0 for s in VALID_STAGES}
        qty_masuk = 0
        old_stage = old.get("stage")
    else:
        sums = await _get_stage_sums(po_id, entry.item_id)
        qty_masuk = await _get_qty_masuk(po_id, entry.item_id)
        old_stage = old.get("stage")
    
    old_qty = int(old.get("qty", 0) or 0)
    if old_stage and old_stage in sums:
        sums[old_stage] = max(0, sums[old_stage] - old_qty)
    
    # Now validate new entry against updated sums
    if entry.stage == "grinda":
        upstream = qty_masuk if not is_manual else float('inf')
        upstream_label = "Barang Masuk"
    else:
        prev = PREV_STAGE[entry.stage]
        upstream = sums[prev]
        upstream_label = prev.capitalize()
    already_at_stage = sums[entry.stage]
    sisa_before = (upstream - already_at_stage) if upstream != float('inf') else float('inf')
    
    if not is_manual and entry.qty > sisa_before:
        raise HTTPException(
            status_code=400,
            detail=f"Qty {entry.stage} ({entry.qty}) melebihi sisa dari {upstream_label} ({upstream} - {already_at_stage} = {max(int(sisa_before),0)})"
        )
    
    # Validate finishing stage qty doesn't exceed servis qty
    if entry.stage == "finishing":
        servis_qty = 0
        async for e in db.progres.find({"po_id": po_id, "item_id": entry.item_id, "stage": "servis"}):
            servis_qty += e.get("qty", 0) or 0
        
        if entry.qty > servis_qty:
            raise HTTPException(
                status_code=400,
                detail=f"Finishing qty ({entry.qty}) cannot exceed servis qty ({servis_qty})"
            )
    
    update_doc = {
        "po_id": po_id,
        "item_id": entry.item_id,
        "stage": entry.stage,
        "qty": entry.qty,
        "tanggal": entry.tanggal or old.get("tanggal") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pengrajin_id": pengrajin_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user["_id"],
    }
    for meta_key in (
        "nama_barang", "nama_pengrajin", "pengrajin_nama", "spesifikasi", "gambar_path",
        "catatan_finishing_1", "catatan_finishing_2", "catatan_finishing_3",
        "catatan_finishing_4", "catatan_finishing_5",
    ):
        val = getattr(entry, meta_key, None)
        if val:
            update_doc[meta_key] = val
    
    await db.progres.update_one({"_id": ObjectId(entry_id)}, {"$set": update_doc})
    return {"message": "Entry updated", "sisa_setelah_input": (upstream - already_at_stage - entry.qty) if not is_manual else None}


@api_router.delete("/progres/{entry_id}")
async def delete_progres_entry(entry_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    result = await db.progres.delete_one({"_id": ObjectId(entry_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Progres entry not found")
    return {"message": "Progres entry deleted"}


@api_router.get("/progres/by-po")
async def get_progres_by_po(user: dict = Depends(get_current_user)):
    """Return progres aggregated (per stage) grouped by PO+barang, synced with barang_masuk."""
    pos = await db.po.find({}).to_list(1000)
    barang_masuk = await db.barang_masuk.find({}).to_list(1000)
    
    # Aggregate qty_masuk per PO+barang from barang_masuk
    bm_agg: Dict[str, Dict[str, Any]] = {}
    for bm in barang_masuk:
        po_id = bm.get("po_id", "")
        for item in bm.get("items", []):
            bid = item.get("barang_id")
            if not bid:
                continue
            k = f"{po_id}_{bid}"
            if k not in bm_agg:
                bm_agg[k] = {
                    "nama_barang": item.get("nama_barang", ""),
                    "spesifikasi": item.get("spesifikasi", ""),
                    "nama_pengrajin": item.get("nama_pengrajin", ""),
                    "gambar_path": item.get("gambar_path"),
                    "qty_masuk": 0,
                }
            bm_agg[k]["qty_masuk"] += item.get("qty_diterima", 0) or 0
    
    # Aggregate stage sums + last tanggal per PO+barang
    pipeline = [
        {"$match": {"stage": {"$in": VALID_STAGES}}},
        {"$group": {
            "_id": {"po_id": "$po_id", "item_id": "$item_id", "stage": "$stage"},
            "total": {"$sum": "$qty"},
            "last_tanggal": {"$max": "$tanggal"},
        }},
    ]
    stage_agg: Dict[str, Dict[str, Any]] = {}
    async for r in db.progres.aggregate(pipeline):
        _id = r.get("_id", {})
        k = f"{_id.get('po_id','')}_{_id.get('item_id','')}"
        if k not in stage_agg:
            stage_agg[k] = {s: 0 for s in VALID_STAGES}
            stage_agg[k]["tanggal"] = ""
        stage_agg[k][_id["stage"]] = int(r.get("total", 0) or 0)
        # Track latest tanggal across any stage
        lt = r.get("last_tanggal") or ""
        if lt > stage_agg[k]["tanggal"]:
            stage_agg[k]["tanggal"] = lt
    
    # Build response per PO
    result = []
    for po in pos:
        po_id = str(po["_id"])
        po_items = []
        for item in po.get("items", []):
            bid = item.get("barang_id")
            k = f"{po_id}_{bid}"
            bm_data = bm_agg.get(k)
            if not bm_data:
                continue
            st = stage_agg.get(k, {s: 0 for s in VALID_STAGES})
            grinda = st.get("grinda", 0)
            servis = st.get("servis", 0)
            finishing = st.get("finishing", 0)
            packing = st.get("packing", 0)
            qty_masuk = bm_data["qty_masuk"]
            po_items.append({
                "barang_id": bid,
                "nama_barang": bm_data["nama_barang"],
                "spesifikasi": bm_data["spesifikasi"],
                "nama_pengrajin": bm_data["nama_pengrajin"],
                "gambar_path": bm_data["gambar_path"],
                "qty_masuk": qty_masuk,
                "grinda": grinda,
                "servis": servis,
                "finishing": finishing,
                "packing": packing,
                # Sisa (remaining) per stage
                "sisa_grinda": max(qty_masuk - grinda, 0),
                "sisa_servis": max(grinda - servis, 0),
                "sisa_finishing": max(servis - finishing, 0),
                "sisa_packing": max(finishing - packing, 0),
                "tanggal": st.get("tanggal", "") or "",
                "komplit": packing >= qty_masuk and qty_masuk > 0,
            })
        if po_items:
            result.append({"po_id": po_id, "no_po": po["no_po"], "items": po_items})
    
    if user["role"] == "guest":
        for po in result:
            for it in po["items"]:
                it.pop("nama_pengrajin", None)
    
    return result


@api_router.get("/progres")
async def get_progres(user: dict = Depends(get_current_user)):
    """Legacy endpoint: return raw progres entries."""
    items = await db.progres.find({}).to_list(2000)
    for item in items:
        item["_id"] = str(item["_id"])
    return items


@api_router.get("/export/progres/pdf")
async def export_progres_pdf(tanggal: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Export progres to PDF. Aggregates stage entries per PO+barang. If tanggal given,
       only include groups whose entries include that tanggal AND filter stage sums to that date only."""
    # Aggregate qty_masuk per PO+barang from barang_masuk
    bm_records = await db.barang_masuk.find({}).to_list(1000)
    bm_agg: Dict[str, Dict[str, Any]] = {}
    for bm in bm_records:
        po_id = bm.get("po_id", "")
        for item in bm.get("items", []):
            bid = item.get("barang_id")
            if not bid: continue
            k = f"{po_id}_{bid}"
            if k not in bm_agg:
                bm_agg[k] = {
                    "no_po": bm.get("no_po", ""),
                    "nama_barang": item.get("nama_barang", ""),
                    "nama_pengrajin": item.get("nama_pengrajin", ""),
                    "gambar_path": item.get("gambar_path"),
                    "qty_masuk": 0,
                }
            bm_agg[k]["qty_masuk"] += item.get("qty_diterima", 0) or 0

    # Aggregate stage sums per PO+barang. If tanggal filter, sum only entries on that date.
    match: Dict[str, Any] = {"stage": {"$in": VALID_STAGES}}
    if tanggal:
        match["tanggal"] = tanggal
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"po_id": "$po_id", "item_id": "$item_id", "stage": "$stage"},
            "total": {"$sum": "$qty"},
            "last_tanggal": {"$max": "$tanggal"},
        }},
    ]
    stage_agg: Dict[str, Dict[str, Any]] = {}
    async for r in db.progres.aggregate(pipeline):
        _id = r.get("_id", {})
        k = f"{_id.get('po_id','')}_{_id.get('item_id','')}"
        if k not in stage_agg:
            stage_agg[k] = {s: 0 for s in VALID_STAGES}
            stage_agg[k]["tanggal"] = ""
        stage_agg[k][_id["stage"]] = int(r.get("total", 0) or 0)
        lt = r.get("last_tanggal") or ""
        if lt > stage_agg[k]["tanggal"]:
            stage_agg[k]["tanggal"] = lt

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm)
    story = []
    styles = getSampleStyleSheet()
    subtitle = f"Filter Tanggal: {tanggal}" if tanggal else "Semua Progres"
    _brand_header(story, "REKAP PROGRES BARANG", subtitle, styles)
    body_style = ParagraphStyle('body', parent=styles["BodyText"], fontSize=9, leading=11)
    data = [["Foto", "No PO", "Nama Barang", "Pengrajin", "Tanggal", "Masuk", "Grinda", "Servis", "Finishing", "Packing", "Status"]]
    # If tanggal filter provided, only show groups that have entries on that date
    keys = [k for k in bm_agg.keys() if (not tanggal) or (k in stage_agg and any(stage_agg[k].get(s, 0) > 0 for s in VALID_STAGES))]
    for k in keys:
        info = bm_agg[k]
        st = stage_agg.get(k, {s: 0 for s in VALID_STAGES})
        img = _fetch_image_flowable(info.get("gambar_path"), 18) or Paragraph("-", body_style)
        packing = st.get("packing", 0)
        qty_masuk = info.get("qty_masuk", 0)
        status = "KOMPLIT" if packing >= qty_masuk and qty_masuk > 0 else "PROSES"
        data.append([
            img,
            info.get("no_po", ""),
            Paragraph(info.get("nama_barang", ""), body_style),
            Paragraph(info.get("nama_pengrajin", ""), body_style),
            st.get("tanggal", "") or "-",
            str(qty_masuk),
            str(st.get("grinda", 0)),
            str(st.get("servis", 0)),
            str(st.get("finishing", 0)),
            str(packing),
            status,
        ])
    table = Table(data, repeatRows=1, colWidths=[15*mm, 20*mm, 30*mm, 22*mm, 20*mm, 12*mm, 13*mm, 12*mm, 14*mm, 13*mm, 15*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E5E5E5")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8B5A2B")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (4,1), (-1,-1), "CENTER"),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    filename = f"progres-{tanggal or 'all'}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})

# ===== Rekap Data Routes =====
@api_router.get("/rekap/all-po")
async def get_rekap_all_po(
    no_po: Optional[str] = None,
    barang_id: Optional[str] = None,
    pengrajin_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query: Dict[str, Any] = {}
    if no_po: query["no_po"] = {"$regex": no_po, "$options": "i"}
    if date_from or date_to:
        query["tanggal_terima"] = {}
        if date_from: query["tanggal_terima"]["$gte"] = date_from
        if date_to: query["tanggal_terima"]["$lte"] = date_to
    pos = await db.po.find(query).to_list(1000)
    staffing = await db.staffing.find({}).to_list(1000)
    spks = await db.spk.find({}).to_list(1000)
    barang_masuk = await db.barang_masuk.find({}).to_list(1000)
    progres = await db.progres.find({}).to_list(1000)
    for p in pos: p["_id"] = str(p["_id"])
    for s in staffing: s["_id"] = str(s["_id"])
    
    # Calculate per-PO status flags
    def po_status(po):
        po_id = po["_id"]
        no_po_val = po["no_po"]
        items = po.get("items", [])
        if not items:
            return {"komplit_spk": False, "komplit_terkirim": False, "komplit_pengrajin": False, "ready": False}
        # Komplit SPK: all barang_id in PO have an SPK entry with matching no_po
        spk_barang_ids = set()
        for spk in spks:
            for si in spk.get("items", []):
                if si.get("no_po") == no_po_val:
                    spk_barang_ids.add(si.get("barang_id"))
        komplit_spk = all(item.get("barang_id") in spk_barang_ids for item in items)
        # Komplit Terkirim: all items qty_staffed >= qty
        komplit_terkirim = all((item.get("qty_staffed", 0) or 0) >= item.get("qty", 0) for item in items)
        # Komplit Pengrajin: all items qty_diterima >= qty
        komplit_pengrajin = all((item.get("qty_diterima", 0) or 0) >= item.get("qty", 0) for item in items)
        # Ready: for each item in PO, packing (from progres) >= qty_po. Requires qty_diterima to be complete too.
        prog_map = {f"{po_id}_{p.get('item_id')}": p for p in progres if p.get("po_id") == po_id}
        ready = True
        for item in items:
            bid = item.get("barang_id")
            pr = prog_map.get(f"{po_id}_{bid}")
            packing = (pr.get("packing", 0) if pr else 0)
            if packing < item.get("qty", 0):
                ready = False
                break
        return {"komplit_spk": komplit_spk, "komplit_terkirim": komplit_terkirim, "komplit_pengrajin": komplit_pengrajin, "ready": ready}
    
    result = []
    for po in pos:
        status = po_status(po)
        for item in po.get("items", []):
            if barang_id and item.get("barang_id") != barang_id:
                continue
            # If filter by pengrajin: only include when SPK/BM has this pengrajin_id for this barang
            if pengrajin_id:
                found = False
                for spk in spks:
                    for si in spk.get("items", []):
                        if si.get("no_po") == po["no_po"] and si.get("barang_id") == item.get("barang_id"):
                            if si.get("pengrajin_id") == pengrajin_id:
                                found = True
                                break
                            for a in si.get("allocations", []) or []:
                                if a.get("pengrajin_id") == pengrajin_id:
                                    found = True; break
                    if found: break
                if not found:
                    continue
            staffing_qty = item.get("qty_staffed", 0) or 0
            kurang_kirim = item["qty"] - staffing_qty
            result.append({
                "no_po": po["no_po"],
                "nama_barang": item["nama_barang"],
                "spesifikasi": item.get("spesifikasi", ""),
                "nama_pengrajin": item.get("nama_pengrajin", ""),
                "qty_po": item["qty"],
                "qty_staffing": staffing_qty,
                "kurang_kirim": kurang_kirim,
                "gambar_path": item.get("gambar_path"),
                **status,
            })
    
    if user["role"] == "guest":
        for r in result:
            r.pop("nama_pengrajin", None)
    
    return result

@api_router.get("/rekap/per-pengrajin")
async def get_rekap_per_pengrajin(
    pengrajin_id: Optional[str] = None,
    no_po: Optional[str] = None,
    barang_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if user["role"] == "guest":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    spks = await db.spk.find({}).to_list(1000)
    barang_masuk = await db.barang_masuk.find({}).to_list(1000)
    for s in spks: s["_id"] = str(s["_id"])
    for b in barang_masuk: b["_id"] = str(b["_id"])
    
    # Build result keyed by pengrajin nama (grouping)
    # Also collect no_po_set and barang_set per pengrajin
    result: Dict[str, Dict[str, Any]] = {}
    
    def _match_filters(no_po_val, bid, pid, pnama):
        if no_po and no_po_val and no_po not in no_po_val: return False
        if barang_id and bid != barang_id: return False
        if pengrajin_id and pid != pengrajin_id: return False
        return True
    
    def _ensure(key, pid):
        result.setdefault(key, {
            "pengrajin_id": pid, "spk_qty": 0, "masuk_qty": 0,
            "_no_po_set": set(), "_barang_set": set(),
        })
    
    for spk in spks:
        for item in spk.get("items", []):
            pid = item.get("pengrajin_id") or ""
            pnama = item.get("pengrajin_nama") or item.get("nama_pengrajin") or "Unknown"
            bang = item.get("nama_barang") or ""
            npo = item.get("no_po") or ""
            if pid or pnama != "Unknown":
                if not _match_filters(item.get("no_po"), item.get("barang_id"), pid, pnama): continue
                _ensure(pnama, pid)
                result[pnama]["spk_qty"] += int(item.get("qty", 0) or 0)
                if npo: result[pnama]["_no_po_set"].add(npo)
                if bang: result[pnama]["_barang_set"].add(bang)
            for a in item.get("allocations", []) or []:
                apid = a.get("pengrajin_id") or ""
                anama = a.get("pengrajin_nama") or "Unknown"
                if not _match_filters(item.get("no_po"), item.get("barang_id"), apid, anama): continue
                if apid == pid: continue
                _ensure(anama, apid)
                result[anama]["spk_qty"] += int(a.get("qty", 0) or 0)
                if npo: result[anama]["_no_po_set"].add(npo)
                if bang: result[anama]["_barang_set"].add(bang)
    
    for bm in barang_masuk:
        if date_from and (bm.get("tanggal_masuk") or "") < date_from: continue
        if date_to and (bm.get("tanggal_masuk") or "") > date_to: continue
        for item in bm.get("items", []):
            pid = item.get("pengrajin_id") or ""
            pnama = item.get("pengrajin_nama") or item.get("nama_pengrajin") or "Unknown"
            if not _match_filters(bm.get("no_po"), item.get("barang_id"), pid, pnama): continue
            key = pnama
            if key in result:
                result[key]["masuk_qty"] += int(item.get("qty_diterima", 0) or 0)
    
    out = []
    for k, v in result.items():
        no_po_list = sorted(v.pop("_no_po_set"))
        barang_list = sorted(v.pop("_barang_set"))
        out.append({
            "pengrajin": k,
            "pengrajin_id": v["pengrajin_id"],
            "spk_qty": v["spk_qty"],
            "masuk_qty": v["masuk_qty"],
            "remaining": v["spk_qty"] - v["masuk_qty"],
            "no_po_list": no_po_list,
            "no_po": ", ".join(no_po_list),
            "barang_list": barang_list,
            "barang_dikerjakan": ", ".join(barang_list),
        })
    # Sort pengrajin A-Z
    out.sort(key=lambda x: (x.get("pengrajin") or "").lower())
    return out

# ===== Export Routes =====
def _fetch_image_flowable(gambar_path: Optional[str], max_width_mm: float = 30) -> Optional[RLImage]:
    """Fetch image from storage and return ReportLab Image flowable, or None."""
    if not gambar_path:
        return None
    try:
        data, _ = get_object(gambar_path)
        pil = PILImage.open(BytesIO(data))
        ratio = pil.height / pil.width if pil.width else 1
        img = RLImage(BytesIO(data), width=max_width_mm*mm, height=max_width_mm*ratio*mm)
        return img
    except Exception as e:
        logger.warning(f"Could not fetch image {gambar_path}: {e}")
        return None


def _brand_header(story, title: str, subtitle: str, styles):
    header_style = ParagraphStyle('brand', parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#8B5A2B"), spaceAfter=4, alignment=0)
    story.append(Paragraph("AGFDATA", header_style))
    story.append(Paragraph("<font color='#5C5C5C' size='9'>Furniture Data Management System</font>", styles["Normal"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>{title}</b>", ParagraphStyle('h1', parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#1A1A1A"))))
    if subtitle:
        story.append(Paragraph(f"<font color='#5C5C5C'>{subtitle}</font>", styles["Normal"]))
    story.append(Spacer(1, 8))


@api_router.get("/export/po/{po_id}/pdf")
async def export_po_pdf(po_id: str, user: dict = Depends(get_current_user)):
    po = await db.po.find_one({"_id": ObjectId(po_id)})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    story = []
    styles = getSampleStyleSheet()

    _brand_header(story, "PURCHASE ORDER", f"No PO: {po['no_po']}  •  Tanggal: {po.get('created_at', '')[:10]}", styles)

    body_style = ParagraphStyle('body', parent=styles["BodyText"], fontSize=9, leading=11)
    header = ["Foto", "Nama Barang", "Spesifikasi", "Pengrajin", "Qty", "Harga Jual", "Subtotal"]
    data = [header]
    grand_total = 0
    for item in po.get("items", []):
        img = _fetch_image_flowable(item.get("gambar_path"), 20) or Paragraph("-", body_style)
        qty = item.get("qty", 0) or 0
        harga = item.get("harga_jual", 0) or 0
        subtotal = qty * harga
        grand_total += subtotal
        data.append([
            img,
            Paragraph(item.get("nama_barang", ""), body_style),
            Paragraph(item.get("spesifikasi", ""), body_style),
            Paragraph(item.get("nama_pengrajin", ""), body_style),
            str(qty),
            f"Rp {harga:,.0f}".replace(",", "."),
            f"Rp {subtotal:,.0f}".replace(",", "."),
        ])
    # Grand total row
    data.append(["", "", "", "", "", Paragraph("<b>Grand Total</b>", body_style), Paragraph(f"<b>Rp {grand_total:,.0f}</b>".replace(",", "."), body_style)])

    table = Table(data, repeatRows=1, colWidths=[22*mm, 38*mm, 42*mm, 26*mm, 12*mm, 25*mm, 27*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-2), 0.5, colors.HexColor("#E5E5E5")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8B5A2B")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-2), [colors.white, colors.HexColor("#FAFAFA")]),
        ("ALIGN", (4,1), (4,-1), "CENTER"),
        ("ALIGN", (5,1), (6,-1), "RIGHT"),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#F0E6D6")),
        ("SPAN", (0,-1), (4,-1)),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))
    if po.get("catatan"):
        story.append(Paragraph(f"<b>Catatan:</b> {po['catatan']}", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=PO-{po['no_po']}.pdf"
    })


@api_router.get("/export/spk/{spk_id}/pdf")
async def export_spk_pdf(spk_id: str, user: dict = Depends(get_current_user)):
    spk = await db.spk.find_one({"_id": ObjectId(spk_id)})
    if not spk:
        raise HTTPException(status_code=404, detail="SPK not found")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    story = []
    styles = getSampleStyleSheet()

    _brand_header(story, "SURAT PERINTAH KERJA (SPK)", f"No SPK: {spk['no_spk']}  •  Deadline: {spk.get('deadline', '')}", styles)

    body_style = ParagraphStyle('body', parent=styles["BodyText"], fontSize=9, leading=11)
    header = ["Foto", "Nama Barang", "Spesifikasi", "No PO", "Pengrajin", "Qty", "Harga"]
    data = [header]
    total = 0
    for item in spk.get("items", []):
        img = _fetch_image_flowable(item.get("gambar_path"), 20) or Paragraph("-", body_style)
        harga = item.get("harga", 0) or 0
        qty = item.get("qty", 0) or 0
        total += harga * qty
        data.append([
            img,
            Paragraph(item.get("nama_barang", ""), body_style),
            Paragraph(item.get("spesifikasi", ""), body_style),
            item.get("no_po", ""),
            Paragraph(item.get("nama_pengrajin", ""), body_style),
            str(qty),
            f"Rp {harga:,.0f}"
        ])

    table = Table(data, repeatRows=1, colWidths=[22*mm, 36*mm, 40*mm, 22*mm, 28*mm, 12*mm, 26*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E5E5E5")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8B5A2B")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAFAFA")]),
        ("ALIGN", (5,1), (6,-1), "RIGHT"),
    ]))
    story.append(table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Total: Rp {total:,.0f}</b>", styles["Normal"]))
    story.append(Spacer(1, 12))
    if spk.get("catatan_pembayaran"):
        story.append(Paragraph(f"<b>Catatan Pembayaran:</b><br/>{spk['catatan_pembayaran']}", styles["Normal"]))
    story.append(Spacer(1, 30))

    # Signature area
    pengrajin_names = ", ".join(set([i.get("nama_pengrajin", "") for i in spk.get("items", []) if i.get("nama_pengrajin")]))
    sig_data = [
        [Paragraph("<b>Owner Perusahaan</b>", styles["Normal"]), Paragraph("<b>Pengrajin</b>", styles["Normal"])],
        ["", ""],
        ["", ""],
        [Paragraph(f"({spk.get('owner_perusahaan', '')})", styles["Normal"]), Paragraph(f"({pengrajin_names})", styles["Normal"])],
    ]
    sig_table = Table(sig_data, colWidths=[90*mm, 90*mm])
    sig_table.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LINEBELOW", (0,2), (0,2), 0.5, colors.black),
        ("LINEBELOW", (1,2), (1,2), 0.5, colors.black),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=SPK-{spk['no_spk']}.pdf"
    })


@api_router.get("/export/barang-masuk/{bm_id}/pdf")
async def export_bm_pdf(bm_id: str, user: dict = Depends(get_current_user)):
    bm = await db.barang_masuk.find_one({"_id": ObjectId(bm_id)})
    if not bm:
        raise HTTPException(status_code=404, detail="Not found")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm)
    story = []
    styles = getSampleStyleSheet()
    _brand_header(story, "BARANG MASUK", f"No PO: {bm['no_po']}  •  Tanggal: {bm['tanggal_masuk']}  •  Penerima: {bm['penerima']}", styles)
    body_style = ParagraphStyle('body', parent=styles["BodyText"], fontSize=9, leading=11)
    data = [["Foto", "Nama Barang", "Spesifikasi", "Pengrajin", "Qty Diterima"]]
    for item in bm.get("items", []):
        img = _fetch_image_flowable(item.get("gambar_path"), 20) or Paragraph("-", body_style)
        data.append([img, Paragraph(item.get("nama_barang", ""), body_style), Paragraph(item.get("spesifikasi", ""), body_style), Paragraph(item.get("nama_pengrajin", ""), body_style), str(item.get("qty_diterima", 0))])
    table = Table(data, repeatRows=1, colWidths=[22*mm, 45*mm, 55*mm, 35*mm, 25*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E5E5E5")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8B5A2B")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=BM-{bm['no_po']}.pdf"})


@api_router.get("/export/staffing/{st_id}/pdf")
async def export_staffing_pdf(st_id: str, user: dict = Depends(get_current_user)):
    st = await db.staffing.find_one({"_id": ObjectId(st_id)})
    if not st:
        raise HTTPException(status_code=404, detail="Not found")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm)
    story = []
    styles = getSampleStyleSheet()
    _brand_header(story, "STAFFING (BARANG KELUAR)", f"No PO: {st['no_po']}  •  Tanggal Keluar: {st['tanggal_keluar']}", styles)
    body_style = ParagraphStyle('body', parent=styles["BodyText"], fontSize=9, leading=11)
    data = [["Foto", "Nama Barang", "Spesifikasi", "Pengrajin", "Qty Keluar"]]
    for item in st.get("items", []):
        img = _fetch_image_flowable(item.get("gambar_path"), 20) or Paragraph("-", body_style)
        data.append([img, Paragraph(item.get("nama_barang", ""), body_style), Paragraph(item.get("spesifikasi", ""), body_style), Paragraph(item.get("nama_pengrajin", ""), body_style), str(item.get("qty", 0))])
    table = Table(data, repeatRows=1, colWidths=[22*mm, 45*mm, 55*mm, 35*mm, 25*mm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E5E5E5")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8B5A2B")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Staffing-{st['no_po']}.pdf"})


# ===== Edit / Delete Endpoints =====
@api_router.put("/barang/{barang_id}")
async def update_barang(barang_id: str, barang: BarangCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.barang.update_one({"_id": ObjectId(barang_id)}, {"$set": barang.model_dump()})
    return {"message": "Barang updated"}


@api_router.delete("/barang/{barang_id}")
async def delete_barang(barang_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    result = await db.barang.delete_one({"_id": ObjectId(barang_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Barang not found")
    return {"message": "Barang deleted"}


@api_router.delete("/po/{po_id}")
async def delete_po(po_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    result = await db.po.delete_one({"_id": ObjectId(po_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="PO not found")
    return {"message": "PO deleted"}


@api_router.put("/barang-masuk/{bm_id}")
async def update_bm(bm_id: str, bm: BarangMasukCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    old = await db.barang_masuk.find_one({"_id": ObjectId(bm_id)})
    po = await db.po.find_one({"_id": ObjectId(bm.po_id)})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    # Validate first (exclude own contribution) before mutating PO.
    own_old_by_bp = {}  # (barang_id, pengrajin_id) → qty
    own_old = {}
    if old and old.get("po_id") == bm.po_id:
        for item in old.get("items", []):
            own_old[item.get("barang_id")] = own_old.get(item.get("barang_id"), 0) + (item.get("qty_diterima", 0) or 0)
            key = (item.get("barang_id"), item.get("pengrajin_id") or "")
            own_old_by_bp[key] = own_old_by_bp.get(key, 0) + (item.get("qty_diterima", 0) or 0)
    
    po_items_map = {it.get("barang_id"): it for it in po.get("items", [])}
    items_dicts = []
    for it in bm.items:
        po_item = po_items_map.get(it.barang_id)
        if not po_item:
            raise HTTPException(status_code=400, detail=f"Barang {it.barang_id} tidak ada di PO ini")
        if it.pengrajin_id:
            alloc = await _get_spk_allocation(bm.po_id, it.barang_id, it.pengrajin_id)
            if alloc <= 0:
                raise HTTPException(status_code=400, detail=f"Belum ada alokasi SPK untuk pengrajin ini pada '{po_item.get('nama_barang','')}'. Buat SPK dulu.")
            already_all = await _get_bm_qty_per_pengrajin(bm.po_id, it.barang_id, it.pengrajin_id, exclude_bm_id=bm_id)
            sisa = alloc - already_all
            if it.qty_diterima > sisa:
                raise HTTPException(status_code=400, detail=f"Qty diterima ({it.qty_diterima}) untuk '{po_item.get('nama_barang','')}' pengrajin melebihi sisa alokasi (alokasi: {alloc}, sudah diterima: {already_all}, sisa: {max(sisa,0)})")
        else:
            current_others = (po_item.get("qty_diterima", 0) or 0) - own_old.get(it.barang_id, 0)
            sisa = (po_item.get("qty", 0) or 0) - current_others
            if it.qty_diterima > sisa:
                raise HTTPException(status_code=400, detail=f"Qty diterima untuk {po_item.get('nama_barang','')} melebihi sisa PO (sisa: {sisa}, diminta: {it.qty_diterima})")
        items_dicts.append({
            **it.model_dump(exclude_none=True),
            "nama_barang": po_item.get("nama_barang", ""),
            "nama_pengrajin": it.pengrajin_nama or po_item.get("nama_pengrajin", ""),
            "spesifikasi": po_item.get("spesifikasi", ""),
            "gambar_path": po_item.get("gambar_path"),
        })
    
    # Validation passed - safe to mutate: revert old, then apply new
    if old:
        for item in old.get("items", []):
            await db.po.update_one({"_id": ObjectId(old["po_id"]), "items.barang_id": item["barang_id"]}, {"$inc": {"items.$.qty_diterima": -(item.get("qty_diterima", 0) or 0)}})
    doc = {"po_id": bm.po_id, "no_po": po["no_po"], "tanggal_masuk": bm.tanggal_masuk, "penerima": bm.penerima, "items": items_dicts}
    await db.barang_masuk.update_one({"_id": ObjectId(bm_id)}, {"$set": doc})
    for item in items_dicts:
        await db.po.update_one({"_id": ObjectId(bm.po_id), "items.barang_id": item["barang_id"]}, {"$inc": {"items.$.qty_diterima": item["qty_diterima"]}})
    return {"message": "Barang masuk updated"}


@api_router.delete("/barang-masuk/{bm_id}")
async def delete_bm(bm_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    old = await db.barang_masuk.find_one({"_id": ObjectId(bm_id)})
    if not old:
        raise HTTPException(status_code=404, detail="Barang masuk not found")
    for item in old.get("items", []):
        try:
            await db.po.update_one({"_id": ObjectId(old["po_id"]), "items.barang_id": item["barang_id"]}, {"$inc": {"items.$.qty_diterima": -item.get("qty_diterima", 0)}})
        except Exception:
            pass
    await db.barang_masuk.delete_one({"_id": ObjectId(bm_id)})
    return {"message": "Barang masuk deleted"}


@api_router.put("/staffing/{st_id}")
async def update_staffing(st_id: str, staffing: StaffingCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    old = await db.staffing.find_one({"_id": ObjectId(st_id)})
    po = await db.po.find_one({"_id": ObjectId(staffing.po_id)})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    
    # Validate first (subtract own old contribution) before mutating PO; also cap by qty_ready
    own_old = {}
    if old and old.get("po_id") == staffing.po_id:
        for item in old.get("items", []):
            own_old[item.get("barang_id")] = own_old.get(item.get("barang_id"), 0) + (item.get("qty", 0) or 0)
    
    po_items_map = {it.get("barang_id"): it for it in po.get("items", [])}
    packing_map = await _get_packing_map(staffing.po_id)
    items_dicts = []
    for it in staffing.items:
        po_item = po_items_map.get(it.barang_id)
        if not po_item:
            raise HTTPException(status_code=400, detail=f"Barang {it.barang_id} tidak ada di PO ini")
        current_others_staffed = (po_item.get("qty_staffed", 0) or 0) - own_old.get(it.barang_id, 0)
        qty_ready = packing_map.get(f"{staffing.po_id}_{it.barang_id}", 0)
        sisa_po = (po_item.get("qty", 0) or 0) - current_others_staffed
        sisa_ready = qty_ready - current_others_staffed
        sisa = min(sisa_po, sisa_ready)
        if it.qty > sisa:
            raise HTTPException(
                status_code=400,
                detail=f"Qty staffing untuk {po_item.get('nama_barang','')} melebihi sisa yang siap (Ready: {qty_ready}, sisa: {max(sisa,0)}, diminta: {it.qty})"
            )
        items_dicts.append({
            **it.model_dump(exclude_none=True),
            "nama_barang": po_item.get("nama_barang", ""),
            "nama_pengrajin": po_item.get("nama_pengrajin", ""),
            "spesifikasi": po_item.get("spesifikasi", ""),
            "gambar_path": po_item.get("gambar_path"),
        })
    
    # Validation passed - safe to mutate: revert old, then apply new
    if old:
        for item in old.get("items", []):
            try:
                await db.po.update_one(
                    {"_id": ObjectId(old["po_id"]), "items.barang_id": item["barang_id"]},
                    {"$inc": {"items.$.qty_staffed": -(item.get("qty", 0) or 0)}}
                )
            except Exception:
                pass
    doc = {"po_id": staffing.po_id, "no_po": po["no_po"], "tanggal_keluar": staffing.tanggal_keluar, "items": items_dicts}
    await db.staffing.update_one({"_id": ObjectId(st_id)}, {"$set": doc})
    for item in items_dicts:
        await db.po.update_one(
            {"_id": ObjectId(staffing.po_id), "items.barang_id": item["barang_id"]},
            {"$inc": {"items.$.qty_staffed": item["qty"]}}
        )
    return {"message": "Staffing updated"}


@api_router.delete("/staffing/{st_id}")
async def delete_staffing(st_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    old = await db.staffing.find_one({"_id": ObjectId(st_id)})
    if not old:
        raise HTTPException(status_code=404, detail="Staffing not found")
    # Revert qty_staffed
    for item in old.get("items", []):
        try:
            await db.po.update_one(
                {"_id": ObjectId(old["po_id"]), "items.barang_id": item["barang_id"]},
                {"$inc": {"items.$.qty_staffed": -item.get("qty", 0)}}
            )
        except Exception:
            pass
    await db.staffing.delete_one({"_id": ObjectId(st_id)})
    return {"message": "Staffing deleted"}


@api_router.delete("/spk/{spk_id}")
async def delete_spk(spk_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    result = await db.spk.delete_one({"_id": ObjectId(spk_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="SPK not found")
    return {"message": "SPK deleted"}


# ===== User Management Endpoints =====
class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str  # admin/staff/guest


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None

@api_router.get("/dashboard/kinerja-pengrajin")
async def get_kinerja_pengrajin(month: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Ranking pengrajin per bulan. month=YYYY-MM (default=current)."""
    if user["role"] == "guest":
        raise HTTPException(status_code=403, detail="Not authorized")
    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    pengrajin_docs = await db.pengrajin.find({}).to_list(1000)
    pengrajin_map = {str(p["_id"]): p.get("nama", "") for p in pengrajin_docs}
    stats: Dict[str, Dict[str, Any]] = {}
    def ensure(pid, nama):
        if not pid: return None
        stats.setdefault(pid, {"pengrajin_id": pid, "pengrajin_nama": nama or pengrajin_map.get(pid, ""), "qty_selesai": 0, "qty_masuk": 0, "spk_qty_month": 0, "on_time_count": 0, "total_spk_month": 0})
        return stats[pid]
    async for e in db.progres.find({"stage": "packing", "tanggal": {"$regex": f"^{month}"}}):
        pid = e.get("pengrajin_id") or ""
        s = ensure(pid, "")
        if s: s["qty_selesai"] += int(e.get("qty", 0) or 0)
    async for bm in db.barang_masuk.find({"tanggal_masuk": {"$regex": f"^{month}"}}):
        for it in bm.get("items", []):
            pid = it.get("pengrajin_id") or ""
            s = ensure(pid, it.get("pengrajin_nama") or it.get("nama_pengrajin") or "")
            if s: s["qty_masuk"] += int(it.get("qty_diterima", 0) or 0)
    async for spk in db.spk.find({"deadline": {"$regex": f"^{month}"}}):
        deadline = spk.get("deadline", "")
        for it in spk.get("items", []):
            pid = it.get("pengrajin_id") or ""
            spk_qty = int(it.get("qty", 0) or 0)
            if not pid or spk_qty == 0: continue
            s = ensure(pid, it.get("pengrajin_nama") or "")
            if not s: continue
            s["spk_qty_month"] += spk_qty
            s["total_spk_month"] += 1
            po_id = ""
            if it.get("no_po"):
                po = await db.po.find_one({"no_po": it.get("no_po")})
                if po: po_id = str(po["_id"])
            match = {"stage": "packing", "pengrajin_id": pid, "item_id": it.get("barang_id"), "tanggal": {"$lte": deadline}}
            if po_id: match["po_id"] = po_id
            done = 0
            async for pk in db.progres.find(match):
                done += int(pk.get("qty", 0) or 0)
            if done >= spk_qty:
                s["on_time_count"] += 1
    result = []
    for s in stats.values():
        rate = (s["on_time_count"] / s["total_spk_month"] * 100) if s["total_spk_month"] > 0 else None
        s["on_time_rate"] = round(rate, 1) if rate is not None else None
        result.append(s)
    result.sort(key=lambda x: (-x["qty_selesai"], -(x["on_time_rate"] or 0)))
    total = len(result)
    for idx, s in enumerate(result):
        s["rank"] = idx + 1
        if s["qty_selesai"] == 0 and (s["on_time_rate"] or 0) == 0:
            s["badge"] = "Belum ada aktivitas"
        elif idx < 3:
            s["badge"] = "MVP"
        elif idx < max(3, total // 2):
            s["badge"] = "Produktif"
        else:
            s["badge"] = "Perlu Improvement"
    return {"month": month, "pengrajin": result}


@api_router.get("/dashboard/po-ready")
async def get_po_ready(user: dict = Depends(get_current_user)):
    """Return list of POs where ALL items have reached packing stage (qty_ready >= qty).
    Excludes POs marked as already shipped (marked_shipped=True).
    Available for all authenticated roles. Prices hidden for staff/guest; pengrajin hidden for guest.
    """
    packing_map = await _get_packing_map()
    pos = await db.po.find({}).to_list(1000)
    result: List[Dict[str, Any]] = []
    for po in pos:
        po["_id"] = str(po["_id"])
        # Skip PO that was explicitly marked as shipped/done by admin
        if po.get("marked_shipped"):
            continue
        items = po.get("items", []) or []
        if not items:
            continue
        total_qty = 0
        total_ready = 0
        all_ready = True
        enriched_items: List[Dict[str, Any]] = []
        for item in items:
            qty = int(item.get("qty", 0) or 0)
            k = f"{po['_id']}_{item.get('barang_id','')}"
            qty_ready = int(packing_map.get(k, 0) or 0)
            total_qty += qty
            total_ready += min(qty_ready, qty)
            if qty_ready < qty:
                all_ready = False
                break  # short-circuit; PO not ready
            enriched_items.append({
                "barang_id": item.get("barang_id"),
                "nama_barang": item.get("nama_barang"),
                "qty": qty,
                "qty_ready": qty_ready,
            })
        if not all_ready:
            continue
        result.append({
            "po_id": po["_id"],
            "no_po": po.get("no_po", ""),
            "total_items": len(items),
            "total_qty": total_qty,
            "total_ready": total_ready,
            "created_at": po.get("created_at"),
            "items": enriched_items,
        })
    # Sort by created_at desc (newest first)
    result.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    # For guest — do not expose items list (guest doesn't see pengrajin, but items here don't contain pengrajin so OK). Guest still allowed.
    return {"count": len(result), "pos": result}


@api_router.post("/dashboard/po-ready/{po_id}/mark-shipped")
async def mark_po_shipped(po_id: str, user: dict = Depends(get_current_user)):
    """Admin action: mark a PO as shipped so it disappears from the Ready-to-Ship notification.
    Idempotent — safe to call multiple times."""
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        oid = ObjectId(po_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid po_id")
    po = await db.po.find_one({"_id": oid})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    await db.po.update_one(
        {"_id": oid},
        {"$set": {
            "marked_shipped": True,
            "marked_shipped_at": datetime.now(timezone.utc).isoformat(),
            "marked_shipped_by": user["_id"],
        }}
    )
    return {"ok": True, "po_id": po_id, "no_po": po.get("no_po", "")}


@api_router.post("/dashboard/po-ready/{po_id}/unmark-shipped")
async def unmark_po_shipped(po_id: str, user: dict = Depends(get_current_user)):
    """Admin action: revert a mark-shipped. Puts PO back into Ready-to-Ship list if still qualifies."""
    if user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        oid = ObjectId(po_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid po_id")
    po = await db.po.find_one({"_id": oid})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    await db.po.update_one(
        {"_id": oid},
        {"$unset": {"marked_shipped": "", "marked_shipped_at": "", "marked_shipped_by": ""}}
    )
    return {"ok": True, "po_id": po_id, "no_po": po.get("no_po", "")}




@api_router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    users = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    for u in users:
        u["_id"] = str(u["_id"])
    return users


@api_router.post("/users")
async def create_user(new_user: UserCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if new_user.role not in ["admin", "staff", "guest", "owner"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = await db.users.find_one({"email": new_user.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    doc = {
        "email": new_user.email.lower(),
        "password_hash": hash_password(new_user.password),
        "name": new_user.name,
        "role": new_user.role,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.users.insert_one(doc)
    return {"_id": str(result.inserted_id), "email": doc["email"], "name": doc["name"], "role": doc["role"]}


@api_router.put("/users/{user_id}")
async def update_user(user_id: str, upd: UserUpdate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    updates = {}
    if upd.email: updates["email"] = upd.email.lower()
    if upd.name: updates["name"] = upd.name
    if upd.role:
        if upd.role not in ["admin", "staff", "guest", "owner"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        updates["role"] = upd.role
    if upd.password:
        updates["password_hash"] = hash_password(upd.password)
    if updates:
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": updates})
    return {"message": "User updated"}


@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if user_id == user["_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


# ===== Pengrajin CRUD =====
@api_router.get("/pengrajin")
async def list_pengrajin(user: dict = Depends(get_current_user)):
    docs = await db.pengrajin.find({}).sort([("nama", 1)]).to_list(1000)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


@api_router.post("/pengrajin")
async def create_pengrajin(p: PengrajinCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if not p.nama.strip():
        raise HTTPException(status_code=400, detail="Nama pengrajin wajib diisi")
    doc = p.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["_id"]
    r = await db.pengrajin.insert_one(doc)
    doc["_id"] = str(r.inserted_id)
    return doc


@api_router.put("/pengrajin/{pid}")
async def update_pengrajin(pid: str, p: PengrajinCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.pengrajin.update_one({"_id": ObjectId(pid)}, {"$set": p.model_dump()})
    return {"message": "Pengrajin updated"}


@api_router.delete("/pengrajin/{pid}")
async def delete_pengrajin(pid: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    r = await db.pengrajin.delete_one({"_id": ObjectId(pid)})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pengrajin not found")
    return {"message": "Pengrajin deleted"}


# Helper: get SPK allocation qty for (po_id, barang_id, pengrajin_id)
async def _get_spk_allocation(po_id: str, barang_id: str, pengrajin_id: str) -> int:
    """Total qty allocated to this pengrajin for this barang across all SPKs tied to this PO.
    Supports both new schema (SPKItem.pengrajin_id) and legacy (allocations[])."""
    po = await db.po.find_one({"_id": ObjectId(po_id)}) if po_id else None
    if not po:
        return 0
    no_po = po.get("no_po", "")
    total = 0
    async for spk in db.spk.find({"items.no_po": no_po}):
        for it in spk.get("items", []):
            if it.get("no_po") == no_po and it.get("barang_id") == barang_id:
                # New schema: pengrajin_id directly on item
                if it.get("pengrajin_id") == pengrajin_id:
                    total += int(it.get("qty", 0) or 0)
                # Legacy: allocations array
                elif not it.get("pengrajin_id"):
                    for a in it.get("allocations", []) or []:
                        if a.get("pengrajin_id") == pengrajin_id:
                            total += int(a.get("qty", 0) or 0)
    return total


async def _get_spk_allocations_by_barang(no_po: str, barang_id: str) -> list:
    """Return list of {pengrajin_id, pengrajin_nama, qty} for a (no_po, barang_id)."""
    result: Dict[str, Dict[str, Any]] = {}  # pengrajin_id -> {nama, qty}
    async for spk in db.spk.find({"items.no_po": no_po}):
        for it in spk.get("items", []):
            if it.get("no_po") != no_po or it.get("barang_id") != barang_id:
                continue
            if it.get("pengrajin_id"):
                pid = it["pengrajin_id"]
                nama = it.get("pengrajin_nama") or it.get("nama_pengrajin") or ""
                result.setdefault(pid, {"pengrajin_id": pid, "pengrajin_nama": nama, "qty": 0})
                result[pid]["qty"] += int(it.get("qty", 0) or 0)
            else:
                for a in it.get("allocations", []) or []:
                    pid = a.get("pengrajin_id")
                    if not pid: continue
                    nama = a.get("pengrajin_nama") or ""
                    result.setdefault(pid, {"pengrajin_id": pid, "pengrajin_nama": nama, "qty": 0})
                    result[pid]["qty"] += int(a.get("qty", 0) or 0)
    return list(result.values())


async def _get_bm_qty_per_pengrajin(po_id: str, barang_id: str, pengrajin_id: str, exclude_bm_id: Optional[str] = None) -> int:
    """Sum qty_diterima for (po, barang, pengrajin_id) across all BM (optionally excluding one)."""
    total = 0
    async for bm in db.barang_masuk.find({"po_id": po_id}):
        if exclude_bm_id and str(bm.get("_id")) == exclude_bm_id:
            continue
        for it in bm.get("items", []):
            if it.get("barang_id") == barang_id and (it.get("pengrajin_id") or "") == pengrajin_id:
                total += int(it.get("qty_diterima", 0) or 0)
    return total


async def _get_progres_stage_per_pengrajin(po_id: str, barang_id: str, pengrajin_id: str, stage: str, exclude_entry_id: Optional[str] = None) -> int:
    match: Dict[str, Any] = {"po_id": po_id, "item_id": barang_id, "stage": stage, "pengrajin_id": pengrajin_id}
    if exclude_entry_id:
        match["_id"] = {"$ne": ObjectId(exclude_entry_id)}
    total = 0
    async for e in db.progres.find(match):
        total += int(e.get("qty", 0) or 0)
    return total


@api_router.get("/spk/allocations")
async def get_spk_allocations(no_po: str, barang_id: str, user: dict = Depends(get_current_user)):
    """Return aggregated pengrajin allocations for a (no_po, barang_id) — used by BM & Progres UI."""
    return await _get_spk_allocations_by_barang(no_po, barang_id)


# ===== Additional Rekap Endpoints =====
@api_router.get("/rekap/per-barang")
async def get_rekap_per_barang(
    no_po: Optional[str] = None,
    barang_id: Optional[str] = None,
    pengrajin_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Rekap per barang: aggregate qty_masuk & qty_packing per barang.
    Collects ALL pengrajin names (from BM items) and ALL no_po values for each barang."""
    barang_masuk = await db.barang_masuk.find({}).to_list(1000)
    progres = await db.progres.find({}).to_list(1000)

    agg: Dict[str, Dict[str, Any]] = {}
    for bm in barang_masuk:
        if date_from and (bm.get("tanggal_masuk") or "") < date_from: continue
        if date_to and (bm.get("tanggal_masuk") or "") > date_to: continue
        if no_po and no_po not in (bm.get("no_po") or ""): continue
        for item in bm.get("items", []):
            bid = item.get("barang_id")
            if not bid: continue
            if barang_id and bid != barang_id: continue
            if pengrajin_id and (item.get("pengrajin_id") or "") != pengrajin_id: continue
            if bid not in agg:
                agg[bid] = {
                    "barang_id": bid,
                    "nama_barang": item.get("nama_barang", ""),
                    "gambar_path": item.get("gambar_path"),
                    "qty_masuk": 0,
                    "qty_packing": 0,
                    "_pengrajin_set": set(),
                    "_no_po_set": set(),
                }
            agg[bid]["qty_masuk"] += item.get("qty_diterima", 0) or 0
            pnama = item.get("pengrajin_nama") or item.get("nama_pengrajin") or ""
            if pnama: agg[bid]["_pengrajin_set"].add(pnama)
            if bm.get("no_po"): agg[bid]["_no_po_set"].add(bm["no_po"])

    for p in progres:
        bid = p.get("item_id")
        if bid in agg:
            agg[bid]["qty_packing"] += int(p.get("qty", 0) or 0) if p.get("stage") == "packing" else 0

    result = []
    for v in agg.values():
        v["no_po_list"] = sorted(v.pop("_no_po_set"))
        v["pengrajin_names"] = sorted(v.pop("_pengrajin_set"))
        v["nama_pengrajin"] = ", ".join(v["pengrajin_names"])  # legacy field, now comma-joined
        v["no_po"] = ", ".join(v["no_po_list"])
        v["kurang"] = v["qty_masuk"] - v["qty_packing"]
        result.append(v)
    # Sort by nama_barang A-Z
    result.sort(key=lambda x: (x.get("nama_barang") or "").lower())
    if user["role"] == "guest":
        for r in result:
            r.pop("nama_pengrajin", None)
            r.pop("pengrajin_names", None)
    return result


@api_router.get("/rekap/progres")
async def get_rekap_progres(
    no_po: Optional[str] = None,
    barang_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Rekap progres per PO+barang. Aggregate from stage entries."""
    barang_masuk = await db.barang_masuk.find({}).to_list(1000)
    
    bm_agg: Dict[str, Dict[str, Any]] = {}
    for bm in barang_masuk:
        if no_po and no_po not in (bm.get("no_po") or ""): continue
        if date_from and (bm.get("tanggal_masuk") or "") < date_from: continue
        if date_to and (bm.get("tanggal_masuk") or "") > date_to: continue
        po_id = bm.get("po_id", "")
        for item in bm.get("items", []):
            bid = item.get("barang_id")
            if not bid: continue
            if barang_id and bid != barang_id: continue
            k = f"{po_id}_{bid}"
            if k not in bm_agg:
                bm_agg[k] = {
                    "po_id": po_id,
                    "no_po": bm.get("no_po", ""),
                    "nama_barang": item.get("nama_barang", ""),
                    "gambar_path": item.get("gambar_path"),
                    "qty_masuk": 0,
                }
            bm_agg[k]["qty_masuk"] += item.get("qty_diterima", 0) or 0
    
    pipeline = [
        {"$match": {"stage": {"$in": VALID_STAGES}}},
        {"$group": {
            "_id": {"po_id": "$po_id", "item_id": "$item_id", "stage": "$stage"},
            "total": {"$sum": "$qty"},
            "last_tanggal": {"$max": "$tanggal"},
        }},
    ]
    stage_agg: Dict[str, Dict[str, Any]] = {}
    async for r in db.progres.aggregate(pipeline):
        _id = r.get("_id", {})
        k = f"{_id.get('po_id','')}_{_id.get('item_id','')}"
        if k not in stage_agg:
            stage_agg[k] = {s: 0 for s in VALID_STAGES}
            stage_agg[k]["tanggal"] = ""
        stage_agg[k][_id["stage"]] = int(r.get("total", 0) or 0)
        lt = r.get("last_tanggal") or ""
        if lt > stage_agg[k]["tanggal"]:
            stage_agg[k]["tanggal"] = lt
    
    result = []
    for k, info in bm_agg.items():
        st = stage_agg.get(k, {s: 0 for s in VALID_STAGES})
        grinda = st.get("grinda", 0); servis = st.get("servis", 0); finishing = st.get("finishing", 0); packing = st.get("packing", 0)
        qty_masuk = info["qty_masuk"]
        result.append({
            "po_id": info["po_id"],
            "no_po": info["no_po"],
            "nama_barang": info["nama_barang"],
            "gambar_path": info["gambar_path"],
            "qty_masuk": qty_masuk,
            "grinda": grinda, "servis": servis, "finishing": finishing, "packing": packing,
            "sisa_grinda": max(qty_masuk - grinda, 0),
            "sisa_servis": max(grinda - servis, 0),
            "sisa_finishing": max(servis - finishing, 0),
            "sisa_packing": max(finishing - packing, 0),
            "tanggal_terakhir": st.get("tanggal", "") or "",
            "komplit": packing >= qty_masuk and qty_masuk > 0,
        })
    # Sort by nama_barang A-Z, then no_po
    result.sort(key=lambda x: ((x.get("nama_barang") or "").lower(), x.get("no_po") or ""))
    return result


@api_router.get("/rekap/staffing-summary")
async def get_rekap_staffing_summary(no_po: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Rekap staffing per PO+barang: qty_po vs qty_staffing dengan kurang_kirim."""
    query = {"no_po": no_po} if no_po else {}
    pos = await db.po.find(query).to_list(1000)
    staffing = await db.staffing.find({}).to_list(1000)
    for p in pos: p["_id"] = str(p["_id"])
    for s in staffing: s["_id"] = str(s["_id"])
    result = []
    for po in pos:
        for item in po.get("items", []):
            staffing_qty = sum(
                si.get("qty", 0) for s in staffing if s.get("po_id") == po["_id"]
                for si in s.get("items", []) if si.get("barang_id") == item.get("barang_id")
            )
            result.append({
                "no_po": po["no_po"],
                "nama_barang": item.get("nama_barang", ""),
                "gambar_path": item.get("gambar_path"),
                "qty_po": item.get("qty", 0),
                "qty_staffing": staffing_qty,
                "kurang_kirim": item.get("qty", 0) - staffing_qty,
            })
    return result


async def _excel_with_images(rows, sheet_name, headers, keys, user):
    """Generate Excel with photo column."""
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    ws = workbook.add_worksheet(sheet_name)
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#8B5A2B', 'font_color': 'white', 'align': 'center', 'valign': 'vcenter', 'border': 1})
    cell_fmt = workbook.add_format({'valign': 'vcenter', 'border': 1})
    ws.set_column(0, 0, 14)
    for i in range(len(headers)):
        ws.set_column(i+1, i+1, 20)
    ws.set_row(0, 25)
    ws.write(0, 0, "Foto", header_fmt)
    for i, h in enumerate(headers):
        ws.write(0, i+1, h, header_fmt)
    for r_idx, row in enumerate(rows, start=1):
        ws.set_row(r_idx, 60)
        gp = row.get("gambar_path")
        if gp:
            try:
                data, _ = get_object(gp)
                pil = PILImage.open(BytesIO(data))
                pil.thumbnail((80, 80))
                out = BytesIO()
                pil.save(out, format='PNG')
                out.seek(0)
                ws.insert_image(r_idx, 0, "img.png", {'image_data': out, 'x_offset': 5, 'y_offset': 5})
            except Exception:
                ws.write(r_idx, 0, "-", cell_fmt)
        else:
            ws.write(r_idx, 0, "-", cell_fmt)
        for i, k in enumerate(keys):
            val = row.get(k, "")
            if user.get("role") == "guest" and k == "nama_pengrajin":
                val = ""
            ws.write(r_idx, i+1, val, cell_fmt)
    workbook.close()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={sheet_name.lower().replace(' ','-')}.xlsx"})


@api_router.get("/export/barang-masuk/pdf")
async def export_all_bm_pdf(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    items = await db.barang_masuk.find({}).to_list(1000)
    if search:
        s = search.lower()
        items = [bm for bm in items if s in (bm.get("no_po","").lower()+bm.get("penerima","").lower()) or any(s in (i.get("nama_barang","")+i.get("nama_pengrajin","")).lower() for i in bm.get("items",[]))]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=8*mm, rightMargin=8*mm)
    story = []
    styles = getSampleStyleSheet()
    _brand_header(story, "REKAP BARANG MASUK", f"Filter: {search or 'Semua'}", styles)
    body_style = ParagraphStyle('body', parent=styles["BodyText"], fontSize=8, leading=10)
    data = [["Foto", "No PO", "Tanggal", "Penerima", "Barang", "Pengrajin", "Qty"]]
    for bm in items:
        for item in bm.get("items", []):
            img = _fetch_image_flowable(item.get("gambar_path"), 16) or Paragraph("-", body_style)
            data.append([img, bm.get("no_po",""), bm.get("tanggal_masuk",""), bm.get("penerima",""), Paragraph(item.get("nama_barang",""), body_style), Paragraph(item.get("nama_pengrajin",""), body_style), str(item.get("qty_diterima",0))])
    table = Table(data, repeatRows=1, colWidths=[18*mm, 24*mm, 22*mm, 26*mm, 40*mm, 30*mm, 14*mm])
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E5E5E5")), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8B5A2B")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTSIZE", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=barang-masuk-all.pdf"})


async def _filter_staffing(no_po, date_from, date_to, pengrajin_id, barang_id, tanggal=None):
    query: Dict[str, Any] = {}
    if tanggal:
        query["tanggal_keluar"] = tanggal
    elif date_from or date_to:
        query["tanggal_keluar"] = {}
        if date_from: query["tanggal_keluar"]["$gte"] = date_from
        if date_to: query["tanggal_keluar"]["$lte"] = date_to
    if no_po:
        query["no_po"] = {"$regex": no_po, "$options": "i"}
    items = await db.staffing.find(query).to_list(1000)
    if barang_id or pengrajin_id:
        filtered = []
        for st in items:
            keep = False
            for it in st.get("items", []):
                if barang_id and it.get("barang_id") != barang_id: continue
                if pengrajin_id and (it.get("pengrajin_id") or "") != pengrajin_id: continue
                keep = True; break
            if keep: filtered.append(st)
        items = filtered
    return items


@api_router.get("/export/staffing/pdf")
async def export_all_staffing_pdf(
    no_po: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pengrajin_id: Optional[str] = None,
    barang_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    items = await _filter_staffing(no_po, date_from, date_to, pengrajin_id, barang_id)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=8*mm, rightMargin=8*mm)
    story = []
    styles = getSampleStyleSheet()
    subtitle = "Semua data staffing"
    filters = []
    if no_po: filters.append(f"PO: {no_po}")
    if date_from or date_to: filters.append(f"Tanggal: {date_from or '...'} → {date_to or '...'}")
    if filters: subtitle = " | ".join(filters)
    _brand_header(story, "REKAP STAFFING", subtitle, styles)
    body_style = ParagraphStyle('body', parent=styles["BodyText"], fontSize=8, leading=10)
    data = [["Foto", "No PO", "Tanggal", "Barang", "Pengrajin", "Qty"]]
    for st in items:
        for item in st.get("items", []):
            if barang_id and item.get("barang_id") != barang_id: continue
            if pengrajin_id and (item.get("pengrajin_id") or "") != pengrajin_id: continue
            img = _fetch_image_flowable(item.get("gambar_path"), 16) or Paragraph("-", body_style)
            data.append([img, st.get("no_po",""), st.get("tanggal_keluar",""), Paragraph(item.get("nama_barang",""), body_style), Paragraph(item.get("pengrajin_nama") or item.get("nama_pengrajin",""), body_style), str(item.get("qty",0))])
    table = Table(data, repeatRows=1, colWidths=[18*mm, 28*mm, 24*mm, 50*mm, 34*mm, 14*mm])
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E5E5E5")), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8B5A2B")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=staffing-all.pdf"})


@api_router.get("/export/staffing/excel")
async def export_staffing_excel(
    no_po: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pengrajin_id: Optional[str] = None,
    barang_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    items = await _filter_staffing(no_po, date_from, date_to, pengrajin_id, barang_id)
    rows = []
    for st in items:
        for item in st.get("items", []):
            if barang_id and item.get("barang_id") != barang_id: continue
            if pengrajin_id and (item.get("pengrajin_id") or "") != pengrajin_id: continue
            rows.append({
                "no_po": st.get("no_po",""),
                "tanggal_keluar": st.get("tanggal_keluar",""),
                "nama_barang": item.get("nama_barang",""),
                "nama_pengrajin": item.get("pengrajin_nama") or item.get("nama_pengrajin",""),
                "qty": item.get("qty",0),
                "gambar_path": item.get("gambar_path"),
            })
    return await _excel_with_images(rows, "Staffing", ["No PO", "Tanggal", "Barang", "Pengrajin", "Qty"], ["no_po","tanggal_keluar","nama_barang","nama_pengrajin","qty"], user)


@api_router.get("/export/barang-masuk/excel")
async def export_barang_masuk_excel_v2(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    items = await db.barang_masuk.find({}).to_list(1000)
    if search:
        s = search.lower()
        items = [bm for bm in items if s in (bm.get("no_po","").lower()+bm.get("penerima","").lower()) or any(s in (i.get("nama_barang","")+i.get("nama_pengrajin","")).lower() for i in bm.get("items",[]))]
    rows = []
    for bm in items:
        for item in bm.get("items", []):
            rows.append({
                "no_po": bm.get("no_po", ""),
                "tanggal_masuk": bm.get("tanggal_masuk", ""),
                "penerima": bm.get("penerima", ""),
                "nama_barang": item.get("nama_barang", ""),
                "nama_pengrajin": item.get("nama_pengrajin", ""),
                "qty_diterima": item.get("qty_diterima", 0),
                "gambar_path": item.get("gambar_path"),
            })
    return await _excel_with_images(rows, "Barang Masuk", ["No PO", "Tanggal", "Penerima", "Barang", "Pengrajin", "Qty"], ["no_po","tanggal_masuk","penerima","nama_barang","nama_pengrajin","qty_diterima"], user)


@api_router.get("/rekap/staffing-detail")
async def get_rekap_staffing_detail(tanggal_from: Optional[str] = None, tanggal_to: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Rekap staffing: data staffing per barang berdasarkan tanggal range."""
    query = {}
    if tanggal_from and tanggal_to:
        query["tanggal_keluar"] = {"$gte": tanggal_from, "$lte": tanggal_to}
    elif tanggal_from:
        query["tanggal_keluar"] = {"$gte": tanggal_from}
    elif tanggal_to:
        query["tanggal_keluar"] = {"$lte": tanggal_to}
    staffing = await db.staffing.find(query).to_list(1000)
    result = []
    for st in staffing:
        for item in st.get("items", []):
            result.append({
                "no_po": st.get("no_po", ""),
                "tanggal_keluar": st.get("tanggal_keluar", ""),
                "nama_barang": item.get("nama_barang", ""),
                "nama_pengrajin": item.get("nama_pengrajin", ""),
                "gambar_path": item.get("gambar_path"),
                "qty": item.get("qty", 0),
            })
    if user["role"] == "guest":
        for r in result:
            r.pop("nama_pengrajin", None)
    return result


# ===== Activity Log Endpoints =====
@api_router.get("/activity-log")
async def get_activity_log(
    action: Optional[str] = None,
    resource: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 500,
    user: dict = Depends(get_current_user),
):
    if user["role"] != "admin" and user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Not authorized")
    query: Dict[str, Any] = {}
    if action: query["action"] = action
    if resource: query["resource"] = resource
    if user_id: query["user_id"] = user_id
    if date_from or date_to:
        query["timestamp"] = {}
        if date_from: query["timestamp"]["$gte"] = date_from
        if date_to: query["timestamp"]["$lte"] = date_to + "T23:59:59Z"
    entries = await db.activity_log.find(query).sort([("timestamp", -1)]).to_list(min(max(limit, 1), 2000))
    for e in entries:
        e["_id"] = str(e["_id"])
    return entries


@api_router.delete("/activity-log/purge")
async def purge_activity_log(before: Optional[str] = None, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if not before:
        raise HTTPException(status_code=400, detail="Query param 'before' (YYYY-MM-DD) is required")
    result = await db.activity_log.delete_many({"timestamp": {"$lt": before}})
    return {"deleted": result.deleted_count}


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

# ===== DEBUG: Barang Qty Inconsistency Check =====
@api_router.get("/debug/barang-qty/{barang_name}")
async def debug_barang_qty(barang_name: str, user: dict = Depends(get_current_user)):
    """Check qty inconsistency: PO qty vs Barang Masuk qty for a specific barang.
    Only accessible to admin."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    
    # Find all barang matching name (case-insensitive)
    barangs = []
    async for b in db.barang.find({"nama_barang": {"$regex": barang_name, "$options": "i"}}):
        barangs.append(str(b["_id"]))
    
    if not barangs:
        return {"error": f"No barang found matching: {barang_name}", "barangs": []}
    
    result = {
        "barang_name": barang_name,
        "barang_ids": barangs,
        "po_entries": [],
        "barang_masuk_entries": [],
        "summary": {}
    }
    
    # Find all POs containing these barangs
    all_pos = {}
    async for po in db.po.find({"items.barang_id": {"$in": barangs}}):
        po_id = str(po["_id"])
        all_pos[po_id] = {
            "no_po": po.get("no_po", ""),
            "items": []
        }
        for item in po.get("items", []):
            if item.get("barang_id") in barangs:
                all_pos[po_id]["items"].append({
                    "barang_id": item.get("barang_id"),
                    "qty": item.get("qty", 0)
                })
        result["po_entries"].append({
            "po_id": po_id,
            "no_po": all_pos[po_id]["no_po"],
            "items": all_pos[po_id]["items"],
            "total_qty": sum(i.get("qty", 0) for i in all_pos[po_id]["items"])
        })
    
    # Find Barang Masuk for those POs
    po_ids = list(all_pos.keys())
    total_po_qty = sum(e.get("total_qty", 0) for e in result["po_entries"])
    total_bm_qty = 0
    
    async for bm in db.barang_masuk.find({"po_id": {"$in": po_ids}}):
        for item in bm.get("items", []):
            if item.get("barang_id") in barangs:
                result["barang_masuk_entries"].append({
                    "barang_masuk_id": str(bm["_id"]),
                    "po_id": bm.get("po_id"),
                    "tanggal_masuk": bm.get("tanggal_masuk", ""),
                    "barang_id": item.get("barang_id"),
                    "qty_diterima": item.get("qty_diterima", 0)
                })
                total_bm_qty += item.get("qty_diterima", 0)
    
    result["summary"] = {
        "total_po_qty": total_po_qty,
        "total_barang_masuk_qty": total_bm_qty,
        "difference": total_po_qty - total_bm_qty,
        "consistency": "✅ OK" if total_po_qty == total_bm_qty else "❌ MISMATCH"
    }
    
    return result

# ===== ADMIN: Fix PO Barang Qty Inconsistency =====
@api_router.get("/admin/po-fix/by-no/{no_po}/{barang_name}")
async def admin_po_fix_check(no_po: str, barang_name: str, user: dict = Depends(get_current_user)):
    """Check what the fix would be for a PO barang qty mismatch. Admin only."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    
    # Find barang by name
    barang = await db.barang.find_one({"nama_barang": {"$regex": barang_name, "$options": "i"}})
    if not barang:
        raise HTTPException(status_code=404, detail=f"Barang not found: {barang_name}")
    
    barang_id = str(barang["_id"])
    
    # Find PO by no_po
    po = await db.po.find_one({"no_po": no_po})
    if not po:
        raise HTTPException(status_code=404, detail=f"PO not found: {no_po}")
    
    po_id = str(po["_id"])
    current_diterima = 0
    for item in po.get("items", []):
        if str(item.get("barang_id")) == barang_id:
            current_diterima = item.get("qty_diterima", 0) or 0
            break
    
    # Calculate actual Barang Masuk total for this barang from this PO
    actual_bm_qty = 0
    async for bm in db.barang_masuk.find({"po_id": po_id}):
        for item in bm.get("items", []):
            if str(item.get("barang_id")) == barang_id:
                actual_bm_qty += item.get("qty_diterima", 0) or 0
    
    return {
        "no_po": no_po,
        "barang_name": barang_name,
        "barang_id": barang_id,
        "po_id": po_id,
        "current_qty_diterima_in_po": current_diterima,
        "actual_barang_masuk_total": actual_bm_qty,
        "match": current_diterima == actual_bm_qty,
        "action_needed": "Update PO item qty_diterima from {} to {}".format(current_diterima, actual_bm_qty) if current_diterima != actual_bm_qty else "No action needed"
    }

@api_router.post("/admin/po-fix/by-no/{no_po}/{barang_name}")
async def admin_po_fix_execute(no_po: str, barang_name: str, user: dict = Depends(get_current_user)):
    """Actually fix the PO barang qty_diterima to match Barang Masuk. Admin only."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    
    # Find barang by name
    barang = await db.barang.find_one({"nama_barang": {"$regex": barang_name, "$options": "i"}})
    if not barang:
        raise HTTPException(status_code=404, detail=f"Barang not found: {barang_name}")
    
    barang_id = str(barang["_id"])
    
    # Find PO by no_po
    po = await db.po.find_one({"no_po": no_po})
    if not po:
        raise HTTPException(status_code=404, detail=f"PO not found: {no_po}")
    
    po_id = str(po["_id"])
    
    # Calculate actual Barang Masuk total for this barang from this PO
    actual_bm_qty = 0
    async for bm in db.barang_masuk.find({"po_id": po_id}):
        for item in bm.get("items", []):
            if str(item.get("barang_id")) == barang_id:
                actual_bm_qty += item.get("qty_diterima", 0) or 0
    
    # Update PO items - find the matching item and update qty_diterima
    updated = False
    old_qty = 0
    for i, item in enumerate(po.get("items", [])):
        if str(item.get("barang_id")) == barang_id:
            old_qty = item.get("qty_diterima", 0)
            po["items"][i]["qty_diterima"] = actual_bm_qty
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=400, detail="Item not found in PO")
    
    # Save back to database
    result = await db.po.update_one(
        {"_id": po["_id"]},
        {"$set": {"items": po["items"]}}
    )
    
    # Log the fix
    try:
        await db.activity_log.insert_one({
            "user_id": user.get("_id", ""),
            "user_email": user.get("email", ""),
            "user_role": user.get("role", ""),
            "action": "po_qty_fix",
            "resource": "po",
            "resource_label": "PO",
            "resource_id": po_id,
            "path": f"/admin/po-fix/by-no/{no_po}/{barang_name}",
            "method": "POST",
            "status_code": 200,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip": "",
            "details": f"Fixed {barang_name} qty_diterima from {old_qty} to {actual_bm_qty}"
        })
    except Exception as e:
        logger.warning(f"Failed to log PO fix: {e}")
    
    return {
        "success": True,
        "no_po": no_po,
        "barang_name": barang_name,
        "old_qty_diterima": old_qty,
        "new_qty_diterima": actual_bm_qty,
        "message": f"Fixed PO {no_po} {barang_name} qty_diterima: {old_qty} → {actual_bm_qty}"
    }

@api_router.post("/admin/sync-po-qty/{no_po}/{barang_name}")
async def sync_po_qty(no_po: str, barang_name: str, user: dict = Depends(get_current_user)):
    """Sync PO item qty_diterima with actual Barang Masuk total. Admin only."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    
    barang = await db.barang.find_one({"nama_barang": {"$regex": barang_name, "$options": "i"}})
    if not barang:
        raise HTTPException(status_code=404, detail=f"Barang not found: {barang_name}")
    
    barang_id = str(barang["_id"])
    po = await db.po.find_one({"no_po": no_po})
    if not po:
        raise HTTPException(status_code=404, detail=f"PO not found: {no_po}")
    
    po_id = str(po["_id"])
    actual_qty = 0
    async for bm in db.barang_masuk.find({"po_id": po_id}):
        for item in bm.get("items", []):
            if str(item.get("barang_id")) == barang_id:
                actual_qty += item.get("qty_diterima", 0) or 0
    
    old_qty = 0
    found = False
    for i, item in enumerate(po.get("items", [])):
        if str(item.get("barang_id")) == barang_id:
            old_qty = item.get("qty_diterima", 0) or 0
            po["items"][i]["qty_diterima"] = actual_qty
            found = True
            break
    
    if not found:
        raise HTTPException(status_code=400, detail="Item not found in PO")
    
    await db.po.update_one({"_id": po["_id"]}, {"$set": {"items": po["items"]}})
    
    return {
        "success": True,
        "no_po": no_po,
        "barang_name": barang_name,
        "old_qty_diterima": old_qty,
        "new_qty_diterima": actual_qty,
        "message": f"Synced {barang_name}: {old_qty} -> {actual_qty}"
    }

# Register all API routes with the FastAPI app
app.include_router(api_router)</replaceContent>
</invoke>
</replaceContent>
</invoke>

