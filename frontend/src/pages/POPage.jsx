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
import { Plus, Search, Trash2, FileText, Download, Edit, Package } from "lucide-react";

export default function POPage() {
  const { API, canEdit, canSeePrice, canSeeCraftsman } = useAuth();
  const [pos, setPos] = useState([]);
  const [barangList, setBarangList] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState({ no_po: "", items: [], catatan: "" });

  const load = async () => {
    try {
      const [poRes, brRes] = await Promise.all([
        axios.get(`${API}/po${search ? `?search=${search}` : ""}`),
        axios.get(`${API}/barang`),
      ]);
      setPos(poRes.data);
      setBarangList(brRes.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, [search]);

  const addItem = () => {
    setForm({ ...form, items: [...form.items, { barang_id: "", qty: 1, catatan: "" }] });
  };

  const removeItem = (idx) => {
    setForm({ ...form, items: form.items.filter((_, i) => i !== idx) });
  };

  const updateItem = (idx, key, val) => {
    const items = [...form.items];
    items[idx][key] = val;
    setForm({ ...form, items });
  };

  const submit = async () => {
    if (form.items.length === 0) {
      toast.error("Tambahkan minimal 1 barang");
      return;
    }
    try {
      if (editingId) {
        await axios.put(`${API}/po/${editingId}`, form);
        toast.success("PO berhasil diupdate");
      } else {
        await axios.post(`${API}/po`, form);
        toast.success("PO berhasil dibuat");
      }
      setOpen(false);
      setEditingId(null);
      setForm({ no_po: "", items: [], catatan: "" });
      load();
    } catch (e) {
      toast.error("Gagal: " + (e.response?.data?.detail || ""));
    }
  };

  const startEdit = async (poId, no_po) => {
    try {
      const { data } = await axios.get(`${API}/po/${poId}`);
      setForm({
        no_po: data.no_po,
        catatan: data.catatan,
        items: data.items.map(i => ({ barang_id: i.barang_id, qty: i.qty, catatan: i.catatan || "" }))
      });
      setEditingId(poId);
      setOpen(true);
    } catch (e) { toast.error("Gagal load PO"); }
  };

  const downloadPDF = async (po) => {
    try {
      const pos_full = await axios.get(`${API}/po?search=${po.no_po}`);
      const url = `${API}/export/po/${po._id || pos_full.data[0]._id}/pdf`;
      window.open(url, '_blank');
    } catch (e) { toast.error("Gagal download"); }
  };

  const deletePo = async (id) => {
    try {
      await axios.delete(`${API}/po/${id}`);
      toast.success("PO dihapus");
      load();
    } catch (e) { toast.error("Gagal hapus"); }
  };

  return (
    <div className="space-y-6" data-testid="po-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Purchase Order (PO)</h1>
          <p className="text-[#5C5C5C] mt-1">Manajemen order pembelian ke pengrajin</p>
        </div>
        {canEdit && (
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditingId(null); setForm({ no_po: "", items: [], catatan: "" }); }}}>
            <DialogTrigger asChild>
              <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-po-button">
                <Plus className="w-4 h-4 mr-2" /> Buat PO
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{editingId ? "Edit PO" : "Buat PO Baru"}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label>No PO</Label>
                  <Input data-testid="input-no-po" value={form.no_po} onChange={(e) => setForm({ ...form, no_po: e.target.value })} placeholder="PO-2026-001" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Daftar Barang</Label>
                    <Button size="sm" variant="outline" onClick={addItem} data-testid="add-po-item-button"><Plus className="w-3 h-3 mr-1" /> Tambah</Button>
                  </div>
                  <div className="space-y-2">
                    {form.items.map((item, idx) => (
                      <div key={idx} className="p-3 border border-[#E5E5E5] rounded-md space-y-2">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 items-end">
                          <div className="md:col-span-7">
                            <Label className="text-xs">Barang</Label>
                            <Select value={item.barang_id} onValueChange={(v) => updateItem(idx, "barang_id", v)}>
                              <SelectTrigger data-testid={`select-barang-${idx}`}><SelectValue placeholder="Pilih barang" /></SelectTrigger>
                              <SelectContent>
                                {barangList.map((b, bi) => (
                                  <SelectItem key={bi} value={b._id || b.id || `${bi}`}>{b.nama_barang}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="md:col-span-3">
                            <Label className="text-xs">Qty</Label>
                            <Input type="number" data-testid={`input-qty-${idx}`} value={item.qty} onChange={(e) => updateItem(idx, "qty", parseInt(e.target.value) || 1)} />
                          </div>
                          <div className="md:col-span-2">
                            <Button variant="ghost" size="icon" onClick={() => removeItem(idx)} className="text-[#F44336]"><Trash2 className="w-4 h-4" /></Button>
                          </div>
                        </div>
                        <Input placeholder="Catatan item (opsional)" value={item.catatan} onChange={(e) => updateItem(idx, "catatan", e.target.value)} />
                      </div>
                    ))}
                    {form.items.length === 0 && (
                      <p className="text-sm text-[#5C5C5C] text-center py-4">Belum ada barang. Klik &quot;Tambah&quot; untuk menambahkan.</p>
                    )}
                  </div>
                </div>
                <div>
                  <Label>Catatan PO</Label>
                  <Textarea value={form.catatan} onChange={(e) => setForm({ ...form, catatan: e.target.value })} />
                </div>
                <Button onClick={submit} className="w-full bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="submit-po-button">{editingId ? "Update PO" : "Simpan PO"}</Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Card className="p-4 border border-[#E5E5E5]">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5C5C5C]" />
          <Input placeholder="Cari No PO..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" data-testid="search-po-input" />
        </div>
      </Card>

      <div className="space-y-4" data-testid="po-list">
        {pos.length === 0 ? (
          <Card className="p-12 text-center border border-dashed border-[#E5E5E5]">
            <FileText className="w-12 h-12 mx-auto text-[#5C5C5C] mb-3" />
            <p className="text-[#5C5C5C]">Belum ada PO. Buat PO pertama.</p>
          </Card>
        ) : (
          pos.map((po, idx) => (
            <Card key={idx} className="p-6 border border-[#E5E5E5]" data-testid={`po-card-${idx}`}>
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-3 mb-4">
                <div>
                  <h3 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>{po.no_po}</h3>
                  <p className="text-sm text-[#5C5C5C] mt-1">{po.items?.length || 0} jenis barang</p>
                  {po.catatan && <p className="text-sm text-[#5C5C5C] mt-1">Catatan: {po.catatan}</p>}
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button variant="outline" size="sm" onClick={() => setDetail(po)} data-testid={`view-po-${idx}`}>Detail</Button>
                  {canEdit && (
                    <>
                      <Button variant="outline" size="sm" onClick={() => startEdit(po._id, po.no_po)} data-testid={`edit-po-${idx}`}><Edit className="w-3 h-3 mr-1" /> Edit</Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="outline" size="sm" className="text-[#F44336]" data-testid={`delete-po-${idx}`}><Trash2 className="w-3 h-3" /></Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Hapus PO {po.no_po}?</AlertDialogTitle>
                            <AlertDialogDescription>PO ini akan dihapus permanen.</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Batal</AlertDialogCancel>
                            <AlertDialogAction className="bg-[#F44336]" onClick={() => deletePo(po._id)}>Hapus</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </>
                  )}
                  <Button variant="outline" size="sm" onClick={() => downloadPDF(po)} data-testid={`pdf-po-${idx}`}><Download className="w-3 h-3 mr-1" /> PDF</Button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {po.items?.map((item, ii) => {
                  const subtotal = (item.qty || 0) * (item.harga_jual || 0);
                  return (
                  <div key={ii} className="flex gap-3 p-3 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]">
                    {item.gambar_path ? (
                      <img src={`${API}/files/${item.gambar_path}`} alt={item.nama_barang} className="w-16 h-16 object-cover rounded" />
                    ) : (
                      <div className="w-16 h-16 bg-[#F0E6D6] rounded flex items-center justify-center flex-shrink-0"><Package className="w-6 h-6 text-[#8B5A2B]" /></div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-[#1A1A1A] truncate">{item.nama_barang}</p>
                      {canSeeCraftsman && <p className="text-xs text-[#5C5C5C] truncate">{item.nama_pengrajin}</p>}
                      <div className="mt-1 flex items-center gap-2 text-xs flex-wrap">
                        <span className="px-1.5 py-0.5 bg-[#8B5A2B] text-white rounded">Qty: {item.qty}</span>
                        <span className="text-[#4CAF50]">Diterima: {item.qty_diterima || 0}</span>
                      </div>
                      {canSeePrice && (
                        <p className="text-xs mt-1 text-[#1A1A1A]" data-testid={`po-item-subtotal-${idx}-${ii}`}>Subtotal: <strong>Rp {subtotal.toLocaleString('id-ID')}</strong></p>
                      )}
                      {(item.qty - (item.qty_diterima || 0)) > 0 && (
                        <p className="text-xs text-[#F44336] mt-1">Kurang: {item.qty - (item.qty_diterima || 0)} pcs</p>
                      )}
                    </div>
                  </div>
                )})}
              </div>
              {canSeePrice && (
                <div className="mt-4 pt-3 border-t border-[#E5E5E5] flex justify-end">
                  <p className="text-sm text-[#1A1A1A]" data-testid={`po-grand-total-${idx}`}>
                    <span className="text-[#5C5C5C]">Grand Total: </span>
                    <strong className="text-[#8B5A2B] text-lg">Rp {(po.items || []).reduce((s, i) => s + (i.qty || 0) * (i.harga_jual || 0), 0).toLocaleString('id-ID')}</strong>
                  </p>
                </div>
              )}
            </Card>
          ))
        )}
      </div>

      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Detail PO: {detail?.no_po}</DialogTitle></DialogHeader>
          {detail && (
            <div className="space-y-4">
              {detail.catatan && <p className="text-sm text-[#5C5C5C]">Catatan: {detail.catatan}</p>}
              {detail.items?.map((item, i) => {
                const subtotal = (item.qty || 0) * (item.harga_jual || 0);
                return (
                <div key={i} className="flex gap-4 p-3 border border-[#E5E5E5] rounded-md">
                  {item.gambar_path && <img src={`${API}/files/${item.gambar_path}`} className="w-24 h-24 object-cover rounded" alt="" />}
                  <div className="flex-1">
                    <h4 className="font-bold text-[#1A1A1A]">{item.nama_barang}</h4>
                    {canSeeCraftsman && <p className="text-sm">Pengrajin: {item.nama_pengrajin}</p>}
                    <p className="text-sm text-[#5C5C5C]">{item.spesifikasi}</p>
                    <p className="text-sm mt-1">Qty: <strong>{item.qty}</strong> | Diterima: <strong className="text-[#4CAF50]">{item.qty_diterima || 0}</strong></p>
                    {canSeePrice && (
                      <>
                        <p className="text-sm text-[#5C5C5C]">Harga Jual: Rp {item.harga_jual?.toLocaleString('id-ID')}</p>
                        <p className="text-sm text-[#1A1A1A]">Subtotal ({item.qty} × Rp {item.harga_jual?.toLocaleString('id-ID')}): <strong className="text-[#8B5A2B]">Rp {subtotal.toLocaleString('id-ID')}</strong></p>
                      </>
                    )}
                  </div>
                </div>
              )})}
              {canSeePrice && (
                <div className="pt-3 border-t border-[#E5E5E5] flex justify-between items-center bg-[#F0E6D6] p-3 rounded-md">
                  <span className="font-bold text-[#1A1A1A]">Grand Total PO:</span>
                  <span className="font-bold text-xl text-[#8B5A2B]" data-testid="po-detail-grand-total">
                    Rp {(detail.items || []).reduce((s, i) => s + (i.qty || 0) * (i.harga_jual || 0), 0).toLocaleString('id-ID')}
                  </span>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
