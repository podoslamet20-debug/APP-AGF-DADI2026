# AGFDATA - Furniture Data Management System

## Problem Statement
Full-stack furniture management (Indonesian). Menus: Database Barang, Pengrajin, PO, Barang Masuk, Staffing, SPK, Progres Barang, Rekap Data, User Management, Activity Log.

Roles: **Admin** (full CRUD) · **Staff** (view + edit BM/Staffing/Progres, no prices) · **Guest** (view-only, no prices/pengrajin) · **Owner** (view-all incl. prices & activity log, NO edit).

Pipeline: PO → SPK (per pengrajin, cross-SPK ≤ PO qty) → Barang Masuk (per pengrajin) → Progres (per pengrajin, 4 stages) → Staffing (aggregate).

## Tech Stack
React + Tailwind + Shadcn UI · FastAPI + Motor MongoDB · JWT auth · ReportLab (PDF) · OpenPyXL/XlsxWriter (Excel)

## Changelog

### Feb 2026 — Iter 23 (current) — Portable Storage
- **File upload → MongoDB GridFS** (was Emergent Object Storage). Portable to Railway/any MongoDB host.
- No more `EMERGENT_LLM_KEY` dependency for file uploads. Files stored in `fs.files` + `fs.chunks` collections.
- `put_object`/`get_object`/`delete_object` helpers use `pymongo.GridFS` (sync, compatible with existing ReportLab PDF helpers).

### Feb 2026 — Iter 22 (current)
- **Dashboard Kinerja Pengrajin** (P2 shipped): Monthly ranking. Metrics: qty_selesai (packing count in month), qty_masuk (BM in month), on_time_rate (% SPKs with deadline in month completed by deadline). Badges: MVP (top 3), Produktif, Perlu Improvement, Belum ada aktivitas.
- Endpoint: `GET /api/dashboard/kinerja-pengrajin?month=YYYY-MM`.

### Feb 2026 — Iter 21
- Rekap Per Barang: kolom No PO + ALL pengrajin (comma-joined). Qty_packing fix (from stage=packing).
- Rekap Per Pengrajin: kolom No PO + Barang Dikerjakan (dari SPK).
- Rekap Progres: pengrajin column REMOVED.
- Shared FilterPanel (No PO/Barang/Pengrajin/Date From/To + Sort A-Z + Reset) applied to ALL 5 Rekap tabs.
- Print button per tab. All backend endpoints accept filter query params.

### Feb 2026 — Iter 20
- SPK single-pengrajin per item; cross-SPK validation ≤ PO qty. Multiple SPKs allowed per (PO, barang).
- Rekap PO tab filter panel. Staffing filter panel + export filters.

### Feb 2026 — Iter 18-19
- Owner role + Pengrajin CRUD menu + Per-pengrajin BM/Progres validation.

## Test Credentials
See `/app/memory/test_credentials.md`. Admin/Staff/Guest/Owner all seeded.

## Key API Endpoints
- Auth: `/api/auth/login` `/api/auth/me` `/api/auth/logout`
- Pengrajin: `/api/pengrajin` (GET/POST) `/api/pengrajin/{id}` (PUT/DELETE)
- SPK: `POST/PUT /api/spk` · `GET /api/spk/allocations?no_po=&barang_id=`
- Rekap (with filters no_po/barang_id/pengrajin_id/date_from/date_to):
  - `/api/rekap/all-po`
  - `/api/rekap/per-barang`
  - `/api/rekap/progres`
  - `/api/rekap/per-pengrajin`
- Staffing filters: `GET /api/staffing?no_po=&pengrajin_id=&barang_id=&date_from=&date_to=`
- Exports staffing/BM (accept same filters): `/api/export/staffing/pdf` `/excel` · `/api/export/barang-masuk/pdf` `/excel`
- **Dashboard Kinerja Pengrajin**: `GET /api/dashboard/kinerja-pengrajin?month=YYYY-MM`
- Activity Log: `GET /api/activity-log` (admin + owner)

## Testing Status
- iter18: 34/34 ✅ · iter19: 38/38 ✅ · iter20: 21/21 ✅ · iter21: 18/18 ✅

## Backlog / Roadmap
- **P1** Split `server.py` (~2790 lines) → `/routes/` + `/models/`
- **P2** S3/Cloudinary uploads (ephemeral pod)
- **P2** Dashboard notif "PO ready-to-ship" · Auto-gen No PO/SPK
- **P3** Refactor shared progres validation helper · Radix Dialog a11y
