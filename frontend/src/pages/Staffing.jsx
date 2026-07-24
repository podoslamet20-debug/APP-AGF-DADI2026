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
import { Plus, Truck, Package } from "lucide-react";

export default function Staffing() {
  const { API, canEditPartial, canSeeCraftsman } = useAuth();
  const [items, setItems] = useState([]);
  const [pos, setPos] = useState([]);
  const [open, setOpen] = useState(false);
  const [selectedPO, setSelectedPO] = useState(null);
  const [form, setForm] = useState({ po_id: "", tanggal_keluar: "", items: [] });

  const load = async () => {
    try {
      const [stRes, poRes] = await Promise.all([axios.get(`${API}/staffing`), axios.get(`${API}/po`)]);
      setItems(stRes.data);
      setPos(poRes.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, []);

  const selectPO = (poId) => {
    const po = pos.find(p => (p._id || p.id) === poId);
    if (!po) return;
    setSelectedPO(po);
    setForm({ ...form, po_id: poId, items: po.items.map(i => ({ ...i, qty: 0 })) });
  };

  const updateQty = (idx, qty) => {
    const items = [...form.items];
    items[idx].qty = parseInt(qty) || 0;
    setForm({ ...form, items });
  };

  const submit = async () => {
    if (!form.po_id || !form.tanggal_keluar) {
      toast.error("Isi semua field wajib");
      return;
    }
    try {
      await axios.post(`${API}/staffing`, form);
      toast.success("Staffing berhasil dicatat");
      setOpen(false);
      setForm({ po_id: "", tanggal_keluar: "", items: [] });
      setSelectedPO(null);
      load();
    } catch (e) {
      toast.error("Gagal: " + (e.response?.data?.detail || ""));
    }
  };

  return (
    <div className="space-y-6" data-testid="staffing-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Staffing</h1>
          <p className="text-[#5C5C5C] mt-1">Catat barang keluar/dikirim ke customer</p>
        </div>
        {canEditPartial && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-staffing-button"><Plus className="w-4 h-4 mr-2" /> Catat Staffing</Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>Catat Staffing</DialogTitle></DialogHeader>
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
                    <Label>Barang dari PO</Label>
                    <div className="space-y-2 mt-2">
                      {form.items.map((item, idx) => (
                        <div key={idx} className="p-3 bg-[#FAFAFA] rounded-md border border-[#E5E5E5] flex gap-3">
                          {item.gambar_path && <img src={`${API}/files/${item.gambar_path}`} className="w-14 h-14 object-cover rounded" alt="" />}
                          <div className="flex-1">
                            <p className="font-medium text-sm">{item.nama_barang}</p>
                            {canSeeCraftsman && <p className="text-xs text-[#5C5C5C]">{item.nama_pengrajin}</p>}
                            <p className="text-xs text-[#5C5C5C]">Total PO: {item.qty}</p>
                          </div>
                          <div className="w-24">
                            <Label className="text-xs">Qty Keluar</Label>
                            <Input type="number" data-testid={`staffing-qty-${idx}`} value={item.qty || 0} onChange={(e) => updateQty(idx, e.target.value)} />
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

      <div className="space-y-4" data-testid="staffing-list">
        {items.length === 0 ? (
          <Card className="p-12 text-center border border-dashed border-[#E5E5E5]">
            <Truck className="w-12 h-12 mx-auto text-[#5C5C5C] mb-3" />
            <p className="text-[#5C5C5C]">Belum ada data staffing.</p>
          </Card>
        ) : (
          items.map((st, idx) => (
            <Card key={idx} className="p-6 border border-[#E5E5E5]" data-testid={`staffing-card-${idx}`}>
              <div className="mb-4">
                <h3 className="text-lg font-bold text-[#1A1A1A]">{st.no_po}</h3>
                <p className="text-sm text-[#5C5C5C]">Tanggal Keluar: {st.tanggal_keluar}</p>
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
    </div>
  );
}
