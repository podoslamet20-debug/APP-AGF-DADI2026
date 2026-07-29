# AGFDATA - Furniture Data Management System

## Problem Statement
Full-stack furniture management app (Indonesian language). Menus: Database Barang, Pengrajin (Craftsman), PO (Purchase Order), Barang Masuk (Incoming), Staffing (Outgoing), SPK (Work Order), Progres Barang (Progress Tracking), Rekap Data (Summary), User Management, Activity Log.

Roles:
- **Admin** — full CRUD across all menus
- **Staff** — view all + edit Barang Masuk, Staffing, Progres (no prices)
- **Guest (Tamu)** — view-only, no prices, no pengrajin visibility
- **Owner** — view-all (including prices, activity log), NO edit

Pipeline: PO → SPK allocations (per pengrajin) → Barang Masuk (per pengrajin) → Progres (per pengrajin, 4 stages: grinda/servis/finishing/packing) → Staffing (aggregate).

## Tech Stack
React + Tailwind + Shadcn UI · FastAPI + Motor MongoDB · JWT auth · ReportLab (PDF) · OpenPyXL (Excel)

## Recent Changes (Feb 2026 — this iteration)
- **Owner role** added (view-all, no edit). Sees prices + activity log. Cannot access User Management.
- **Pengrajin menu** independent CRUD (nama, telepon, alamat, rekening, catatan). Removed pengrajin fields from Database Barang.
- **Multi-pengrajin SPK allocations**: SPK items now have `allocations = [{pengrajin_id, pengrajin_nama, qty}]`. Sum(qty) must equal item.qty. Mandatory.
- **Per-pengrajin Barang Masuk**: PO items are split into rows per SPK allocation. Validation: qty_diterima ≤ (allocation - already received) per (barang, pengrajin).
- **Per-pengrajin Progres**: pipeline validation per (po, barang, pengrajin) — grinda ≤ BM for that pengrajin, servis ≤ grinda for that pengrajin, etc.
- Backward compat: legacy data without allocations still validates via PO-level fallback.

## Test Credentials
See `/app/memory/test_credentials.md`. Admin/Staff/Guest/Owner all seeded.

## Key API Endpoints
- Auth: POST /api/auth/login · GET /api/auth/me · POST /api/auth/logout
- Pengrajin: GET/POST /api/pengrajin · PUT/DELETE /api/pengrajin/{id}
- SPK (allocations): POST/PUT /api/spk · GET /api/spk
- Barang Masuk (per-pengrajin): POST/PUT /api/barang-masuk (items have pengrajin_id)
- Progres (per-pengrajin): POST/PUT /api/progres (entry has pengrajin_id)
- Activity Log: GET /api/activity-log (admin + owner)

## Testing Status
- iter18: 34/34 backend + 9/9 frontend smoke ✅
- iter19: 38/38 backend + 3/3 frontend (fixes verified) ✅

## Backlog / Roadmap
- **P1** Refactor `server.py` (2447 lines) → `/app/backend/routes/` + `/models/`
- **P1** Advanced filters on Rekap & Staffing (PO, tanggal, pengrajin, barang) + updated exports
- **P2** S3/Cloudinary for uploads (ephemeral pod issue)
- **P2** Dashboard notif "PO ready-to-ship"
- **P2** Auto-gen No PO / No SPK
- **P3** Refactor shared progres validation helper (POST/PUT duplication)
- **P3** Radix Dialog a11y (DialogDescription) — minor console warnings

## File Map
- `/app/backend/server.py` — monolithic FastAPI (2447 lines)
- `/app/frontend/src/pages/Pengrajin.jsx` (new)
- `/app/frontend/src/pages/SPKPage.jsx` (rewrote for allocations)
- `/app/frontend/src/pages/BarangMasuk.jsx` (rewrote for per-pengrajin rows)
- `/app/frontend/src/pages/ProgresBarang.jsx` (added pengrajin selector)
- `/app/frontend/src/pages/DatabaseBarang.jsx` (pengrajin fields removed)
- `/app/frontend/src/contexts/AuthContext.js` (owner role helpers)
- `/app/frontend/src/layouts/DashboardLayout.jsx` (Pengrajin nav + owner)
