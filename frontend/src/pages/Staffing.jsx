import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Plus, Truck, Package, Search, Trash2, Edit, Eye, Download, Printer } from "lucide-react";

export default function Staffing() {
  const { API, canEditPartial, canSeeCraftsman } = useAuth();
  const [items, setItems] = useState([]);
  const [pos, setPos] = useState([]);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [preview, setPreview] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedPO, setSelectedPO] = useState(null);
  const [form, setForm] = useState({ po_id: "", tanggal_keluar: "", items: [] });

  const load = async () => {
    try {
      const [stRes, poRes] = await Promise.all([axios.get(`${API}/staffing`), axios.get(`${API}/po`)]);
      let stData = stRes.data;
      if (search) {
        stData = stData.filter(st => st.no_po?.toLowerCase().includes(search.toLowerCase()));
      }
      setItems(stData);
      setPos(poRes.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, [search]);

  const selectPO = (poId) => {
    const po = pos.find(p => (p._id || p.id) === poId);
    if (!po) return;
    setSelectedPO(po);
    setForm({ ...form, po_id: poId, items: po.items.map(i => {
      const sisa = (i.qty || 0) - (i.qty_staffed || 0);
      return { ...i, _original_qty: i.qty || 0, qty: 0, _selected: true, _max_qty: sisa, _sisa: sisa };
    }) });
  };

  const toggleItem = (idx) => {
    const items = [...form.items];
    items[idx]._selected = !items[idx]._selected;
    setForm({ ...form, items });
  };

  const updateQty = (idx, qty) => {
    const items = [...form.items];
    const max = items[idx]._max_qty || items[idx].qty || 0;
    items[idx].qty = Math.min(Math.max(parseInt(qty) || 0, 0), max);
    setForm({ ...form, items });
  };

  const submit = async () => {
    if (!form.po_id || !form.tanggal_keluar) {
      toast.error("Isi semua field wajib");
      return;
    }
    const filteredItems = form.items.filter(i => i._selected !== false && (i.qty || 0) > 0).map(({_selected, _max_qty, _sisa, _original_qty, ...rest}) => rest);
    if (filteredItems.length === 0) {
      toast.error("Pilih minimal 1 barang dengan qty > 0");
      return;
    }
    const payload = { ...form, items: filteredItems };
    try {
      if (editingId) {
        await axios.put(`${API}/staffing/${editingId}`, payload);
        toast.success("Staffing berhasil diupdate");
      } else {
        await axios.post(`${API}/staffing`, payload);
        toast.success("Staffing berhasil dicatat");
      }
      setOpen(false);
      setEditingId(null);
      setForm({ po_id: "", tanggal_keluar: "", items: [] });
      setSelectedPO(null);
      load();
    } catch (e) {
      toast.error("Gagal: " + (e.response?.data?.detail || ""));
    }
  };

  const startEdit = (st) => {
    setForm({ po_id: st.po_id, tanggal_keluar: st.tanggal_keluar, items: st.items });
    setEditingId(st._id);
    setSelectedPO({ items: st.items });
    setOpen(true);
  };

  const deleteStaffing = async (id) => {
    try {
      await axios.delete(`${API}/staffing/${id}`);
      toast.success("Staffing dihapus");
      load();
    } catch (e) { toast.error("Gagal hapus"); }
  };

  const downloadPDF = (id) => window.open(`${API}/export/staffing/${id}/pdf`, '_blank');
  const downloadAllPDF = () => window.open(`${API}/export/staffing/pdf`, '_blank');
  const downloadExcel = () => window.open(`${API}/export/staffing/excel`, '_blank');
  const printPage = () => window.print();

  return (
    <div className="space-y-6" data-testid="staffing-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 print:hidden">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Staffing</h1>
          <p className="text-[#5C5C5C] mt-1">Catat barang keluar/dikirim ke customer</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" onClick={downloadAllPDF} data-testid="export-pdf-staffing"><Download className="w-4 h-4 mr-2" /> PDF</Button>
          <Button variant="outline" onClick={downloadExcel} data-testid="export-excel-staffing"><Download className="w-4 h-4 mr-2" /> Excel</Button>
          <Button variant="outline" onClick={printPage} data-testid="print-staffing"><Printer className="w-4 h-4 mr-2" /> Print</Button>
        </div>
        {canEditPartial && (
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditingId(null); setForm({ po_id: "", tanggal_keluar: "", items: [] }); setSelectedPO(null); }}}>
            <DialogTrigger asChild>
              <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-staffing-button"><Plus className="w-4 h-4 mr-2" /> Catat Staffing</Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>{editingId ? "Edit Staffing" : "Catat Staffing"}</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label>Pilih PO</Label>
                  <Select value={form.po_id} onValueChange={selectPO}>
                    <SelectTrigger data-testid="select-po-staffing"><SelectValue placeholder="Pilih PO" /></SelectTrigger>
                    <SelectContent>
                      {pos.map((p, i) => <SelectItem key={i} value={p._id || p.id || `${i}`}>{p.no_po}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Tanggal Keluar</Label>
                  <Input type="date" data-testid="input-tanggal-keluar" value={form.tanggal_keluar} onChange={(e) => setForm({ ...form, tanggal_keluar: e.target.value })} />
                </div>
                {selectedPO && (
                  <div>
                    <Label>Pilih Barang yang Dikirim <span className="text-xs text-[#5C5C5C]">(centang untuk memilih, qty max sesuai PO)</span></Label>
                    <div className="space-y-2 mt-2">
                      {form.items.map((item, idx) => (
                        <div key={idx} className={`p-3 rounded-md border flex gap-3 ${item._selected !== false ? 'bg-[#FAFAFA] border-[#E5E5E5]' : 'bg-gray-100 border-gray-200 opacity-60'}`}>
                          <input
                            type="checkbox"
                            checked={item._selected !== false}
                            onChange={() => toggleItem(idx)}
                            data-testid={`staffing-select-${idx}`}
                            className="mt-2 w-4 h-4 accent-[#8B5A2B]"
                          />
                          {item.gambar_path && <img src={`${API}/files/${item.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" />}
                          <div className="flex-1">
                            <p className="font-medium text-sm">{item.nama_barang}</p>
                            {canSeeCraftsman && <p className="text-xs text-[#5C5C5C]">{item.nama_pengrajin}</p>}
                            <p className="text-xs text-[#5C5C5C]">Total PO: {item._original_qty || 0} • Sudah dikirim: {item.qty_staffed || 0} • Sisa: <strong className="text-[#8B5A2B]">{item._sisa || 0}</strong></p>
                          </div>
                          <div className="w-24">
                            <Label className="text-xs">Qty (max {item._max_qty || 0})</Label>
                            <Input type="number" min={0} max={item._max_qty || 0} data-testid={`staffing-qty-${idx}`} value={item.qty || 0} onChange={(e) => updateQty(idx, e.target.value)} disabled={item._selected === false || (item._max_qty || 0) === 0} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <Button onClick={submit} className="w-full bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="submit-staffing-button">Simpan</Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <Card className="p-4 border border-[#E5E5E5]">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5C5C5C]" />
          <Input placeholder="Cari No PO..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10" data-testid="search-staffing-input" />
        </div>
      </Card>

      <div className="space-y-4" data-testid="staffing-list">
        {items.length === 0 ? (
          <Card className="p-12 text-center border border-dashed border-[#E5E5E5]">
            <Truck className="w-12 h-12 mx-auto text-[#5C5C5C] mb-3" />
            <p className="text-[#5C5C5C]">Belum ada data staffing.</p>
          </Card>
        ) : (
          items.map((st, idx) => (
            <Card key={idx} className="p-6 border border-[#E5E5E5]" data-testid={`staffing-card-${idx}`}>
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
                <div>
                  <h3 className="text-lg font-bold text-[#1A1A1A]">{st.no_po}</h3>
                  <p className="text-sm text-[#5C5C5C]">Tanggal Keluar: {st.tanggal_keluar}</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button variant="outline" size="sm" onClick={() => setPreview(st)} data-testid={`preview-staffing-${idx}`}><Eye className="w-3 h-3 mr-1" /> Preview</Button>
                  {canEditPartial && <Button variant="outline" size="sm" onClick={() => startEdit(st)} data-testid={`edit-staffing-${idx}`}><Edit className="w-3 h-3 mr-1" /> Edit</Button>}
                  {canEditPartial && (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="outline" size="sm" className="text-[#F44336]" data-testid={`delete-staffing-${idx}`}><Trash2 className="w-3 h-3" /></Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Hapus Staffing?</AlertDialogTitle>
                          <AlertDialogDescription>Data staffing ini akan dihapus permanen.</AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Batal</AlertDialogCancel>
                          <AlertDialogAction className="bg-[#F44336]" onClick={() => deleteStaffing(st._id)}>Hapus</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                  <Button variant="outline" size="sm" onClick={() => downloadPDF(st._id)} data-testid={`pdf-staffing-${idx}`}><Download className="w-3 h-3 mr-1" /> PDF</Button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {st.items?.map((item, ii) => (
                  <div key={ii} className="flex gap-3 p-3 bg-[#FAFAFA] rounded-md border border-[#E5E5E5]">
                    {item.gambar_path ? <img src={`${API}/files/${item.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" /> : <div className="w-14 h-14 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-5 h-5 text-[#8B5A2B]" /></div>}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{item.nama_barang}</p>
                      {canSeeCraftsman && <p className="text-xs text-[#5C5C5C] truncate">{item.nama_pengrajin}</p>}
                      <span className="text-xs px-1.5 py-0.5 bg-[#2196F3] text-white rounded inline-block mt-1">Keluar: {item.qty}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ))
        )}
      </div>

      <Dialog open={!!preview} onOpenChange={() => setPreview(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Detail Staffing</DialogTitle></DialogHeader>
          {preview && (
            <div className="space-y-3">
              <p><strong>No PO:</strong> {preview.no_po}</p>
              <p><strong>Tanggal Keluar:</strong> {preview.tanggal_keluar}</p>
              {preview.items?.map((item, i) => (
                <div key={i} className="flex gap-3 p-3 border border-[#E5E5E5] rounded-md">
                  {item.gambar_path && <img src={`${API}/files/${item.gambar_path}`} className="w-20 h-20 object-cover rounded" alt="" />}
                  <div className="flex-1">
                    <p className="font-bold">{item.nama_barang}</p>
                    {canSeeCraftsman && <p className="text-sm text-[#5C5C5C]">{item.nama_pengrajin}</p>}
                    <p className="text-sm">Qty Keluar: <strong>{item.qty}</strong></p>
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
