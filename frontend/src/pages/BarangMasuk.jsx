import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Plus, PackageOpen, Download, Package, Search, Trash2, Edit, Eye, Printer, CheckCircle2 } from "lucide-react";

export default function BarangMasuk() {
  const { API, canEditPartial, canSeeCraftsman } = useAuth();
  const [items, setItems] = useState([]);
  const [pos, setPos] = useState([]);
  const [spks, setSpks] = useState([]);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [preview, setPreview] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedPO, setSelectedPO] = useState(null);
  const [form, setForm] = useState({ po_id: "", tanggal_masuk: "", penerima: "", items: [] });

  const load = async () => {
    try {
      const [bmRes, poRes, spkRes] = await Promise.all([
        axios.get(`${API}/barang-masuk`),
        axios.get(`${API}/po`),
        axios.get(`${API}/spk`),
      ]);
      let bmData = bmRes.data;
      if (search) {
        const s = search.toLowerCase();
        bmData = bmData.filter(bm =>
          bm.no_po?.toLowerCase().includes(s) ||
          bm.penerima?.toLowerCase().includes(s) ||
          bm.items?.some(i => (i.nama_barang || "").toLowerCase().includes(s) || (i.nama_pengrajin || "").toLowerCase().includes(s))
        );
      }
      setItems(bmData);
      setPos(poRes.data);
      setSpks(spkRes.data);
    } catch (e) { console.error(e); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [search]);

  // Build rows from PO items: aggregate all SPK lines per (barang, pengrajin)
  const buildRowsFromPO = (po, existingBmMap = new Map()) => {
    const rows = [];
    const poSpks = spks.filter(s => s.items?.some(si => si.no_po === po.no_po));
    for (const poItem of po.items || []) {
      // Aggregate SPK qty per pengrajin_id for this PO+barang
      const allocMap = new Map();  // pengrajin_id -> {pengrajin_nama, alloc_qty}
      for (const spk of poSpks) {
        for (const si of spk.items || []) {
          if (si.no_po !== po.no_po || si.barang_id !== poItem.barang_id) continue;
          // New schema
          if (si.pengrajin_id) {
            const cur = allocMap.get(si.pengrajin_id) || { pengrajin_nama: si.pengrajin_nama || si.nama_pengrajin || "", alloc_qty: 0 };
            cur.alloc_qty += parseInt(si.qty) || 0;
            allocMap.set(si.pengrajin_id, cur);
          } else {
            // Legacy allocations[]
            for (const a of si.allocations || []) {
              if (!a.pengrajin_id) continue;
              const cur = allocMap.get(a.pengrajin_id) || { pengrajin_nama: a.pengrajin_nama || "", alloc_qty: 0 };
              cur.alloc_qty += parseInt(a.qty) || 0;
              allocMap.set(a.pengrajin_id, cur);
            }
          }
        }
      }
      const allocs = [...allocMap.entries()].map(([pid, v]) => ({ pengrajin_id: pid, pengrajin_nama: v.pengrajin_nama, alloc_qty: v.alloc_qty }));
      if (allocs.length === 0) {
        // No SPK allocation: create a single "unassigned" row (legacy)
        rows.push({
          barang_id: poItem.barang_id,
          pengrajin_id: "",
          pengrajin_nama: poItem.nama_pengrajin || "",
          nama_barang: poItem.nama_barang,
          spesifikasi: poItem.spesifikasi,
          gambar_path: poItem.gambar_path,
          alloc_qty: poItem.qty,
          _po_qty: poItem.qty,
          qty_diterima: 0,
          _selected: false,
          _no_alloc: true,
        });
      } else {
        for (const a of allocs) {
          const existing = existingBmMap.get(`${poItem.barang_id}__${a.pengrajin_id}`);
          rows.push({
            barang_id: poItem.barang_id,
            pengrajin_id: a.pengrajin_id,
            pengrajin_nama: a.pengrajin_nama,
            nama_barang: poItem.nama_barang,
            spesifikasi: poItem.spesifikasi,
            gambar_path: poItem.gambar_path,
            alloc_qty: a.alloc_qty,
            _po_qty: poItem.qty,
            qty_diterima: existing?.qty_diterima || 0,
            _selected: !!existing,
            _existing_qty: existing?.qty_diterima || 0,
          });
        }
      }
    }
    return rows;
  };

  // Aggregate qty received per (barang_id, pengrajin_id) across ALL BM for a PO (exclude current editingId)
  const computeReceivedMap = (poId, excludeBmId) => {
    const map = new Map();
    for (const bm of items) {
      if (bm.po_id !== poId) continue;
      if (excludeBmId && bm._id === excludeBmId) continue;
      for (const it of bm.items || []) {
        const k = `${it.barang_id}__${it.pengrajin_id || ""}`;
        map.set(k, (map.get(k) || 0) + (it.qty_diterima || 0));
      }
    }
    return map;
  };

  const selectPO = (poId) => {
    const po = pos.find(p => (p._id || p.id) === poId);
    if (!po) return;
    setSelectedPO(po);
    const rows = buildRowsFromPO(po);
    // Compute sudah diterima per (barang, pengrajin) across other BM
    const receivedMap = computeReceivedMap(poId);
    rows.forEach(r => {
      const k = `${r.barang_id}__${r.pengrajin_id || ""}`;
      r._already_received = receivedMap.get(k) || 0;
    });
    setForm({ ...form, po_id: poId, items: rows });
  };

  const toggleItem = (idx) => {
    const rows = [...form.items];
    rows[idx]._selected = !rows[idx]._selected;
    if (!rows[idx]._selected) rows[idx].qty_diterima = 0;
    setForm({ ...form, items: rows });
  };

  const updateQty = (idx, qty) => {
    const rows = [...form.items];
    const r = rows[idx];
    const maxQty = (r.alloc_qty || 0) - (r._already_received || 0);
    const clamped = Math.min(Math.max(parseInt(qty) || 0, 0), maxQty);
    r.qty_diterima = clamped;
    setForm({ ...form, items: rows });
  };

  const submit = async () => {
    if (!form.po_id || !form.tanggal_masuk || !form.penerima) {
      toast.error("Isi semua field wajib");
      return;
    }
    const filtered = form.items.filter(r => r._selected && (r.qty_diterima || 0) > 0);
    if (filtered.length === 0) { toast.error("Pilih minimal 1 baris dengan qty > 0"); return; }
    // Server payload
    const payload = {
      po_id: form.po_id,
      tanggal_masuk: form.tanggal_masuk,
      penerima: form.penerima,
      items: filtered.map(r => ({
        barang_id: r.barang_id,
        pengrajin_id: r.pengrajin_id || undefined,
        pengrajin_nama: r.pengrajin_nama || undefined,
        qty_diterima: r.qty_diterima,
      })),
    };
    try {
      if (editingId) {
        await axios.put(`${API}/barang-masuk/${editingId}`, payload);
        toast.success("Barang masuk diupdate");
      } else {
        await axios.post(`${API}/barang-masuk`, payload);
        toast.success("Barang masuk dicatat");
      }
      setOpen(false); setEditingId(null);
      setForm({ po_id: "", tanggal_masuk: "", penerima: "", items: [] });
      setSelectedPO(null);
      load();
    } catch (e) {
      toast.error("Gagal: " + (e.response?.data?.detail || ""));
    }
  };

  const startEdit = (bm) => {
    const po = pos.find(p => (p._id || p.id) === bm.po_id);
    if (!po) return;
    // Map own BM items keyed by (barang, pengrajin) so we can prefill qty
    const ownMap = new Map();
    for (const it of bm.items || []) {
      ownMap.set(`${it.barang_id}__${it.pengrajin_id || ""}`, it);
    }
    const rows = buildRowsFromPO(po, ownMap);
    const receivedMap = computeReceivedMap(bm.po_id, bm._id); // exclude self
    rows.forEach(r => {
      const k = `${r.barang_id}__${r.pengrajin_id || ""}`;
      r._already_received = receivedMap.get(k) || 0;
    });
    setForm({ po_id: bm.po_id, tanggal_masuk: bm.tanggal_masuk, penerima: bm.penerima, items: rows });
    setEditingId(bm._id);
    setSelectedPO(po);
    setOpen(true);
  };

  const deleteBm = async (id) => {
    try {
      await axios.delete(`${API}/barang-masuk/${id}`);
      toast.success("Barang masuk dihapus");
      load();
    } catch (e) { toast.error("Gagal hapus"); }
  };

  const downloadPDF = (id) => window.open(`${API}/export/barang-masuk/${id}/pdf`, '_blank');
  const downloadAllPDF = () => {
    const url = search ? `${API}/export/barang-masuk/pdf?search=${encodeURIComponent(search)}` : `${API}/export/barang-masuk/pdf`;
    window.open(url, '_blank');
  };
  const downloadExcel = () => {
    const url = search ? `${API}/export/barang-masuk/excel?search=${encodeURIComponent(search)}` : `${API}/export/barang-masuk/excel`;
    window.open(url, '_blank');
  };
  const printPage = () => window.print();

  return (
    <div className="space-y-6" data-testid="barang-masuk-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Barang Masuk</h1>
          <p className="text-[#5C5C5C] mt-1">Terima barang per pengrajin sesuai alokasi SPK</p>
        </div>
        <div className="flex gap-2 flex-wrap print:hidden">
          <Button variant="outline" onClick={downloadAllPDF} data-testid="export-pdf-bm"><Download className="w-4 h-4 mr-2" /> PDF</Button>
          <Button variant="outline" onClick={downloadExcel} data-testid="export-excel-bm"><Download className="w-4 h-4 mr-2" /> Excel</Button>
          <Button variant="outline" onClick={printPage} data-testid="print-bm"><Printer className="w-4 h-4 mr-2" /> Print</Button>
          {canEditPartial && (
            <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditingId(null); setForm({ po_id: "", tanggal_masuk: "", penerima: "", items: [] }); setSelectedPO(null); }}}>
              <DialogTrigger asChild>
                <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-bm-button"><Plus className="w-4 h-4 mr-2" /> Catat Masuk</Button>
              </DialogTrigger>
              <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>{editingId ? "Edit Barang Masuk" : "Catat Barang Masuk"}</DialogTitle>
                  <DialogDescription>Pilih PO — daftar barang otomatis dipecah per pengrajin sesuai alokasi SPK.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label>Pilih PO</Label>
                    <Select value={form.po_id} onValueChange={selectPO}>
                      <SelectTrigger data-testid="select-po-bm"><SelectValue placeholder="Pilih PO" /></SelectTrigger>
                      <SelectContent>
                        {pos.map((p, i) => <SelectItem key={i} value={p._id || `${i}`}>{p.no_po}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label>Tanggal Masuk</Label>
                      <Input type="date" data-testid="input-tanggal-masuk" value={form.tanggal_masuk} onChange={(e) => setForm({ ...form, tanggal_masuk: e.target.value })} />
                    </div>
                    <div>
                      <Label>Penerima</Label>
                      <Input data-testid="input-penerima" value={form.penerima} onChange={(e) => setForm({ ...form, penerima: e.target.value })} />
                    </div>
                  </div>
                  {selectedPO && (
                    <div>
                      <Label>Pilih Baris yang Diterima <span className="text-xs text-[#5C5C5C]">(per barang per pengrajin)</span></Label>
                      <div className="space-y-2 mt-2">
                        {form.items.length === 0 && <p className="text-sm text-[#5C5C5C]">Tidak ada item pada PO ini.</p>}
                        {form.items.map((row, idx) => {
                          const sisa = (row.alloc_qty || 0) - (row._already_received || 0);
                          return (
                            <div key={idx} className={`p-3 rounded-md border flex gap-3 ${row._selected ? 'bg-[#FAFAFA] border-[#E5E5E5]' : 'bg-gray-100 border-gray-200 opacity-70'}`}>
                              <input type="checkbox" checked={row._selected} onChange={() => toggleItem(idx)} data-testid={`bm-select-${idx}`} className="mt-2 w-4 h-4 accent-[#8B5A2B]" disabled={row._no_alloc} />
                              {row.gambar_path && <img src={`${API}/files/${row.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" />}
                              <div className="flex-1">
                                <p className="font-medium text-sm">{row.nama_barang}</p>
                                {row._no_alloc ? (
                                  <p className="text-xs text-[#F44336]">⚠️ Belum ada alokasi SPK — buat SPK dulu untuk mengaktifkan</p>
                                ) : (
                                  <p className="text-xs text-[#5C5C5C]">Pengrajin: <strong>{row.pengrajin_nama}</strong> • Alokasi: {row.alloc_qty} • Sudah diterima: {row._already_received} • <span className="font-semibold text-[#8B5A2B]">Sisa: {sisa}</span></p>
                                )}
                              </div>
                              <div className="w-24">
                                <Label className="text-xs">Qty Terima</Label>
                                <Input type="number" min="0" max={sisa} data-testid={`bm-qty-${idx}`} value={row.qty_diterima} onChange={(e) => updateQty(idx, e.target.value)} disabled={!row._selected || row._no_alloc} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  <Button onClick={submit} className="w-full bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="submit-bm-button">Simpan</Button>
                </div>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>

      <Card className="p-4 border border-[#E5E5E5] print:hidden">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5C5C5C]" />
          <Input placeholder="Cari No PO, Penerima, Nama Barang, atau Pengrajin..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" data-testid="search-bm-input" />
        </div>
      </Card>

      <div className="space-y-4" data-testid="bm-list">
        {items.length === 0 ? (
          <Card className="p-12 text-center border border-dashed border-[#E5E5E5]">
            <PackageOpen className="w-12 h-12 mx-auto text-[#5C5C5C] mb-3" />
            <p className="text-[#5C5C5C]">Belum ada data barang masuk.</p>
          </Card>
        ) : (
          items.map((bm, idx) => {
            const po = pos.find(p => (p._id || p.id) === bm.po_id);
            const poItems = po?.items || [];
            const totalPO = poItems.reduce((s, i) => s + (i.qty || 0), 0);
            const totalDiterima = poItems.reduce((s, i) => s + (i.qty_diterima || 0), 0);
            const poKomplit = totalPO > 0 && totalDiterima >= totalPO;
            return (
              <Card key={idx} className="p-6 border border-[#E5E5E5]" data-testid={`bm-card-${idx}`}>
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-lg font-bold text-[#1A1A1A]">{bm.no_po}</h3>
                      {poKomplit && <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-[#4CAF50] text-white rounded-full" data-testid={`bm-komplit-po-${idx}`}><CheckCircle2 className="w-3 h-3" /> KOMPLIT PO</span>}
                    </div>
                    <p className="text-sm text-[#5C5C5C]">Tanggal: {bm.tanggal_masuk} • Penerima: {bm.penerima}</p>
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <Button variant="outline" size="sm" onClick={() => setPreview(bm)} data-testid={`preview-bm-${idx}`}><Eye className="w-3 h-3 mr-1" /> Preview</Button>
                    {canEditPartial && <Button variant="outline" size="sm" onClick={() => startEdit(bm)} data-testid={`edit-bm-${idx}`}><Edit className="w-3 h-3 mr-1" /> Edit</Button>}
                    {canEditPartial && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="outline" size="sm" className="text-[#F44336]" data-testid={`delete-bm-${idx}`}><Trash2 className="w-3 h-3" /></Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Hapus Barang Masuk?</AlertDialogTitle>
                            <AlertDialogDescription>Data ini akan dihapus dan qty diterima di PO akan dikurangi.</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Batal</AlertDialogCancel>
                            <AlertDialogAction className="bg-[#F44336]" onClick={() => deleteBm(bm._id)}>Hapus</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                    <Button variant="outline" size="sm" onClick={() => downloadPDF(bm._id)} data-testid={`pdf-bm-${idx}`}><Download className="w-3 h-3 mr-1" /> PDF</Button>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {bm.items?.map((item, ii) => (
                    <div key={ii} className="flex gap-3 p-3 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]">
                      {item.gambar_path ? <img src={`${API}/files/${item.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" /> : <div className="w-14 h-14 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-5 h-5 text-[#8B5A2B]" /></div>}
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm truncate">{item.nama_barang}</p>
                        {canSeeCraftsman && (item.pengrajin_nama || item.nama_pengrajin) && <p className="text-xs text-[#5C5C5C] truncate">{item.pengrajin_nama || item.nama_pengrajin}</p>}
                        <span className="text-xs px-1.5 py-0.5 bg-[#4CAF50] text-white rounded inline-block mt-1">Diterima: {item.qty_diterima}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            );
          })
        )}
      </div>

      <Dialog open={!!preview} onOpenChange={() => setPreview(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Detail Barang Masuk</DialogTitle></DialogHeader>
          {preview && (
            <div className="space-y-3">
              <p><strong>No PO:</strong> {preview.no_po}</p>
              <p><strong>Tanggal Masuk:</strong> {preview.tanggal_masuk}</p>
              <p><strong>Penerima:</strong> {preview.penerima}</p>
              {preview.items?.map((item, i) => (
                <div key={i} className="flex gap-3 p-3 border border-[#E5E5E5] rounded-md">
                  {item.gambar_path && <img src={`${API}/files/${item.gambar_path}`} className="w-20 h-20 object-cover rounded" alt="" />}
                  <div className="flex-1">
                    <p className="font-bold">{item.nama_barang}</p>
                    {canSeeCraftsman && (item.pengrajin_nama || item.nama_pengrajin) && <p className="text-sm text-[#5C5C5C]">Pengrajin: {item.pengrajin_nama || item.nama_pengrajin}</p>}
                    <p className="text-sm">Qty Diterima: <strong>{item.qty_diterima}</strong></p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
