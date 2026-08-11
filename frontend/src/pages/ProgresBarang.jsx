import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { TrendingUp, Package, CheckCircle2, Download, Printer, Plus, Calendar, History } from "lucide-react";

const STAGES = [
  { key: "grinda", label: "Grinda", color: "#FFC107", prev: null, prevLabel: "Barang Masuk" },
  { key: "servis", label: "Servis", color: "#2196F3", prev: "grinda", prevLabel: "Grinda" },
  { key: "finishing", label: "Finishing", color: "#9C27B0", prev: "servis", prevLabel: "Servis" },
  { key: "packing", label: "Packing / Ready", color: "#4CAF50", prev: "finishing", prevLabel: "Finishing" },
];

export default function ProgresBarang() {
  const { API, canEdit, canEditPartial, canSeeCraftsman } = useAuth();
  const [progresList, setProgresList] = useState([]);
  const [poList, setPoList] = useState([]);
  const [barangList, setBarangList] = useState([]);
  const [spks, setSpks] = useState([]);
  const [filterPO, setFilterPO] = useState("all");
  const [filterTanggal, setFilterTanggal] = useState("");
  const [open, setOpen] = useState(false);
  const [manual, setManual] = useState(false);
  const [historyMap, setHistoryMap] = useState({});
  const [historyOpen, setHistoryOpen] = useState({});
  const [editEntryId, setEditEntryId] = useState(null);
  const initialForm = {
    po_id: "",
    item_id: "",
    stage: "grinda",
    qty: 0,
    tanggal: new Date().toISOString().slice(0, 10),
    pengrajin_id: "",
    pengrajin_nama: "",
    nama_barang: "",
    nama_pengrajin: "",
    spesifikasi: "",
    gambar_path: "",
    catatan_finishing_1: "",
    catatan_finishing_2: "",
    catatan_finishing_3: "",
    catatan_finishing_4: "",
    catatan_finishing_5: "",
  };
  const [form, setForm] = useState(initialForm);
  const [errorMsg, setErrorMsg] = useState("");

  const load = async () => {
    try {
      const [pr, po, br, spkRes] = await Promise.all([
        axios.get(`${API}/progres/by-po`),
        axios.get(`${API}/po`),
        axios.get(`${API}/barang`),
        axios.get(`${API}/spk`),
      ]);
      setProgresList(pr.data);
      setPoList(po.data);
      setBarangList(br.data);
      setSpks(spkRes.data);
    } catch (e) { console.error(e); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const loadHistory = async (poId, itemId) => {
    const k = `${poId}_${itemId}`;
    try {
      const { data } = await axios.get(`${API}/progres/entries`, { params: { po_id: poId, item_id: itemId } });
      setHistoryMap(prev => ({ ...prev, [k]: data }));
    } catch (e) { console.error(e); }
  };

  const toggleHistory = (poId, itemId) => {
    const k = `${poId}_${itemId}`;
    const willOpen = !historyOpen[k];
    setHistoryOpen(prev => ({ ...prev, [k]: willOpen }));
    if (willOpen && !historyMap[k]) loadHistory(poId, itemId);
  };

  // Selected item from progresList (has aggregate sums + sisa)
  const selectedProgres = progresList.find(p => p.po_id === form.po_id)?.items.find(i => i.barang_id === form.item_id);
  const selectedPO = poList.find(p => (p._id || p.id) === form.po_id);

  // Get aggregated pengrajin allocations for currently selected PO+barang
  const currentAllocations = (() => {
    if (!form.po_id || !form.item_id || !selectedPO) return [];
    const poSpks = spks.filter(s => s.items?.some(si => si.no_po === selectedPO.no_po));
    const map = new Map();  // pengrajin_id -> {pengrajin_id, pengrajin_nama, qty}
    for (const spk of poSpks) {
      for (const si of spk.items || []) {
        if (si.no_po !== selectedPO.no_po || si.barang_id !== form.item_id) continue;
        if (si.pengrajin_id) {
          const cur = map.get(si.pengrajin_id) || { pengrajin_id: si.pengrajin_id, pengrajin_nama: si.pengrajin_nama || si.nama_pengrajin || "", qty: 0 };
          cur.qty += parseInt(si.qty) || 0;
          map.set(si.pengrajin_id, cur);
        } else {
          for (const a of si.allocations || []) {
            if (!a.pengrajin_id) continue;
            const cur = map.get(a.pengrajin_id) || { pengrajin_id: a.pengrajin_id, pengrajin_nama: a.pengrajin_nama || "", qty: 0 };
            cur.qty += parseInt(a.qty) || 0;
            map.set(a.pengrajin_id, cur);
          }
        }
      }
    }
    return [...map.values()];
  })();

  // Compute upstream/max for the current form.stage
  const getStageContext = () => {
    if (manual) return { max: Infinity, upstreamLabel: "—", upstreamQty: null, sisa: null };
    if (!selectedProgres) return { max: 0, upstreamLabel: "Barang Masuk", upstreamQty: 0, sisa: 0 };
    const stage = form.stage;
    const s = selectedProgres;
    const upstreamQty = stage === "grinda" ? s.qty_masuk : (s[STAGES.find(x => x.key === stage).prev] || 0);
    const alreadyAt = s[stage] || 0;
    const sisa = Math.max(0, upstreamQty - alreadyAt);
    const upstreamLabel = STAGES.find(x => x.key === stage).prevLabel;
    return { max: sisa, upstreamLabel, upstreamQty, sisa, alreadyAt };
  };
  const ctx = getStageContext();

  const submitCreate = async () => {
    if (!form.item_id) return toast.error("Pilih atau isi barang");
    if (!manual && !form.po_id) return toast.error("Pilih PO terlebih dahulu");
    if (!form.qty || form.qty <= 0) return toast.error("Qty harus lebih besar dari 0");
    setErrorMsg("");
    const payload = {
      po_id: form.po_id || null,
      item_id: form.item_id,
      stage: form.stage,
      qty: parseInt(form.qty),
      tanggal: form.tanggal,
    };
    if (manual) {
      payload.nama_barang = form.nama_barang;
      payload.nama_pengrajin = form.nama_pengrajin;
      payload.spesifikasi = form.spesifikasi;
      payload.gambar_path = form.gambar_path;
    }
    if (form.stage === "finishing") {
      payload.catatan_finishing_1 = form.catatan_finishing_1;
      payload.catatan_finishing_2 = form.catatan_finishing_2;
      payload.catatan_finishing_3 = form.catatan_finishing_3;
      payload.catatan_finishing_4 = form.catatan_finishing_4;
      payload.catatan_finishing_5 = form.catatan_finishing_5;
    }
    try {
      const url = editEntryId ? `${API}/progres/${editEntryId}` : `${API}/progres`;
      const method = editEntryId ? 'put' : 'post';
      const { data } = await axios[method](url, payload);
      const sisa = data.sisa_setelah_input;
      toast.success(sisa != null ? `Entry ${form.stage} ${editEntryId ? 'diupdate' : '+' + form.qty + ' disimpan'}. Sisa: ${sisa}` : `Entry ${editEntryId ? 'diupdate' : 'disimpan'}.`);
      setOpen(false);
      setManual(false);
      setEditEntryId(null);
      setForm(initialForm);
      setHistoryMap({});
      load();
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      if (e.response?.status === 400) {
        setErrorMsg(`⚠️ ${detail}`);
      }
      toast.error("Gagal simpan: " + detail);
    }
  };

  const startEditEntry = (entry) => {
    setEditEntryId(entry._id);
    setManual(!entry.po_id);
    setForm({
      po_id: entry.po_id || "",
      item_id: entry.item_id,
      stage: entry.stage,
      qty: entry.qty,
      tanggal: entry.tanggal || new Date().toISOString().slice(0, 10),
      pengrajin_id: entry.pengrajin_id || "",
      pengrajin_nama: entry.pengrajin_nama || "",
      nama_barang: entry.nama_barang || "",
      nama_pengrajin: entry.nama_pengrajin || "",
      spesifikasi: entry.spesifikasi || "",
      gambar_path: entry.gambar_path || "",
      catatan_finishing_1: entry.catatan_finishing_1 || "",
      catatan_finishing_2: entry.catatan_finishing_2 || "",
      catatan_finishing_3: entry.catatan_finishing_3 || "",
      catatan_finishing_4: entry.catatan_finishing_4 || "",
      catatan_finishing_5: entry.catatan_finishing_5 || "",
    });
    setErrorMsg("");
    setOpen(true);
  };

  const deleteEntry = async (entryId, poId, itemId) => {
    if (!window.confirm("Hapus entry ini?")) return;
    try {
      await axios.delete(`${API}/progres/${entryId}`);
      toast.success("Entry dihapus");
      const k = `${poId}_${itemId}`;
      setHistoryMap(prev => ({ ...prev, [k]: undefined }));
      if (historyOpen[k]) loadHistory(poId, itemId);
      load();
    } catch (e) { toast.error("Gagal hapus: " + (e.response?.data?.detail || "")); }
  };

  const onSelectBarangFromPO = (barangId) => {
    const item = selectedPO?.items.find(i => i.barang_id === barangId);
    if (!item) return;
    setForm(f => ({
      ...f, item_id: barangId,
      nama_barang: item.nama_barang || "", nama_pengrajin: item.nama_pengrajin || "",
      spesifikasi: item.spesifikasi || "", gambar_path: item.gambar_path || "",
    }));
  };

  const onSelectBarangManual = (barangId) => {
    const b = barangList.find(bl => (bl._id || bl.id) === barangId);
    setForm(f => ({
      ...f, item_id: barangId,
      nama_barang: b?.nama_barang || "", nama_pengrajin: b?.nama_pengrajin || "",
      spesifikasi: b?.spesifikasi || "", gambar_path: b?.gambar_path || "",
    }));
  };

  const printPDF = () => {
    const url = filterTanggal ? `${API}/export/progres/pdf?tanggal=${filterTanggal}` : `${API}/export/progres/pdf`;
    window.open(url, '_blank');
  };
  const printPage = () => window.print();

  const filtered = progresList.filter(po => filterPO === "all" || po.po_id === filterPO);

  return (
    <div className="space-y-6" data-testid="progres-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 print:hidden">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Progres Barang</h1>
          <p className="text-[#5C5C5C] mt-1">Tracking per tanggal: Grinda → Servis → Finishing → Packing. Setiap input jadi entry baru.</p>
        </div>
        <div className="flex gap-2 flex-wrap items-end">
          {canEditPartial && (
            <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setManual(false); setForm(initialForm); setEditEntryId(null); setErrorMsg(""); } }}>
              <DialogTrigger asChild>
                <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-progres-button"><Plus className="w-4 h-4 mr-2" /> Tambah Progres</Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>{editEntryId ? "Edit Entry Progres" : "Tambah Entry Progres"}</DialogTitle>
                  <DialogDescription>Setiap input jadi entry baru dengan tanggal & stage. Qty otomatis dibatasi oleh sisa dari stage sebelumnya.</DialogDescription>
                </DialogHeader>
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
                      </div>
                      {form.po_id && form.item_id && (
                        <div>
                          <Label>Pengrajin (dari alokasi SPK)</Label>
                          {currentAllocations.length === 0 ? (
                            <p className="text-xs text-[#F44336] mt-1">⚠️ Belum ada alokasi SPK untuk barang ini. Buat SPK dulu.</p>
                          ) : (
                            <Select value={form.pengrajin_id} onValueChange={(v) => {
                              const a = currentAllocations.find(x => x.pengrajin_id === v);
                              setForm(f => ({ ...f, pengrajin_id: v, pengrajin_nama: a?.pengrajin_nama || "" }));
                            }}>
                              <SelectTrigger data-testid="progres-select-pengrajin"><SelectValue placeholder="Pilih pengrajin" /></SelectTrigger>
                              <SelectContent>
                                {currentAllocations.map((a, i) => <SelectItem key={i} value={a.pengrajin_id}>{a.pengrajin_nama} (alokasi {a.qty})</SelectItem>)}
                              </SelectContent>
                            </Select>
                          )}
                        </div>
                      )}
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
                      <p className="text-xs text-[#F44336]">Mode manual: qty tidak dibatasi pipeline.</p>
                    </>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <Label><Calendar className="w-3 h-3 inline mr-1" /> Tanggal Input</Label>
                      <Input type="date" value={form.tanggal} onChange={(e) => setForm({ ...form, tanggal: e.target.value })} data-testid="progres-tanggal-input" />
                    </div>
                    <div>
                      <Label>Stage</Label>
                      <Select value={form.stage} onValueChange={(v) => setForm({ ...form, stage: v, qty: 0 })}>
                        <SelectTrigger data-testid="progres-stage-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {STAGES.map(s => <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {!manual && selectedProgres && (
                    <div className="p-3 bg-[#F0E6D6] rounded-md border border-[#D4B896] text-sm" data-testid="progres-context-info">
                      <p className="text-[#1A1A1A]"><strong>{selectedProgres.nama_barang}</strong> ({selectedPO?.no_po})</p>
                      <p className="text-[#5C5C5C] mt-1">
                        {ctx.upstreamLabel}: <strong>{ctx.upstreamQty}</strong> • Sudah di {form.stage}: <strong>{ctx.alreadyAt}</strong> • <span className="text-[#8B5A2B]">Sisa yang bisa diinput: <strong data-testid="progres-sisa-hint">{ctx.sisa}</strong></span>
                      </p>
                    </div>
                  )}

                  <div>
                    <Label>Qty Input {!manual && ctx.max !== Infinity && <span className="text-xs text-[#5C5C5C]">(max {ctx.max})</span>}</Label>
                    <Input type="number" min={1} max={manual ? undefined : ctx.max || undefined}
                      value={form.qty}
                      onChange={(e) => {
                        const n = Math.max(0, parseInt(e.target.value) || 0);
                        if (form.stage === "finishing" && !manual && ctx.upstreamQty != null && n > ctx.upstreamQty) {
                          setErrorMsg(`⚠️ Finishing qty (${n}) tidak boleh melebihi servis qty (${ctx.upstreamQty})`);
                        } else {
                          setErrorMsg("");
                        }
                        setForm({ ...form, qty: manual ? n : (ctx.max > 0 ? Math.min(n, ctx.max) : 0) });
                      }}
                      data-testid="progres-qty-input"
                      disabled={!manual && ctx.max === 0}
                    />
                    {!manual && ctx.max === 0 && <p className="text-xs text-[#F44336] mt-1">Tidak ada sisa yang bisa diinput ke {form.stage}. Isi stage sebelumnya dulu.</p>}
                  </div>

                  {form.stage === "finishing" && (
                    <div className="mt-4" data-testid="progres-catatan-finishing-section">
                      <Label className="block text-sm font-medium mb-2">Catatan Finishing (Warna & Qty)</Label>
                      <div className="space-y-2">
                        <Input
                          type="text"
                          maxLength={100}
                          placeholder="Catatan 1 (e.g., Merah: 10pcs)"
                          value={form.catatan_finishing_1}
                          onChange={(e) => setForm({ ...form, catatan_finishing_1: e.target.value })}
                          className="w-full px-3 py-2 border rounded-md text-sm"
                          data-testid="progres-catatan-finishing-1"
                        />
                        <Input
                          type="text"
                          maxLength={100}
                          placeholder="Catatan 2 (e.g., Biru: 15pcs)"
                          value={form.catatan_finishing_2}
                          onChange={(e) => setForm({ ...form, catatan_finishing_2: e.target.value })}
                          className="w-full px-3 py-2 border rounded-md text-sm"
                          data-testid="progres-catatan-finishing-2"
                        />
                        <Input
                          type="text"
                          maxLength={100}
                          placeholder="Catatan 3"
                          value={form.catatan_finishing_3}
                          onChange={(e) => setForm({ ...form, catatan_finishing_3: e.target.value })}
                          className="w-full px-3 py-2 border rounded-md text-sm"
                          data-testid="progres-catatan-finishing-3"
                        />
                        <Input
                          type="text"
                          maxLength={100}
                          placeholder="Catatan 4"
                          value={form.catatan_finishing_4}
                          onChange={(e) => setForm({ ...form, catatan_finishing_4: e.target.value })}
                          className="w-full px-3 py-2 border rounded-md text-sm"
                          data-testid="progres-catatan-finishing-4"
                        />
                        <Input
                          type="text"
                          maxLength={100}
                          placeholder="Catatan 5"
                          value={form.catatan_finishing_5}
                          onChange={(e) => setForm({ ...form, catatan_finishing_5: e.target.value })}
                          className="w-full px-3 py-2 border rounded-md text-sm"
                          data-testid="progres-catatan-finishing-5"
                        />
                      </div>
                    </div>
                  )}

                  {errorMsg && <p className="text-xs text-[#F44336] mt-1" data-testid="progres-error-msg">{errorMsg}</p>}

                  <Button onClick={submitCreate} className="w-full bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="submit-progres-button" disabled={!manual && ctx.max === 0}>Simpan Entry</Button>
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
                {po.items.map((item, idx) => {
                  const k = `${po.po_id}_${item.barang_id}`;
                  return (
                    <div key={idx} className="p-4 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]" data-testid={`progres-item-${poIdx}-${idx}`}>
                      <div className="flex flex-col md:flex-row gap-4 mb-3">
                        {item.gambar_path ? <img src={`${API}/files/${item.gambar_path}`} className="w-full md:w-24 h-24 object-cover rounded" alt="" /> : <div className="w-full md:w-24 h-24 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-8 h-8 text-[#8B5A2B]" /></div>}
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <h3 className="text-lg font-bold text-[#1A1A1A]">{item.nama_barang}</h3>
                            {item.komplit && <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-[#4CAF50] text-white rounded-full"><CheckCircle2 className="w-3 h-3" /> KOMPLIT</span>}
                            {item.tanggal && <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-[#F0E6D6] text-[#8B5A2B] rounded-full"><Calendar className="w-3 h-3" /> Update: {item.tanggal}</span>}
                          </div>
                          {canSeeCraftsman && <p className="text-sm text-[#5C5C5C]">Pengrajin: {item.nama_pengrajin}</p>}
                          <p className="text-sm text-[#5C5C5C]">{item.spesifikasi}</p>
                          <p className="text-sm mt-1">Qty Barang Masuk: <strong className="text-[#8B5A2B]">{item.qty_masuk}</strong></p>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {STAGES.map((stage) => (
                          <div key={stage.key} className="p-3 border border-[#E5E5E5] rounded-md bg-white" data-testid={`progres-stage-cell-${stage.key}-${poIdx}-${idx}`}>
                            <Label className="text-xs" style={{ color: stage.color }}>{stage.label}</Label>
                            <div className="mt-1 text-2xl font-bold" style={{ color: stage.color }} data-testid={`progres-${stage.key}-${poIdx}-${idx}`}>{item[stage.key] || 0}</div>
                            <p className="text-xs text-[#5C5C5C]" data-testid={`progres-sisa-${stage.key}-${poIdx}-${idx}`}>Sisa: <strong className="text-[#1A1A1A]">{item[`sisa_${stage.key}`] || 0}</strong></p>
                            {stage.key === "finishing" && (
                              <div className="mt-2 text-xs text-[#666] border-t border-[#E5E5E5] pt-2" data-testid={`progres-finishing-catatan-${poIdx}-${idx}`}>
                                {[1, 2, 3, 4, 5].map((n) => {
                                  const catatanKey = `catatan_finishing_${n}`;
                                  const catatan = historyMap[k]?.find(e => e.stage === "finishing" && e[catatanKey])?.[catatanKey];
                                  return catatan ? (
                                    <p key={n} className="text-[#5C5C5C] my-1">
                                      📌 {catatan}
                                    </p>
                                  ) : null;
                                })}
                                {historyMap[k]?.filter(e => e.stage === "finishing" && [1,2,3,4,5].some(n => e[`catatan_finishing_${n}`])).length === 0 && (
                                  <p className="text-[#999] italic">Belum ada catatan</p>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 flex justify-end">
                        <Button variant="ghost" size="sm" onClick={() => toggleHistory(po.po_id, item.barang_id)} data-testid={`toggle-history-${poIdx}-${idx}`} className="text-[#8B5A2B]"><History className="w-3 h-3 mr-1" /> {historyOpen[k] ? "Tutup" : "Lihat"} Riwayat Entry</Button>
                      </div>
                      {historyOpen[k] && (
                        <div className="mt-2 p-3 bg-white rounded-md border border-[#E5E5E5]" data-testid={`history-panel-${poIdx}-${idx}`}>
                          {!historyMap[k] ? <p className="text-xs text-[#5C5C5C]">Memuat...</p> : historyMap[k].length === 0 ? <p className="text-xs text-[#5C5C5C]">Belum ada entry.</p> : (
                            <div className="space-y-1">
                              {historyMap[k].map((e) => (
                                <div key={e._id}>
                                  <div className="flex items-center gap-2 text-sm">
                                    <span className="text-xs px-2 py-0.5 rounded" style={{ backgroundColor: (STAGES.find(s => s.key === e.stage)?.color || "#8B5A2B") + "22", color: STAGES.find(s => s.key === e.stage)?.color || "#8B5A2B" }}>{e.stage}</span>
                                    <span className="font-medium">+{e.qty}</span>
                                    <span className="text-[#5C5C5C]">•</span>
                                    <span className="text-xs text-[#5C5C5C]"><Calendar className="w-3 h-3 inline mr-0.5" />{e.tanggal}</span>
                                    {canEdit && (
                                      <div className="ml-auto flex gap-1">
                                        <Button variant="ghost" size="sm" className="text-[#2196F3] text-xs h-6 px-2" onClick={() => startEditEntry(e)} data-testid={`edit-entry-${e._id}`}>Edit</Button>
                                        <Button variant="ghost" size="sm" className="text-[#F44336] text-xs h-6 px-2" onClick={() => deleteEntry(e._id, po.po_id, item.barang_id)}>Hapus</Button>
                                      </div>
                                    )}
                                  </div>
                                  {e.stage === "finishing" && (
                                    <div className="pl-1" data-testid={`catatan-finishing-${e._id}`}>
                                      {e.catatan_finishing_1 && <p className="text-xs text-gray-600">{e.catatan_finishing_1}</p>}
                                      {e.catatan_finishing_2 && <p className="text-xs text-gray-600">{e.catatan_finishing_2}</p>}
                                      {e.catatan_finishing_3 && <p className="text-xs text-gray-600">{e.catatan_finishing_3}</p>}
                                      {e.catatan_finishing_4 && <p className="text-xs text-gray-600">{e.catatan_finishing_4}</p>}
                                      {e.catatan_finishing_5 && <p className="text-xs text-gray-600">{e.catatan_finishing_5}</p>}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
