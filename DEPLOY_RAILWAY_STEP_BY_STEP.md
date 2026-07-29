# 🚀 Deploy AGFDATA ke Railway — Step by Step

Panduan lengkap deploy AGFDATA dari zero ke production di Railway + Vercel + MongoDB Atlas.

**Total waktu**: ~30-45 menit  
**Biaya**: GRATIS (semua free tier)

---

## 📋 Checklist Sebelum Mulai

- [ ] Punya akun GitHub (repo sudah ada: `podoslamet20-debug/APLIKASI-FIX-DADI`)
- [ ] Punya akun MongoDB Atlas (buat di https://mongodb.com/atlas — GRATIS)
- [ ] Punya akun Railway (buat di https://railway.app — GRATIS, login pakai GitHub)
- [ ] Punya akun Vercel (buat di https://vercel.com — GRATIS, login pakai GitHub)

---

## STEP 1: Setup MongoDB Atlas (10 menit)

### 1.1 Buat Cluster
1. Login ke https://cloud.mongodb.com
2. Klik **"Build a Database"** → pilih **"M0 FREE"**
3. Provider: **AWS**, Region: **Singapore (ap-southeast-1)** (paling cepat untuk Indonesia)
4. Cluster Name: `agfdata-cluster`
5. Klik **"Create"** → tunggu ~3 menit sampai cluster ready

### 1.2 Setup Database User
1. Muncul modal **"Security Quickstart"** → pilih **"Username and Password"**
2. Username: `agfdata`
3. Password: klik **"Autogenerate Secure Password"** → **COPY & SIMPAN** (contoh: `Rk8Xj2mNpQ4wLt9v`)
4. Klik **"Create User"**

### 1.3 Network Access
1. Di section **"Where would you like to connect from?"** → pilih **"My Local Environment"**
2. Klik **"Add My Current IP Address"** — nanti kita ganti ke allow-all
3. Klik **"Finish and Close"**
4. Buka menu kiri **"Network Access"** → klik **"Add IP Address"**
5. Klik **"ALLOW ACCESS FROM ANYWHERE"** (0.0.0.0/0) — ini penting untuk Railway
6. Klik **"Confirm"**

### 1.4 Copy Connection String
1. Kembali ke **"Database"** menu → klik tombol **"Connect"** di cluster
2. Pilih **"Drivers"**
3. Driver: **Python**, Version: **3.11 or later**
4. Copy connection string, contoh:
   ```
   mongodb+srv://agfdata:<password>@agfdata-cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=agfdata-cluster
   ```
5. **Ganti `<password>`** dengan password yang tadi di-copy di step 1.2
6. **Simpan connection string ini** — dipakai di Railway sebagai `MONGO_URL`

---

## STEP 2: Deploy Backend ke Railway (10 menit)

### 2.1 Buat Project
1. Login ke https://railway.app (pakai GitHub)
2. Klik **"New Project"** → pilih **"Deploy from GitHub repo"**
3. Cari & pilih repo: **`podoslamet20-debug/APLIKASI-FIX-DADI`**
4. Railway auto-detect → klik **"Deploy Now"**

### 2.2 Set Root Directory
1. Setelah project dibuat, klik service yang muncul
2. Buka tab **"Settings"**
3. Scroll ke **"Root Directory"** → set ke: **`backend`**
4. Klik **"Update"**

### 2.3 Set Environment Variables
1. Buka tab **"Variables"** → klik **"Raw Editor"** (biar bisa paste sekaligus)
2. Paste ini (ganti nilai bertanda `<>`):

```env
MONGO_URL=mongodb+srv://agfdata:<PASSWORD>@agfdata-cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=agfdata-cluster
DB_NAME=agfdata
JWT_SECRET=pOg7tWWmuVVPVhV_IepUxt7Nvj1oItH6e2RzkggXalSFVskdrJA1Fovu02ywwnq9Q7GZjM7OTeS9XPqCnNlORg
CORS_ORIGINS=*
ADMIN_EMAIL=admin@agfdata.com
ADMIN_PASSWORD=GantiPasswordAdminYangKuat123!
```

⚠️ **PENTING**:
- Ganti `MONGO_URL` dengan connection string dari MongoDB Atlas
- **JWT_SECRET** di atas sudah di-generate random khusus untuk Anda — atau generate baru: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- Ganti **`ADMIN_PASSWORD`** ke password kuat (minimal 12 karakter, campur huruf besar/kecil/angka/simbol)
- `CORS_ORIGINS=*` untuk sementara — nanti kita ganti setelah frontend di-deploy

3. Klik **"Update Variables"**

### 2.4 Generate Public URL
1. Buka tab **"Settings"** → scroll ke **"Networking"**
2. Klik **"Generate Domain"**
3. Anda dapat URL seperti: `https://agfdata-production-xxxx.up.railway.app`
4. **Copy URL ini** — dipakai untuk `REACT_APP_BACKEND_URL` di frontend

### 2.5 Verify Backend
Tunggu deployment selesai (~3-5 menit, lihat tab **"Deployments"**), lalu test:

```bash
curl https://agfdata-production-xxxx.up.railway.app/api/health
# Expected: {"status":"ok","service":"agfdata-backend"}
```

Test login:
```bash
curl -X POST https://agfdata-production-xxxx.up.railway.app/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@agfdata.com","password":"GantiPasswordAdminYangKuat123!"}'
```
Kalau dapat response JSON dengan `role: admin` → backend SUKSES 🎉

---

## STEP 3: Deploy Frontend ke Vercel (10 menit)

Vercel lebih cepat + gratis untuk React static site (Railway juga bisa tapi lebih boros resource).

### 3.1 Import Project
1. Login ke https://vercel.com (pakai GitHub)
2. Klik **"Add New..."** → **"Project"**
3. Cari & pilih repo: **`podoslamet20-debug/APLIKASI-FIX-DADI`**
4. Klik **"Import"**

### 3.2 Configure Build Settings
1. **Framework Preset**: `Create React App`
2. **Root Directory**: klik **"Edit"** → set ke `frontend`
3. **Build Command**: `yarn build` (auto-detect dari vercel.json)
4. **Output Directory**: `build`
5. **Install Command**: `yarn install`

### 3.3 Set Environment Variables
Di section **"Environment Variables"**:

| Name | Value |
|------|-------|
| `REACT_APP_BACKEND_URL` | `https://agfdata-production-xxxx.up.railway.app` (dari Step 2.4) |

⚠️ **JANGAN pakai trailing slash** (`/`) di URL

### 3.4 Deploy
1. Klik **"Deploy"** — tunggu ~2-3 menit
2. Setelah selesai, Anda dapat URL frontend: `https://aplikasi-fix-dadi.vercel.app`
3. **Copy URL frontend** ini

---

## STEP 4: Finalisasi CORS (2 menit)

### 4.1 Update Railway Backend
1. Kembali ke Railway → project → tab **"Variables"**
2. Update variable `CORS_ORIGINS`:
   ```
   CORS_ORIGINS=https://aplikasi-fix-dadi.vercel.app
   ```
   (URL frontend dari Step 3.4, TANPA trailing slash)
3. Klik **"Update"** — Railway akan auto-redeploy backend

### 4.2 Verify Full Flow
1. Buka frontend URL: `https://aplikasi-fix-dadi.vercel.app`
2. Login dengan `admin@agfdata.com` + password admin yang Anda set
3. **Test upload foto**: menu **Database Barang** → tombol **"+ Tambah Barang"** → upload gambar
4. Kalau upload berhasil dan gambar tampil → **DEPLOY SUKSES 🎉**

---

## STEP 5: Post-Deploy Checklist

- [ ] Login sebagai admin, buka **User Management** → **ganti password admin** ke yang lebih kuat
- [ ] Buat user staff/owner/guest baru sesuai kebutuhan (via User Management)
- [ ] Test upload foto → tampil di list Barang
- [ ] Test PO → SPK → Barang Masuk → Progres → verify notif **"PO Siap Kirim"** muncul
- [ ] Test Export PDF/Excel dari halaman Rekap & Staffing
- [ ] (Opsional) Setup custom domain di Vercel & Railway
- [ ] (Opsional) Setup MongoDB Atlas auto-backup

---

## 🐛 Troubleshooting

### Backend "Application failed to respond"
- Cek Railway logs (tab **"Deployments"** → klik latest → view logs)
- Kemungkinan besar: `MONGO_URL` salah (password/user typo, atau `<password>` belum diganti)
- Test connection dari lokal:
  ```bash
  python -c "from pymongo import MongoClient; print(MongoClient('<your-url>').server_info()['version'])"
  ```

### CORS error di browser (frontend gagal fetch backend)
- **Buka Vercel URL frontend** → F12 → Console → cek error CORS
- Pastikan `CORS_ORIGINS` di Railway = URL Vercel EXACT (dengan `https://`, tanpa trailing `/`)
- Kalau URL Vercel berubah (misal branch preview), tambah semua di `CORS_ORIGINS` dipisah koma:
  ```
  CORS_ORIGINS=https://aplikasi-fix-dadi.vercel.app,https://staging.aplikasi-fix-dadi.vercel.app
  ```

### Login sukses tapi keluar sendiri (cookie tidak persist)
- Backend set cookie dengan `SameSite=None; Secure` — HARUS via HTTPS ✅ (Railway sudah HTTPS default)
- Cross-domain cookie: pastikan `axios.defaults.withCredentials = true` (sudah ada di code)
- Kalau masih bermasalah, cek browser: DevTools → Application → Cookies → apakah `access_token` ter-set setelah login?

### Upload foto 500 error
- Cek Railway logs — biasanya MongoDB write error
- Free tier Atlas M0: **limit 512MB storage**. Kalau penuh, upgrade ke M2 ($9/mo) atau hapus file lama
- Cek GridFS collection di Atlas: `agfdata.fs.files` & `agfdata.fs.chunks`

### Railway free tier habis (limit 500 jam/month)
- Free tier Railway: $5 credit/bulan (~500 jam)
- Upgrade ke Hobby ($5/bulan flat) untuk unlimited hours
- Alternative: pindah backend ke **Render.com** (free tier 750 jam/bulan tapi sleep after 15 min idle)

---

## 📊 Ringkasan Biaya (Free Tier)

| Service | Free Limit | Cocok untuk |
|---------|-----------|-------------|
| **MongoDB Atlas M0** | 512MB storage, shared CPU | 500-1000 record + ratusan foto |
| **Railway** | $5 credit/bulan (~500 jam) | Backend running non-stop |
| **Vercel Hobby** | 100GB bandwidth/bulan | Traffic ribuan pengunjung/bulan |

**Total: GRATIS** untuk penggunaan kecil-menengah. Kalau butuh scale, upgrade satu-satu (biaya biasanya $5-9/bulan).

---

## 📁 File Konfigurasi Deploy (sudah tersedia di repo)

- `backend/Procfile` — Railway entry point
- `backend/requirements.txt` — Python dependencies
- `backend/runtime.txt` — Python version
- `backend/railway.json` — Railway build config + health check
- `frontend/vercel.json` — Vercel build config
- `.env` files — TIDAK di-commit (di-.gitignore). Anda set langsung di dashboard Railway/Vercel.

---

## 🔒 Security Reminders

1. **JANGAN commit file `.env`** ke Git (sudah di-.gitignore)
2. **GANTI `ADMIN_PASSWORD`** default → password kuat production
3. **GANTI `JWT_SECRET`** dengan random string 64 char (jangan pakai default)
4. **Setelah first login production**, GANTI password admin lewat User Management menu
5. Setup **2FA** di MongoDB Atlas, Railway, Vercel dashboards
6. Restrict **Network Access** MongoDB Atlas ke Railway static IP kalau memungkinkan (upgrade ke M2+)

---

## 📞 Butuh Bantuan?

Kalau ada error di step manapun, kirim screenshot:
1. Screenshot error yang muncul (browser atau log Railway/Vercel)
2. Step nomor berapa yang gagal
3. Environment variables (JANGAN kirim password/secret — hanya nama variable-nya)

Selamat deploy! 🚀
