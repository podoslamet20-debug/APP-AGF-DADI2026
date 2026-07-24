import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { TrendingUp, Package, CheckCircle2, Download, Printer, Plus, Calendar } from "lucide-react";

export default function ProgresBarang() {
  const { API, canEditPartial, canSeeCraftsman } = useAuth();
  const [progresList, setProgresList] = useState([]);
  const [poList, setPoList] = useState([]);
  const [barangList, setBarangList] = useState([]);
  const [filterPO, setFilterPO] = useState("all");
  const [filterTanggal, setFilterTanggal] = useState("");
  const [open, setOpen] = useState(false);
  const [manual, setManual] = useState(false);
  const [form, setForm] = useState({
    po_id: "",
    item_id: "",
    tanggal: new Date().toISOString().slice(0, 10),
    grinda: 0,
    servis: 0,
    finishing: 0,
    packing: 0,
    // manual-only meta
    nama_barang: "",
    nama_pengrajin: "",
    spesifikasi: "",
    gambar_path: "",
  });

  const load = async () => {
    try {
      const [pr, po, br] = await Promise.all([
        axios.get(`${API}/progres/by-po`),
        axios.get(`${API}/po`),
        axios.get(`${API}/barang`),
      ]);
      setProgresList(pr.data);
      setPoList(po.data);
      setBarangList(br.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, []);

  // Compute qty_masuk for a given po_id + barang_id from progresList (already aggregated)
  const getQtyMasuk = (poId, barangId) => {
    const po = progresList.find(p => p.po_id === poId);
    const it = po?.items.find(i => i.barang_id === barangId);
    return it?.qty_masuk || 0;
  };

  const selectedPO = poList.find(p => (p._id || p.id) === form.po_id);
  const selectedItem = selectedPO?.items.find(i => i.barang_id === form.item_id);
  const currentQtyMasuk = manual ? 0 : getQtyMasuk(form.po_id, form.item_id);
  const maxQty = manual ? Infinity : currentQtyMasuk;

  const updateProgres = async (poId, barangId, key, val, maxQty) => {
    if (!canEditPartial) return;
    const clamped = Math.max(0, parseInt(val) || 0);
    const finalVal = maxQty > 0 ? Math.min(clamped, maxQty) : clamped;
    const po = progresList.find(p => p.po_id === poId);
    const item = po?.items.find(i => i.barang_id === barangId);
    if (!item) return;
    const payload = {
      po_id: poId,
      item_id: barangId,
      grinda: item.grinda,
      servis: item.servis,
      finishing: item.finishing,
      packing: item.packing,
      tanggal: item.tanggal || new Date().toISOString().slice(0, 10),
      [key]: finalVal,
    };
    try {
      await axios.post(`${API}/progres`, payload);
      setProgresList(prev => prev.map(po => po.po_id !== poId ? po : {
        ...po,
        items: po.items.map(it => it.barang_id !== barangId ? it : {
          ...it,
          [key]: finalVal,
          komplit: (key === "packing" ? finalVal : it.packing) >= it.qty_masuk && it.qty_masuk > 0,
        })
      }));
    } catch (e) { toast.error("Gagal update progres"); }
  };

  const submitCreate = async () => {
    if (!form.item_id) {
      toast.error("Pilih atau isi barang terlebih dahulu");
      return;
    }
    if (!manual && !form.po_id) {
      toast.error("Pilih PO terlebih dahulu");
      return;
    }
    const payload = {
      po_id: form.po_id || null,
      item_id: form.item_id,
      tanggal: form.tanggal,
      grinda: parseInt(form.grinda) || 0,
      servis: parseInt(form.servis) || 0,
      finishing: parseInt(form.finishing) || 0,
      packing: parseInt(form.packing) || 0,
    };
    if (manual) {
      payload.nama_barang = form.nama_barang;
      payload.nama_pengrajin = form.nama_pengrajin;
      payload.spesifikasi = form.spesifikasi;
      payload.gambar_path = form.gambar_path;
    }
    try {
      await axios.post(`${API}/progres`, payload);
      toast.success("Progres disimpan");
      setOpen(false);
      setManual(false);
      setForm({ po_id: "", item_id: "", tanggal: new Date().toISOString().slice(0, 10), grinda: 0, servis: 0, finishing: 0, packing: 0, nama_barang: "", nama_pengrajin: "", spesifikasi: "", gambar_path: "" });
      load();
    } catch (e) { toast.error("Gagal simpan progres: " + (e.response?.data?.detail || "")); }
  };

  const onSelectBarangFromPO = (barangId) => {
    const item = selectedPO?.items.find(i => i.barang_id === barangId);
    if (!item) return;
    setForm(f => ({
      ...f,
      item_id: barangId,
      nama_barang: item.nama_barang || "",
      nama_pengrajin: item.nama_pengrajin || "",
      spesifikasi: item.spesifikasi || "",
      gambar_path: item.gambar_path || "",
    }));
  };

  const onSelectBarangManual = (barangId) => {
    const b = barangList.find(bl => (bl._id || bl.id) === barangId);
    setForm(f => ({
      ...f,
      item_id: barangId,
      nama_barang: b?.nama_barang || "",
      nama_pengrajin: b?.nama_pengrajin || "",
      spesifikasi: b?.spesifikasi || "",
      gambar_path: b?.gambar_path || "",
    }));
  };

  const printPDF = () => {
    const url = filterTanggal ? `${API}/export/progres/pdf?tanggal=${filterTanggal}` : `${API}/export/progres/pdf`;
    window.open(url, '_blank');
  };
  const printPage = () => window.print();

  const filtered = progresList.filter(po => filterPO === "all" || po.po_id === filterPO);

  const clampInput = (v) => {
    const n = Math.max(0, parseInt(v) || 0);
    return manual ? n : (maxQty > 0 ? Math.min(n, maxQty) : n);
  };

  return (
    <div className="space-y-6" data-testid="progres-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 print:hidden">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Progres Barang</h1>
          <p className="text-[#5C5C5C] mt-1">Tracking produksi per PO: Grinda → Servis → Finishing → Packing</p>
        </div>
        <div className="flex gap-2 flex-wrap items-end">
          {canEditPartial && (
            <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setManual(false); setForm({ po_id: "", item_id: "", tanggal: new Date().toISOString().slice(0, 10), grinda: 0, servis: 0, finishing: 0, packing: 0, nama_barang: "", nama_pengrajin: "", spesifikasi: "", gambar_path: "" }); } }}>
              <DialogTrigger asChild>
                <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-progres-button"><Plus className="w-4 h-4 mr-2" /> Tambah Progres</Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle>Tambah / Update Progres Barang</DialogTitle></DialogHeader>
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Button type="button" size="sm" variant={manual ? "outline" : "default"} onClick={() => setManual(false)} data-testid="progres-source-po" className={manual ? "" : "bg-[#8B5A2B] hover:bg-[#7A4E24] text-white"}>Dari PO</Button>
                    <Button type="button" size="sm" variant={manual ? "default" : "outline"} onClick={() => setManual(true)} data-testid="progres-source-manual" className={manual ? "bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" : ""}>Manual</Button>
                  </div>

                  {!manual ? (
                    <>
                      <div>
                        <Label>Pilih PO</Label>
                        <Select value={form.po_id} onValueChange={(v) => setForm({ ...form, po_id: v, item_id: "" })}>
                          <SelectTrigger data-testid="progres-select-po"><SelectValue placeholder="Pilih PO" /></SelectTrigger>
                          <SelectContent>
                            {poList.map((p, i) => <SelectItem key={i} value={p._id || p.id || `${i}`}>{p.no_po}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Pilih Barang dari PO</Label>
                        <Select value={form.item_id} onValueChange={onSelectBarangFromPO} disabled={!form.po_id}>
                          <SelectTrigger data-testid="progres-select-barang-po"><SelectValue placeholder={form.po_id ? "Pilih barang" : "Pilih PO dulu"} /></SelectTrigger>
                          <SelectContent>
                            {(selectedPO?.items || []).map((it, i) => <SelectItem key={i} value={it.barang_id}>{it.nama_barang}</SelectItem>)}
                          </SelectContent>
                        </Select>
                        {selectedItem && (
                          <p className="text-xs text-[#5C5C5C] mt-1">Qty Barang Masuk (max input): <strong className="text-[#8B5A2B]">{currentQtyMasuk}</strong>{currentQtyMasuk === 0 && <span className="text-[#F44336]"> — belum ada barang masuk untuk item ini</span>}</p>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <Label>Pilih Barang (Database)</Label>
                        <Select value={form.item_id} onValueChange={onSelectBarangManual}>
                          <SelectTrigger data-testid="progres-select-barang-manual"><SelectValue placeholder="Pilih barang" /></SelectTrigger>
                          <SelectContent>
                            {barangList.map((b, i) => <SelectItem key={i} value={b._id || b.id || `${i}`}>{b.nama_barang}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <div>
                          <Label className="text-xs">Nama Barang (opsional override)</Label>
                          <Input value={form.nama_barang} onChange={(e) => setForm({ ...form, nama_barang: e.target.value })} data-testid="progres-manual-nama" />
                        </div>
                        <div>
                          <Label className="text-xs">Nama Pengrajin</Label>
                          <Input value={form.nama_pengrajin} onChange={(e) => setForm({ ...form, nama_pengrajin: e.target.value })} data-testid="progres-manual-pengrajin" />
                        </div>
                      </div>
                      <p className="text-xs text-[#F44336]">Mode manual: qty tidak dibatasi barang masuk. Input dengan hati-hati.</p>
                    </>
                  )}

                  <div>
                    <Label><Calendar className="w-3 h-3 inline mr-1" /> Tanggal Progres</Label>
                    <Input type="date" value={form.tanggal} onChange={(e) => setForm({ ...form, tanggal: e.target.value })} data-testid="progres-tanggal-input" />
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      { key: "grinda", label: "Grinda", color: "#FFC107" },
                      { key: "servis", label: "Servis", color: "#2196F3" },
                      { key: "finishing", label: "Finishing", color: "#9C27B0" },
                      { key: "packing", label: "Packing/Ready", color: "#4CAF50" },
                    ].map((s) => (
                      <div key={s.key} className="p-3 border border-[#E5E5E5] rounded-md">
                        <Label className="text-xs" style={{ color: s.color }}>{s.label}</Label>
                        <Input
                          type="number"
                          min={0}
                          max={manual ? undefined : maxQty || undefined}
                          value={form[s.key]}
                          onChange={(e) => setForm({ ...form, [s.key]: clampInput(e.target.value) })}
                          data-testid={`progres-form-${s.key}`}
                          className="mt-1"
                        />
                      </div>
                    ))}
                  </div>
                  {!manual && maxQty > 0 && (
                    <p className="text-xs text-[#5C5C5C]">Semua qty dibatasi maksimum <strong>{maxQty}</strong> (dari Barang Masuk).</p>
                  )}
                  <Button onClick={submitCreate} className="w-full bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="submit-progres-button">Simpan Progres</Button>
                </div>
              </DialogContent>
            </Dialog>
          )}
          <div>
            <Label className="text-xs">Filter PO</Label>
            <Select value={filterPO} onValueChange={setFilterPO}>
              <SelectTrigger className="w-40" data-testid="filter-po-progres"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua PO</SelectItem>
                {progresList.map((p, i) => <SelectItem key={i} value={p.po_id}>{p.no_po}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Filter Tanggal PDF</Label>
            <Input type="date" value={filterTanggal} onChange={(e) => setFilterTanggal(e.target.value)} className="w-40" data-testid="filter-tanggal-progres" />
          </div>
          <Button variant="outline" onClick={printPDF} data-testid="print-progres-pdf"><Download className="w-4 h-4 mr-2" /> PDF</Button>
          <Button variant="outline" onClick={printPage} data-testid="print-progres-page"><Printer className="w-4 h-4 mr-2" /> Print</Button>
        </div>
      </div>

      <div className="hidden print:block print-header mb-4">
        <h1 className="text-2xl font-bold">AGFDATA - Rekap Progres Barang</h1>
        <p className="text-sm">Filter: {filterPO === "all" ? "Semua PO" : filtered[0]?.no_po}</p>
      </div>

      <div className="space-y-6" data-testid="progres-list">
        {filtered.length === 0 ? (
          <Card className="p-12 text-center border border-dashed border-[#E5E5E5] print:hidden">
            <TrendingUp className="w-12 h-12 mx-auto text-[#5C5C5C] mb-3" />
            <p className="text-[#5C5C5C]">Belum ada barang masuk untuk ditrack.</p>
          </Card>
        ) : (
          filtered.map((po, poIdx) => (
            <Card key={poIdx} className="p-6 border border-[#E5E5E5]" data-testid={`progres-po-${poIdx}`}>
              <div className="mb-4 pb-3 border-b border-[#E5E5E5]">
                <h2 className="text-xl font-bold text-[#8B5A2B]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>PO: {po.no_po}</h2>
                <p className="text-xs text-[#5C5C5C]">{po.items.length} jenis barang</p>
              </div>
              <div className="space-y-4">
                {po.items.map((item, idx) => (
                  <div key={idx} className="p-4 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]" data-testid={`progres-item-${poIdx}-${idx}`}>
                    <div className="flex flex-col md:flex-row gap-4 mb-3">
                      {item.gambar_path ? <img src={`${API}/files/${item.gambar_path}`} className="w-full md:w-24 h-24 object-cover rounded" alt="" /> : <div className="w-full md:w-24 h-24 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-8 h-8 text-[#8B5A2B]" /></div>}
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <h3 className="text-lg font-bold text-[#1A1A1A]">{item.nama_barang}</h3>
                          {item.komplit && <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-[#4CAF50] text-white rounded-full"><CheckCircle2 className="w-3 h-3" /> KOMPLIT</span>}
                          {item.tanggal && <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-[#F0E6D6] text-[#8B5A2B] rounded-full"><Calendar className="w-3 h-3" /> {item.tanggal}</span>}
                        </div>
                        {canSeeCraftsman && <p className="text-sm text-[#5C5C5C]">Pengrajin: {item.nama_pengrajin}</p>}
                        <p className="text-sm text-[#5C5C5C]">{item.spesifikasi}</p>
                        <p className="text-sm mt-1">Qty Barang Masuk: <strong className="text-[#8B5A2B]">{item.qty_masuk}</strong></p>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {[
                        { key: "grinda", label: "Grinda", color: "#FFC107" },
                        { key: "servis", label: "Servis", color: "#2196F3" },
                        { key: "finishing", label: "Finishing", color: "#9C27B0" },
                        { key: "packing", label: `Packing/Ready (max ${item.qty_masuk})`, color: "#4CAF50" },
                      ].map((stage) => (
                        <div key={stage.key} className="p-3 border border-[#E5E5E5] rounded-md bg-white">
                          <Label className="text-xs" style={{ color: stage.color }}>{stage.label}</Label>
                          <Input
                            type="number"
                            min={0}
                            max={item.qty_masuk}
                            data-testid={`progres-${stage.key}-${poIdx}-${idx}`}
                            value={item[stage.key] || 0}
                            onChange={(e) => updateProgres(po.po_id, item.barang_id, stage.key, e.target.value, item.qty_masuk)}
                            disabled={!canEditPartial}
                            className="mt-1"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
