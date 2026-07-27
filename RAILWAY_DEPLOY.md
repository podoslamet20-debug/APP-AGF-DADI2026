# Railway Deployment Guide - AGFDATA

## Architecture
Aplikasi ini terdiri dari 2 service terpisah yang harus dideploy sebagai 2 Railway service (atau 1 Railway + 1 Vercel):
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React (CRA + Craco)

## Prerequisite
- Akun Railway (free tier OK untuk testing)
- MongoDB database (bisa pakai MongoDB Atlas free tier, atau Railway MongoDB plugin)

---

## STEP 1: Backend Deployment

### 1.1 Setup Root Directory
Di Railway → New Project → Deploy from GitHub → pilih repo:
- Set **Root Directory** = `backend`
- Railway akan auto-detect `Procfile` + `requirements.txt` + `runtime.txt`

### 1.2 Environment Variables (Railway Dashboard → Variables)
```
MONGO_URL=<mongodb-atlas-connection-string>
DB_NAME=agfdata
JWT_SECRET=<generate-random-64-char-string>
CORS_ORIGINS=https://<your-frontend-domain>
ADMIN_EMAIL=admin@agfdata.com
ADMIN_PASSWORD=<change-this-strong-password>
```

Optional (untuk image upload di storage Emergent — biasanya tidak tersedia di Railway):
```
EMERGENT_LLM_KEY=<optional; leave empty → upload endpoint returns 503>
```

### 1.3 Deploy
- Klik "Deploy" — Railway auto-build via `pip install -r requirements.txt`
- Build biasanya 3-5 menit
- Setelah live, catat URL: `https://<your-backend>.up.railway.app`

### 1.4 Verify
```bash
curl https://<your-backend>.up.railway.app/api/auth/me
# Expect: HTTP 401 {"detail":"Not authenticated"}  ← this means backend is UP
```

---

## STEP 2: Frontend Deployment

### 2.1 Option A - Railway Static Hosting
- New Service → Deploy from GitHub → Root Directory = `frontend`
- Build command: `yarn install && yarn build`
- Start command: `npx serve -s build -p $PORT`

### 2.2 Option B - Vercel (Recommended, easier)
- Import repo di Vercel
- Root Directory = `frontend`
- Framework: **Create React App**
- Build command: `yarn build`
- Output directory: `build`

### 2.3 Environment Variables (frontend)
```
REACT_APP_BACKEND_URL=https://<your-backend>.up.railway.app
```
⚠️ Setelah set env var, TRIGGER REDEPLOY frontend (env vars di-inject saat build, bukan runtime).

### 2.4 Update Backend CORS
Setelah frontend deployed, update backend env var:
```
CORS_ORIGINS=https://<your-frontend>.vercel.app
```
Redeploy backend.

---

## STEP 3: MongoDB Setup (MongoDB Atlas Free Tier)

1. Buat cluster gratis di https://www.mongodb.com/atlas
2. Network Access → Add IP Address → `0.0.0.0/0` (allow all — untuk Railway)
3. Database Access → Add user → catat username/password
4. Connect → Drivers → copy connection string
5. Format: `mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority`
6. Paste ke env var `MONGO_URL` di Railway backend

---

## STEP 4: First Login
- Buka frontend URL
- Login dengan `ADMIN_EMAIL` / `ADMIN_PASSWORD` yang diset di step 1.2
- **SEGERA ganti password admin lewat User Management menu**

---

## Common Issues

### "Application failed to respond"
- Cek Railway logs: apakah `MONGO_URL` valid?
- Test MongoDB Atlas connection dari local: `python -c "from pymongo import MongoClient; MongoClient('<url>').server_info()"`

### CORS error di browser
- Pastikan `CORS_ORIGINS` di backend = URL frontend EXACT (dengan `https://`, tanpa trailing slash)

### Image upload 503
- Object storage butuh `EMERGENT_LLM_KEY` (Emergent internal service, tidak berfungsi di Railway)
- Solusi: implementasi upload ke S3/Cloudinary/local disk (perlu modifikasi kode di `server.py` fungsi `put_object`/`get_object`)

### Backend crash saat migrate progres
- Migrasi legacy progres runs on startup. Idempotent — safe untuk restart berulang.
- Bila error, cek `MONGO_URL` benar & database accessible.

### Cookie tidak set (login sukses tapi tetap logout)
- Backend set cookie dengan `samesite="none"` dan `secure=True` — HARUS via HTTPS. Railway sudah HTTPS default.
- Frontend & backend HARUS beda domain OK (SameSite=None allows cross-site cookie), tapi keduanya harus HTTPS.
