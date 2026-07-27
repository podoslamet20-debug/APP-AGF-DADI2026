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
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [preview, setPreview] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedPO, setSelectedPO] = useState(null);
  const [form, setForm] = useState({ po_id: "", tanggal_masuk: "", penerima: "", items: [] });

  const load = async () => {
    try {
      const [bmRes, poRes] = await Promise.all([axios.get(`${API}/barang-masuk`), axios.get(`${API}/po`)]);
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
    } catch (e) { console.error(e); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [search]);

  const selectPO = async (poId) => {
    const po = pos.find(p => (p._id || p.id) === poId);
    if (!po) return;
    setSelectedPO(po);
    setForm({
      ...form,
      po_id: poId,
      items: po.items.map(i => ({ ...i, qty_diterima: 0, _selected: true, _original_qty_diterima: i.qty_diterima || 0, _sisa: (i.qty || 0) - (i.qty_diterima || 0) }))
    });
  };

  const toggleItem = (idx) => {
    const items = [...form.items];
    items[idx]._selected = !items[idx]._selected;
    setForm({ ...form, items });
  };

  const updateQty = (idx, qty) => {
    const items = [...form.items];
    const maxQty = (items[idx].qty || 0) - (items[idx]._original_qty_diterima || 0);
    const clamped = Math.min(Math.max(parseInt(qty) || 0, 0), maxQty);
    items[idx].qty_diterima = clamped;
    setForm({ ...form, items });
  };

  const submit = async () => {
    if (!form.po_id || !form.tanggal_masuk || !form.penerima) {
      toast.error("Isi semua field wajib");
      return;
    }
    // Only include items with _selected=true (or true by default) and qty_diterima > 0
    const filteredItems = form.items.filter(i => i._selected !== false && (i.qty_diterima || 0) > 0).map(({_selected, ...rest}) => rest);
    if (filteredItems.length === 0) {
      toast.error("Pilih minimal 1 barang dengan qty > 0");
      return;
    }
    const payload = { ...form, items: filteredItems };
    try {
      if (editingId) {
        await axios.put(`${API}/barang-masuk/${editingId}`, payload);
        toast.success("Barang masuk berhasil diupdate");
      } else {
        await axios.post(`${API}/barang-masuk`, payload);
        toast.success("Barang masuk berhasil dicatat");
      }
      setOpen(false);
      setEditingId(null);
      setForm({ po_id: "", tanggal_masuk: "", penerima: "", items: [] });
      setSelectedPO(null);
      load();
    } catch (e) {
      toast.error("Gagal: " + (e.response?.data?.detail || ""));
    }
  };

  const startEdit = (bm) => {
    // Reload from PO to get accurate qty & sisa; subtract this record's contribution from "sudah diterima"
    const po = pos.find(p => (p._id || p.id) === bm.po_id);
    const bmMap = new Map((bm.items || []).map(i => [i.barang_id, i]));
    const items = (po?.items || bm.items || []).map(pi => {
      const own = bmMap.get(pi.barang_id);
      const otherReceived = (pi.qty_diterima || 0) - ((own?.qty_diterima) || 0);
      return {
        ...pi,
        qty_diterima: own?.qty_diterima || 0,
        _selected: !!own,
        _original_qty_diterima: otherReceived,
      };
    });
    setForm({ po_id: bm.po_id, tanggal_masuk: bm.tanggal_masuk, penerima: bm.penerima, items });
    setEditingId(bm._id);
    setSelectedPO(po || { items });
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
          <p className="text-[#5C5C5C] mt-1">Catat barang yang masuk dari pengrajin</p>
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
              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>{editingId ? "Edit Barang Masuk" : "Catat Barang Masuk"}</DialogTitle>
                  <DialogDescription>Pilih PO lalu centang barang yang diterima dan isi jumlahnya. Qty dibatasi sisa PO.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label>Pilih PO</Label>
                    <Select value={form.po_id} onValueChange={selectPO}>
                      <SelectTrigger data-testid="select-po-bm"><SelectValue placeholder="Pilih PO" /></SelectTrigger>
                      <SelectContent>
                        {pos.map((p, i) => <SelectItem key={i} value={p._id || p.id || `${i}`}>{p.no_po}</SelectItem>)}
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
                      <Label>Pilih Barang yang Masuk <span className="text-xs text-[#5C5C5C]">(centang untuk memilih)</span></Label>
                      <div className="space-y-2 mt-2">
                        {form.items.map((item, idx) => (
                          <div key={idx} className={`p-3 rounded-md border flex gap-3 ${item._selected !== false ? 'bg-[#FAFAFA] border-[#E5E5E5]' : 'bg-gray-100 border-gray-200 opacity-60'}`}>
                            <input
                              type="checkbox"
                              checked={item._selected !== false}
                              onChange={() => toggleItem(idx)}
                              data-testid={`bm-select-${idx}`}
                              className="mt-2 w-4 h-4 accent-[#8B5A2B]"
                            />
                            {item.gambar_path && <img src={`${API}/files/${item.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" />}
                            <div className="flex-1">
                              <p className="font-medium text-sm">{item.nama_barang}</p>
                              {canSeeCraftsman && <p className="text-xs text-[#5C5C5C]">{item.nama_pengrajin}</p>}
                              <p className="text-xs text-[#5C5C5C]">Total PO: {item.qty} • Sudah Diterima: {item._original_qty_diterima || 0} • <span className={`font-semibold ${(item.qty - (item._original_qty_diterima || 0)) > 0 ? 'text-[#8B5A2B]' : 'text-[#4CAF50]'}`}>Sisa: {(item.qty || 0) - (item._original_qty_diterima || 0)}</span></p>
                            </div>
                            <div className="w-24">
                              <Label className="text-xs">Qty Terima</Label>
                              <Input type="number" min="0" max={(item.qty || 0) - (item._original_qty_diterima || 0)} data-testid={`bm-qty-${idx}`} value={item.qty_diterima} onChange={(e) => updateQty(idx, e.target.value)} disabled={item._selected === false} />
                            </div>
                          </div>
                        ))}
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
                {bm.items?.map((item, ii) => {
                  const poItem = poItems.find(pi => pi.barang_id === item.barang_id);
                  const itemKomplit = poItem && (poItem.qty_diterima || 0) >= (poItem.qty || 0) && (poItem.qty || 0) > 0;
                  return (
                  <div key={ii} className="flex gap-3 p-3 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]">
                    {item.gambar_path ? <img src={`${API}/files/${item.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" /> : <div className="w-14 h-14 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-5 h-5 text-[#8B5A2B]" /></div>}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1 flex-wrap">
                        <p className="font-medium text-sm truncate">{item.nama_barang}</p>
                        {itemKomplit && <span className="text-[10px] px-1 py-0 bg-[#4CAF50] text-white rounded" data-testid={`bm-item-komplit-${idx}-${ii}`}>KOMPLIT</span>}
                      </div>
                      {canSeeCraftsman && <p className="text-xs text-[#5C5C5C] truncate">{item.nama_pengrajin}</p>}
                      <span className="text-xs px-1.5 py-0.5 bg-[#4CAF50] text-white rounded inline-block mt-1">Diterima: {item.qty_diterima}{poItem ? ` / ${poItem.qty}` : ''}</span>
                    </div>
                  </div>
                  );
                })}
              </div>
            </Card>
          )})
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
                    {canSeeCraftsman && <p className="text-sm text-[#5C5C5C]">{item.nama_pengrajin}</p>}
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
