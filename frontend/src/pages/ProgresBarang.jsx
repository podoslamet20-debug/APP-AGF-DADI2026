import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { TrendingUp, Package, CheckCircle2 } from "lucide-react";

export default function ProgresBarang() {
  const { API, canEditPartial, canSeeCraftsman } = useAuth();
  const [barangMasuk, setBarangMasuk] = useState([]);
  const [progresMap, setProgresMap] = useState({});

  const load = async () => {
    try {
      const [bmRes, prRes] = await Promise.all([axios.get(`${API}/barang-masuk`), axios.get(`${API}/progres`)]);
      setBarangMasuk(bmRes.data);
      const map = {};
      prRes.data.forEach(p => {
        map[`${p.barang_masuk_id}_${p.item_id}`] = p;
      });
      setProgresMap(map);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, []);

  const getProgres = (bmId, itemId) => progresMap[`${bmId}_${itemId}`] || { grinda: 0, servis: 0, finishing: 0, packing: 0 };

  const updateProgres = async (bmId, itemId, key, val) => {
    if (!canEditPartial) return;
    const current = getProgres(bmId, itemId);
    const updated = { ...current, barang_masuk_id: bmId, item_id: itemId, [key]: parseInt(val) || 0 };
    try {
      await axios.post(`${API}/progres`, updated);
      setProgresMap({ ...progresMap, [`${bmId}_${itemId}`]: updated });
    } catch (e) { toast.error("Gagal update"); }
  };

  const allItems = [];
  barangMasuk.forEach(bm => {
    bm.items?.forEach(item => {
      const bmId = bm._id || bm.id || `${bm.no_po}_${bm.tanggal_masuk}`;
      const itemId = item.barang_id;
      const progres = getProgres(bmId, itemId);
      allItems.push({
        bmId,
        itemId,
        no_po: bm.no_po,
        ...item,
        progres,
        isComplete: progres.packing >= item.qty_diterima,
      });
    });
  });

  return (
    <div className="space-y-6" data-testid="progres-page">
      <div>
        <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Progres Barang</h1>
        <p className="text-[#5C5C5C] mt-1">Tracking progres produksi: Grinda → Servis → Finishing → Packing</p>
      </div>

      <div className="space-y-4" data-testid="progres-list">
        {allItems.length === 0 ? (
          <Card className="p-12 text-center border border-dashed border-[#E5E5E5]">
            <TrendingUp className="w-12 h-12 mx-auto text-[#5C5C5C] mb-3" />
            <p className="text-[#5C5C5C]">Belum ada barang masuk untuk ditrack.</p>
          </Card>
        ) : (
          allItems.map((item, idx) => (
            <Card key={idx} className="p-6 border border-[#E5E5E5]" data-testid={`progres-card-${idx}`}>
              <div className="flex flex-col md:flex-row gap-4 mb-4">
                {item.gambar_path ? (
                  <img src={`${API}/files/${item.gambar_path}`} className="w-full md:w-32 h-32 object-cover rounded-md" alt="" />
                ) : (
                  <div className="w-full md:w-32 h-32 bg-[#F0E6D6] rounded-md flex items-center justify-center">
                    <Package className="w-10 h-10 text-[#8B5A2B]" />
                  </div>
                )}
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <h3 className="text-lg font-bold text-[#1A1A1A]">{item.nama_barang}</h3>
                    {item.isComplete && (
                      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 bg-[#4CAF50] text-white rounded-full">
                        <CheckCircle2 className="w-3 h-3" /> KOMPLIT
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-[#5C5C5C]">No PO: {item.no_po}</p>
                  {canSeeCraftsman && <p className="text-sm text-[#5C5C5C]">Pengrajin: {item.nama_pengrajin}</p>}
                  <p className="text-sm mt-1">Qty Barang Masuk: <strong className="text-[#8B5A2B]">{item.qty_diterima}</strong></p>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { key: "grinda", label: "Grinda", color: "#FFC107" },
                  { key: "servis", label: "Servis", color: "#2196F3" },
                  { key: "finishing", label: "Finishing", color: "#9C27B0" },
                  { key: "packing", label: "Qty Packing/Ready", color: "#4CAF50" },
                ].map((stage) => (
                  <div key={stage.key} className="p-3 border border-[#E5E5E5] rounded-md">
                    <Label className="text-xs" style={{ color: stage.color }}>{stage.label}</Label>
                    <Input
                      type="number"
                      data-testid={`progres-${stage.key}-${idx}`}
                      value={item.progres[stage.key] || 0}
                      onChange={(e) => updateProgres(item.bmId, item.itemId, stage.key, e.target.value)}
                      disabled={!canEditPartial}
                      className="mt-1"
                    />
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
