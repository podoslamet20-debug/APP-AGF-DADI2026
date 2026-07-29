# AGFDATA - Furniture Data Management System

## Problem Statement
Full-stack furniture management (Indonesian). Menus: Database Barang, Pengrajin, PO, Barang Masuk, Staffing, SPK, Progres Barang, Rekap Data, User Management, Activity Log.

Roles: **Admin** (full CRUD) · **Staff** (view + edit BM/Staffing/Progres, no prices) · **Guest** (view-only, no prices/pengrajin) · **Owner** (view-all incl. prices & activity log, NO edit).

Pipeline: PO → SPK (per pengrajin) → Barang Masuk (per pengrajin) → Progres (per pengrajin, 4 stages) → Staffing (aggregate).

## Tech Stack
React + Tailwind + Shadcn UI · FastAPI + Motor MongoDB · JWT auth · ReportLab (PDF) · OpenPyXL/XlsxWriter (Excel)

## Changelog

### Feb 2026 — Iter 20 (current)
- **SPK single-pengrajin per item (cross-SPK validation)** — Removed strict per-SPK allocation. Now each SPK item = (barang, pengrajin, qty). Cumulative SPK qty across ALL SPKs for (no_po, barang_id) must ≤ PO qty. Example: PO qty=400 → SPK001 Kemat 300 + SPK002 Roni 50 + SPK003 Marten 50 = OK.
- **Rekap Data filter panel** (tab Rekap PO): No PO, Barang, Pengrajin, Date From/To.
- **Staffing filter panel**: No PO, Barang, Pengrajin, Date From/To + search.
- **Export Staffing PDF/Excel accepts filter query params**.
- New endpoint: `GET /api/spk/allocations?no_po=&barang_id=` returns aggregated pengrajin allocations.

### Feb 2026 — Iter 18-19
- Owner role added (view-all, no edit). Sees prices + activity log.
- Pengrajin menu independent CRUD (nama, telepon, alamat, rekening, catatan).
- Barang Masuk & Progres per-pengrajin validation.
- Legacy `allocations[]` still readable (backward compat).

## Test Credentials
See `/app/memory/test_credentials.md`. Admin/Staff/Guest/Owner all seeded.

## Key API Endpoints
- Auth: `POST /api/auth/login` · `GET /api/auth/me` · `POST /api/auth/logout`
- Pengrajin: `GET/POST /api/pengrajin` · `PUT/DELETE /api/pengrajin/{id}`
- SPK: `POST/PUT /api/spk` (single-pengrajin per item, cross-SPK ≤ PO qty)
- SPK alloc lookup: `GET /api/spk/allocations?no_po=&barang_id=`
- Rekap (with filters): `GET /api/rekap/all-po?no_po=&barang_id=&pengrajin_id=&date_from=&date_to=`
- Staffing (with filters): `GET /api/staffing?no_po=&pengrajin_id=&barang_id=&date_from=&date_to=`
- Export staffing (with filters): `GET /api/export/staffing/pdf` and `/excel` accept same filter params
- Activity Log: `GET /api/activity-log` (admin + owner)

## Testing Status
- iter18: 34/34 backend + 9/9 frontend ✅
- iter19: 38/38 backend + 3/3 frontend ✅
- iter20: 21/21 new + 32/33 legacy retained (6 old allocations-strict tests skipped by design) + 3/3 frontend ✅

## Backlog / Roadmap
- **P1** Split `server.py` (2674 lines) → `/app/backend/routes/` + `/models/`
- **P2** S3/Cloudinary for uploads (ephemeral pod)
- **P2** Dashboard notif "PO ready-to-ship"
- **P2** Auto-gen No PO / No SPK
- **P2** Dashboard "Kinerja Pengrajin" (qty selesai + on-time rate ranking)
- **P3** Refactor shared progres validation helper (POST/PUT dup)
- **P3** Radix Dialog a11y (DialogDescription) — minor console warnings
