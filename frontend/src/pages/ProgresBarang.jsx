import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { TrendingUp, Package, CheckCircle2, Download, Printer } from "lucide-react";

export default function ProgresBarang() {
  const { API, canEditPartial, canSeeCraftsman } = useAuth();
  const [progresList, setProgresList] = useState([]);
  const [filterPO, setFilterPO] = useState("all");
  const [filterTanggal, setFilterTanggal] = useState("");

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/progres/by-po`);
      setProgresList(data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, []);

  const updateProgres = async (poId, barangId, key, val, maxQty) => {
    if (!canEditPartial) return;
    const clamped = Math.max(0, parseInt(val) || 0);
    // No max limit for grinda/servis/finishing - only packing is capped by qty_masuk
    const finalVal = key === "packing" ? Math.min(clamped, maxQty) : clamped;
    
    // Find current item to build payload
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
      [key]: finalVal,
    };
    
    try {
      await axios.post(`${API}/progres`, payload);
      // Update local state
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
          <p className="text-[#5C5C5C] mt-1">Tracking produksi per PO: Grinda → Servis → Finishing → Packing</p>
        </div>
        <div className="flex gap-2 flex-wrap items-end">
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
                        { key: "packing", label: `Qty Packing/Ready (max ${item.qty_masuk})`, color: "#4CAF50" },
                      ].map((stage) => (
                        <div key={stage.key} className="p-3 border border-[#E5E5E5] rounded-md bg-white">
                          <Label className="text-xs" style={{ color: stage.color }}>{stage.label}</Label>
                          <Input
                            type="number"
                            min={0}
                            max={stage.key === "packing" ? item.qty_masuk : undefined}
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
