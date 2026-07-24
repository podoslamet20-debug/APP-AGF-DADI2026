import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Plus, Search, Trash2, FileText, Download, Package, Edit } from "lucide-react";

export default function SPKPage() {
  const { API, canEdit, canSeePrice, canSeeCraftsman } = useAuth();
  const [spks, setSpks] = useState([]);
  const [barangList, setBarangList] = useState([]);
  const [poList, setPoList] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState({
    no_spk: "",
    items: [],
    catatan_pembayaran: "",
    owner_perusahaan: "",
    deadline: "",
  });

  const load = async () => {
    try {
      const [spkRes, brRes, poRes] = await Promise.all([
        axios.get(`${API}/spk${search ? `?search=${search}` : ""}`),
        axios.get(`${API}/barang`),
        axios.get(`${API}/po`),
      ]);
      setSpks(spkRes.data);
      setBarangList(brRes.data);
      setPoList(poRes.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, [search]);

  const importFromPO = (poId) => {
    const po = poList.find(p => (p._id || p.id) === poId);
    if (!po) return;
    const newItems = po.items.map(i => ({
      barang_id: i.barang_id,
      nama_barang: i.nama_barang,
      spesifikasi: i.spesifikasi,
      qty: i.qty,
      no_po: po.no_po,
      nama_pengrajin: i.nama_pengrajin,
      harga: i.harga_pengrajin || 0,
      gambar_path: i.gambar_path,
    }));
    setForm({ ...form, items: [...form.items, ...newItems] });
    toast.success(`${newItems.length} item ditambahkan dari PO ${po.no_po}`);
  };

  const addItem = () => {
    setForm({ ...form, items: [...form.items, { barang_id: "", nama_barang: "", spesifikasi: "", qty: 1, no_po: "", nama_pengrajin: "", harga: 0, gambar_path: "" }] });
  };

  const removeItem = (idx) => {
    setForm({ ...form, items: form.items.filter((_, i) => i !== idx) });
  };

  const selectBarang = (idx, barangId) => {
    const b = barangList.find(bl => (bl._id || bl.id) === barangId);
    if (!b) return;
    const items = [...form.items];
    items[idx] = {
      ...items[idx],
      barang_id: barangId,
      nama_barang: b.nama_barang,
      spesifikasi: b.spesifikasi,
      nama_pengrajin: b.nama_pengrajin,
      pengrajin_list: b.pengrajin_list || [],
      gambar_path: b.gambar_path,
      harga: b.harga_pengrajin || 0,
    };
    setForm({ ...form, items });
  };

  const updateItem = (idx, key, val) => {
    const items = [...form.items];
    items[idx][key] = val;
    setForm({ ...form, items });
  };

  const submit = async () => {
    if (form.items.length === 0) { toast.error("Tambahkan minimal 1 barang"); return; }
    try {
      if (editingId) {
        await axios.put(`${API}/spk/${editingId}`, form);
        toast.success("SPK berhasil diupdate");
      } else {
        await axios.post(`${API}/spk`, form);
        toast.success("SPK berhasil dibuat");
      }
      setOpen(false);
      setEditingId(null);
      setForm({ no_spk: "", items: [], catatan_pembayaran: "", owner_perusahaan: "", deadline: "" });
      load();
    } catch (e) {
      toast.error("Gagal: " + (e.response?.data?.detail || ""));
    }
  };

  const startEdit = (spk) => {
    setForm({
      no_spk: spk.no_spk,
      items: spk.items,
      catatan_pembayaran: spk.catatan_pembayaran,
      owner_perusahaan: spk.owner_perusahaan,
      deadline: spk.deadline,
    });
    setEditingId(spk._id);
    setOpen(true);
  };

  const downloadPDF = (spkId) => {
    window.open(`${API}/export/spk/${spkId}/pdf`, '_blank');
  };

  const deleteSpk = async (id) => {
    try {
      await axios.delete(`${API}/spk/${id}`);
      toast.success("SPK dihapus");
      load();
    } catch (e) { toast.error("Gagal hapus"); }
  };

  return (
    <div className="space-y-6" data-testid="spk-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>SPK</h1>
          <p className="text-[#5C5C5C] mt-1">Surat Perintah Kerja untuk pengrajin</p>
        </div>
        {canEdit && (
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditingId(null); setForm({ no_spk: "", items: [], catatan_pembayaran: "", owner_perusahaan: "", deadline: "" }); }}}>
            <DialogTrigger asChild>
              <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-spk-button"><Plus className="w-4 h-4 mr-2" /> Buat SPK</Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>{editingId ? "Edit SPK" : "Buat SPK Baru"}</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>No SPK</Label>
                    <Input data-testid="input-no-spk" value={form.no_spk} onChange={(e) => setForm({ ...form, no_spk: e.target.value })} />
                  </div>
                  <div>
                    <Label>Deadline</Label>
                    <Input type="date" data-testid="input-deadline" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Daftar Barang</Label>
                    <div className="flex gap-2">
                      <Select onValueChange={importFromPO}>
                        <SelectTrigger className="w-48 h-8 text-xs" data-testid="import-from-po"><SelectValue placeholder="Import dari PO..." /></SelectTrigger>
                        <SelectContent>
                          {poList.map((p, i) => <SelectItem key={i} value={p._id || `${i}`}>{p.no_po}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Button size="sm" variant="outline" onClick={addItem} data-testid="add-spk-item"><Plus className="w-3 h-3 mr-1" /> Manual</Button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {form.items.map((item, idx) => {
                      const pengrajinOptions = [item.nama_pengrajin, ...(item.pengrajin_list || [])].filter(Boolean);
                      // Dedupe while preserving order
                      const seen = new Set();
                      const uniqueOptions = pengrajinOptions.filter(p => { if (seen.has(p)) return false; seen.add(p); return true; });
                      return (
                      <div key={idx} className="p-3 border border-[#E5E5E5] rounded-md space-y-2">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 items-end">
                          <div className="md:col-span-6">
                            <Label className="text-xs">Barang</Label>
                            <Select value={item.barang_id} onValueChange={(v) => selectBarang(idx, v)}>
                              <SelectTrigger data-testid={`spk-barang-${idx}`}><SelectValue placeholder="Pilih barang" /></SelectTrigger>
                              <SelectContent>
                                {barangList.map((b, bi) => <SelectItem key={bi} value={b._id || b.id || `${bi}`}>{b.nama_barang}</SelectItem>)}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="md:col-span-2">
                            <Label className="text-xs">Qty</Label>
                            <Input type="number" data-testid={`spk-qty-${idx}`} value={item.qty} onChange={(e) => updateItem(idx, "qty", parseInt(e.target.value) || 1)} />
                          </div>
                          <div className="md:col-span-3">
                            <Label className="text-xs">No PO</Label>
                            <Input value={item.no_po || ""} onChange={(e) => updateItem(idx, "no_po", e.target.value)} />
                          </div>
                          <div className="md:col-span-1">
                            <Button variant="ghost" size="icon" onClick={() => removeItem(idx)} className="text-[#F44336]"><Trash2 className="w-4 h-4" /></Button>
                          </div>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                          <div className="md:col-span-5">
                            <Label className="text-xs">Pengrajin</Label>
                            {uniqueOptions.length > 1 ? (
                              <Select value={item.nama_pengrajin || ""} onValueChange={(v) => updateItem(idx, "nama_pengrajin", v)}>
                                <SelectTrigger data-testid={`spk-pengrajin-select-${idx}`}><SelectValue placeholder="Pilih pengrajin" /></SelectTrigger>
                                <SelectContent>
                                  {uniqueOptions.map((p, pi) => <SelectItem key={pi} value={p}>{p}</SelectItem>)}
                                </SelectContent>
                              </Select>
                            ) : (
                              <Input value={item.nama_pengrajin || ""} onChange={(e) => updateItem(idx, "nama_pengrajin", e.target.value)} placeholder="Nama pengrajin" data-testid={`spk-pengrajin-input-${idx}`} />
                            )}
                          </div>
                          <div className="md:col-span-4">
                            <Label className="text-xs">Harga</Label>
                            <Input type="number" placeholder="Harga" value={item.harga} onChange={(e) => updateItem(idx, "harga", parseFloat(e.target.value) || 0)} data-testid={`spk-harga-${idx}`} />
                          </div>
                          <div className="md:col-span-3">
                            <Label className="text-xs">Catatan Item</Label>
                            <Input placeholder="Note (opsional)" value={item.catatan || ""} onChange={(e) => updateItem(idx, "catatan", e.target.value)} data-testid={`spk-catatan-${idx}`} />
                          </div>
                        </div>
                      </div>
                    )})}
                  </div>
                </div>
                <div>
                  <Label>Catatan Pembayaran</Label>
                  <Textarea data-testid="input-catatan-pembayaran" value={form.catatan_pembayaran} onChange={(e) => setForm({ ...form, catatan_pembayaran: e.target.value })} />
                </div>
                <div>
                  <Label>Owner Perusahaan</Label>
                  <Input data-testid="input-owner" value={form.owner_perusahaan} onChange={(e) => setForm({ ...form, owner_perusahaan: e.target.value })} />
                </div>
                <Button onClick={submit} className="w-full bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="submit-spk-button">{editingId ? "Update SPK" : "Simpan SPK"}</Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Card className="p-4 border border-[#E5E5E5]">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5C5C5C]" />
          <Input placeholder="Cari No SPK..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" data-testid="search-spk-input" />
        </div>
      </Card>

      <div className="space-y-4" data-testid="spk-list">
        {spks.length === 0 ? (
          <Card className="p-12 text-center border border-dashed border-[#E5E5E5]">
            <FileText className="w-12 h-12 mx-auto text-[#5C5C5C] mb-3" />
            <p className="text-[#5C5C5C]">Belum ada SPK.</p>
          </Card>
        ) : (
          spks.map((spk, idx) => (
            <Card key={idx} className="p-6 border border-[#E5E5E5]" data-testid={`spk-card-${idx}`}>
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-3 mb-4">
                <div>
                  <h3 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>{spk.no_spk}</h3>
                  <p className="text-sm text-[#5C5C5C]">Deadline: {spk.deadline}</p>
                  <p className="text-sm text-[#5C5C5C]">Owner: {spk.owner_perusahaan}</p>
                </div>
                <div className="flex gap-2">
                  {canEdit && <Button variant="outline" size="sm" onClick={() => setDetail(spk)} data-testid={`view-spk-${idx}`}>Detail</Button>}
                  {canEdit && <Button variant="outline" size="sm" onClick={() => startEdit(spk)} data-testid={`edit-spk-${idx}`}><Edit className="w-3 h-3 mr-1" /> Edit</Button>}
                  {canEdit && (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="outline" size="sm" className="text-[#F44336]" data-testid={`delete-spk-${idx}`}><Trash2 className="w-3 h-3" /></Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Hapus SPK?</AlertDialogTitle>
                          <AlertDialogDescription>SPK {spk.no_spk} akan dihapus permanen.</AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Batal</AlertDialogCancel>
                          <AlertDialogAction className="bg-[#F44336]" onClick={() => deleteSpk(spk._id)}>Hapus</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                  <Button variant="outline" size="sm" onClick={() => downloadPDF(spk._id)} data-testid={`pdf-spk-${idx}`}><Download className="w-3 h-3 mr-1" /> PDF</Button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {spk.items?.map((item, ii) => (
                  <div key={ii} className="flex gap-3 p-3 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]">
                    {item.gambar_path ? <img src={`${API}/files/${item.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" /> : <div className="w-14 h-14 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-5 h-5 text-[#8B5A2B]" /></div>}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{item.nama_barang}</p>
                      {canSeeCraftsman && <p className="text-xs text-[#5C5C5C] truncate">{item.nama_pengrajin}</p>}
                      <div className="flex gap-2 items-center mt-1 flex-wrap">
                        <span className="text-xs px-1.5 py-0.5 bg-[#8B5A2B] text-white rounded">Qty: {item.qty}</span>
                        {canSeePrice && item.harga > 0 && <span className="text-xs text-[#4CAF50]">Rp {item.harga?.toLocaleString('id-ID')}</span>}
                      </div>
                      {item.catatan && <p className="text-xs text-[#5C5C5C] italic mt-1 truncate">📝 {item.catatan}</p>}
                    </div>
                  </div>
                ))}
              </div>
              {spk.catatan_pembayaran && (
                <div className="mt-4 pt-4 border-t border-[#E5E5E5]">
                  <p className="text-sm text-[#5C5C5C]"><strong>Catatan Pembayaran:</strong> {spk.catatan_pembayaran}</p>
                </div>
              )}
            </Card>
          ))
        )}
      </div>
      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Detail SPK: {detail?.no_spk}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-4">
              <div className="text-sm">
                <p><strong>Deadline:</strong> {detail.deadline}</p>
                <p><strong>Owner:</strong> {detail.owner_perusahaan}</p>
              </div>
              {detail.items?.map((item, i) => (
                <div key={i} className="flex gap-4 p-3 border border-[#E5E5E5] rounded-md">
                  {item.gambar_path && <img src={`${API}/files/${item.gambar_path}`} className="w-24 h-24 object-cover rounded" alt="" />}
                  <div className="flex-1">
                    <h4 className="font-bold text-[#1A1A1A]">{item.nama_barang}</h4>
                    {canSeeCraftsman && <p className="text-sm">Pengrajin: {item.nama_pengrajin}</p>}
                    <p className="text-sm text-[#5C5C5C]">{item.spesifikasi}</p>
                    <p className="text-sm mt-1">No PO: <strong>{item.no_po}</strong> | Qty: <strong>{item.qty}</strong></p>
                    {canSeePrice && item.harga > 0 && <p className="text-sm text-[#4CAF50]">Rp {item.harga?.toLocaleString('id-ID')}</p>}
                    {item.catatan && <p className="text-sm text-[#5C5C5C] italic mt-1">📝 {item.catatan}</p>}
                  </div>
                </div>
              ))}
              {detail.catatan_pembayaran && (
                <div className="p-3 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]">
                  <p className="text-sm"><strong>Catatan Pembayaran:</strong> {detail.catatan_pembayaran}</p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
