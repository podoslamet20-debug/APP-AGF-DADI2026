import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Package, ShoppingCart, PackageOpen, Truck, FileText, TrendingUp, Trophy, Hammer, Calendar, BellRing, PackageCheck, ChevronDown, ChevronUp, Check, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function Dashboard() {
  const { API, user, isGuest, isAdmin } = useAuth();
  const [stats, setStats] = useState({ barang: 0, po: 0, barangMasuk: 0, staffing: 0, spk: 0 });
  const [kinerjaMonth, setKinerjaMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [kinerja, setKinerja] = useState([]);
  const [poReady, setPoReady] = useState({ count: 0, pos: [] });
  const [poReadyOpen, setPoReadyOpen] = useState(true);
  const [expandedPo, setExpandedPo] = useState(null);
  const [markingId, setMarkingId] = useState(null);

  const loadPoReady = async () => {
    try {
      const { data } = await axios.get(`${API}/dashboard/po-ready`);
      setPoReady({ count: data.count || 0, pos: data.pos || [] });
    } catch (e) { console.error("Failed to load PO ready:", e); }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const [barang, po, bm, st, spk] = await Promise.all([
          axios.get(`${API}/barang`),
          axios.get(`${API}/po`),
          axios.get(`${API}/barang-masuk`),
          axios.get(`${API}/staffing`),
          axios.get(`${API}/spk`),
        ]);
        setStats({ barang: barang.data.length, po: po.data.length, barangMasuk: bm.data.length, staffing: st.data.length, spk: spk.data.length });
      } catch (e) { console.error(e); }
    };
    load();
    loadPoReady();
  }, [API, loadPoReady]);

  const handleMarkShipped = async (poId, noPo) => {
    if (!window.confirm(`Tandai PO "${noPo}" sebagai sudah dikirim? PO akan hilang dari daftar notifikasi ini.`)) return;
    setMarkingId(poId);
    try {
      await axios.post(`${API}/dashboard/po-ready/${poId}/mark-shipped`);
      toast.success(`PO ${noPo} ditandai sudah dikirim`);
      await loadPoReady();
    } catch (e) {
      toast.error("Gagal menandai PO: " + (e.response?.data?.detail || e.message));
    } finally {
      setMarkingId(null);
    }
  };

  useEffect(() => {
    if (isGuest) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/dashboard/kinerja-pengrajin?month=${kinerjaMonth}`);
        setKinerja(data.pengrajin || []);
      } catch (e) { console.error(e); }
    })();
  }, [API, kinerjaMonth, isGuest]);

  const cards = [
    { label: "Database Barang", value: stats.barang, icon: Package, color: "#8B5A2B", link: "/barang" },
    { label: "Total PO", value: stats.po, icon: ShoppingCart, color: "#4CAF50", link: "/po" },
    { label: "Barang Masuk", value: stats.barangMasuk, icon: PackageOpen, color: "#FFC107", link: "/barang-masuk" },
    { label: "Staffing", value: stats.staffing, icon: Truck, color: "#2196F3", link: "/staffing" },
    { label: "Total SPK", value: stats.spk, icon: FileText, color: "#9C27B0", link: "/spk" },
    { label: "Progres Barang", value: "Lihat", icon: TrendingUp, color: "#F44336", link: "/progres" },
  ];

  const badgeColor = { "MVP": "bg-[#FFD700] text-[#5C4400]", "Produktif": "bg-[#4CAF50] text-white", "Perlu Improvement": "bg-[#FFC107] text-white", "Belum ada aktivitas": "bg-[#E5E5E5] text-[#5C5C5C]" };
  const maxSelesai = Math.max(1, ...kinerja.map(k => k.qty_selesai));

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div>
        <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Dashboard</h1>
        <p className="text-[#5C5C5C] mt-1">Ringkasan data furniture management system</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map((c) => (
          <Link to={c.link} key={c.label}>
            <Card className="p-6 hover:shadow-md transition-shadow duration-200 border border-[#E5E5E5] cursor-pointer" data-testid={`dashboard-card-${c.label.toLowerCase().replace(/\s+/g, '-')}`}>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-[#5C5C5C] font-medium">{c.label}</p>
                  <p className="text-3xl font-bold text-[#1A1A1A] mt-1" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>{c.value}</p>
                </div>
                <div className="w-12 h-12 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${c.color}20` }}>
                  <c.icon className="w-6 h-6" style={{ color: c.color }} />
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      {/* PO Ready-to-Ship Notification */}
      {poReady.count > 0 && (
        <Card className="border border-[#4CAF50] bg-[#4CAF5010]" data-testid="po-ready-notif-card">
          <div className="p-4 sm:p-5 flex items-start gap-3">
            <div className="w-10 h-10 rounded-full bg-[#4CAF50] flex items-center justify-center flex-shrink-0 animate-pulse">
              <BellRing className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div>
                  <h3 className="text-lg font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>
                    <span className="text-[#2E7D32]">{poReady.count}</span> PO Siap Kirim! 🚚
                  </h3>
                  <p className="text-sm text-[#5C5C5C]">Semua barang sudah selesai stage <strong>Packing</strong> — siap dikirim ke pelanggan.</p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setPoReadyOpen(!poReadyOpen)} data-testid="po-ready-toggle" className="text-[#2E7D32]">
                  {poReadyOpen ? (<><ChevronUp className="w-4 h-4 mr-1" /> Sembunyikan</>) : (<><ChevronDown className="w-4 h-4 mr-1" /> Lihat Detail</>)}
                </Button>
              </div>

              {poReadyOpen && (
                <div className="mt-4 space-y-2" data-testid="po-ready-list">
                  {poReady.pos.map((p) => {
                    const isExpanded = expandedPo === p.po_id;
                    return (
                      <div key={p.po_id} className="bg-white border border-[#4CAF50]/40 rounded-md overflow-hidden" data-testid={`po-ready-row-${p.no_po}`}>
                        <div className="p-3 flex items-center gap-3 flex-wrap">
                          <PackageCheck className="w-5 h-5 text-[#4CAF50] flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <p className="font-semibold text-[#1A1A1A]">{p.no_po}</p>
                            <p className="text-xs text-[#5C5C5C]">
                              {p.total_items} barang · {p.total_qty} qty siap kirim
                              {p.created_at ? ` · dibuat ${new Date(p.created_at).toLocaleDateString('id-ID', { day:'2-digit', month:'short', year:'numeric' })}` : ''}
                            </p>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <Button size="sm" variant="outline" onClick={() => setExpandedPo(isExpanded ? null : p.po_id)} data-testid={`po-ready-expand-${p.no_po}`}>
                              {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                              Detail
                            </Button>
                            <Link to="/po">
                              <Button size="sm" variant="outline" className="text-[#8B5A2B] border-[#8B5A2B]/40" data-testid={`po-ready-view-${p.no_po}`}>Buka PO</Button>
                            </Link>
                            {isAdmin && (
                              <Button size="sm" className="bg-[#4CAF50] hover:bg-[#2E7D32] text-white" disabled={markingId === p.po_id} onClick={() => handleMarkShipped(p.po_id, p.no_po)} data-testid={`po-ready-mark-shipped-${p.no_po}`}>
                                <Check className="w-4 h-4 mr-1" />
                                {markingId === p.po_id ? "..." : "Tandai Dikirim"}
                              </Button>
                            )}
                          </div>
                        </div>
                        {isExpanded && (
                          <div className="border-t border-[#E5E5E5] bg-[#FAFAFA] px-3 py-2" data-testid={`po-ready-items-${p.no_po}`}>
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-[#5C5C5C]">
                                  <th className="text-left py-1 font-medium">Barang</th>
                                  <th className="text-right py-1 font-medium">Qty PO</th>
                                  <th className="text-right py-1 font-medium">Qty Siap</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(p.items || []).map((it, idx) => (
                                  <tr key={idx} className="border-t border-[#E5E5E5]/60">
                                    <td className="py-1 text-[#1A1A1A]">{it.nama_barang}</td>
                                    <td className="py-1 text-right text-[#1A1A1A]">{it.qty}</td>
                                    <td className="py-1 text-right font-semibold text-[#2E7D32]">{it.qty_ready}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {!isGuest && (
        <Card className="p-6 border border-[#E5E5E5]" data-testid="kinerja-pengrajin-card">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Trophy className="w-6 h-6 text-[#FFD700]" />
              <h2 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Kinerja Pengrajin</h2>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[#5C5C5C]" />
              <Label htmlFor="month-input" className="text-sm text-[#5C5C5C]">Bulan:</Label>
              <Input id="month-input" type="month" value={kinerjaMonth} onChange={(e) => setKinerjaMonth(e.target.value)} className="w-40" data-testid="kinerja-month-picker" />
            </div>
          </div>
          <p className="text-xs text-[#5C5C5C] mb-4">Ranking berdasarkan qty <strong>Packing</strong> bulan tsb + on-time rate SPK deadline di bulan tsb.</p>
          {kinerja.length === 0 ? (
            <div className="text-center py-8 text-[#5C5C5C]"><Hammer className="w-8 h-8 mx-auto mb-2 opacity-50" /> Belum ada data kinerja untuk bulan ini.</div>
          ) : (
            <div className="space-y-2" data-testid="kinerja-list">
              {kinerja.slice(0, 10).map((k) => (
                <div key={k.pengrajin_id} className="p-3 border border-[#E5E5E5] rounded-md hover:bg-[#FAFAFA]" data-testid={`kinerja-row-${k.rank}`}>
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-[#F0E6D6] flex items-center justify-center font-bold text-[#8B5A2B]" data-testid={`kinerja-rank-${k.rank}`}>#{k.rank}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-medium text-[#1A1A1A]">{k.pengrajin_nama}</p>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${badgeColor[k.badge] || 'bg-gray-200'}`} data-testid={`kinerja-badge-${k.rank}`}>{k.badge}</span>
                      </div>
                      <div className="mt-1 h-2 bg-[#F0E6D6] rounded-full overflow-hidden">
                        <div className="h-full bg-[#8B5A2B] transition-all" style={{ width: `${(k.qty_selesai / maxSelesai) * 100}%` }} />
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-lg font-bold text-[#1A1A1A]">{k.qty_selesai}</p>
                      <p className="text-[10px] text-[#5C5C5C]">Packing bulan ini</p>
                    </div>
                    <div className="text-right flex-shrink-0 hidden md:block w-24">
                      <p className="text-sm font-medium">
                        {k.on_time_rate !== null ? (
                          <span className={k.on_time_rate >= 80 ? "text-[#4CAF50]" : k.on_time_rate >= 50 ? "text-[#FFC107]" : "text-[#F44336]"}>{k.on_time_rate}%</span>
                        ) : <span className="text-[#5C5C5C]">-</span>}
                      </p>
                      <p className="text-[10px] text-[#5C5C5C]">On-time ({k.on_time_count}/{k.total_spk_month})</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <Card className="p-6 border border-[#E5E5E5]">
        <h2 className="text-xl font-bold text-[#1A1A1A] mb-4" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Akses Cepat</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {cards.slice(0, 4).map((c) => (
            <Link key={c.link} to={c.link}>
              <div className="p-4 border border-[#E5E5E5] rounded-md hover:border-[#8B5A2B] hover:bg-[#F0E6D6]/30 transition-colors duration-150 text-center">
                <c.icon className="w-6 h-6 mx-auto mb-2 text-[#8B5A2B]" />
                <p className="text-sm font-medium text-[#1A1A1A]">{c.label}</p>
              </div>
            </Link>
          ))}
        </div>
      </Card>

      {user?.role === "guest" && (
        <Card className="p-4 bg-[#FFC10720] border border-[#FFC107]">
          <p className="text-sm text-[#1A1A1A]"><strong>Mode Tamu:</strong> Anda hanya bisa melihat data. Harga dan nama pengrajin disembunyikan.</p>
        </Card>
      )}
      {user?.role === "staff" && (
        <Card className="p-4 bg-[#4CAF5020] border border-[#4CAF50]">
          <p className="text-sm text-[#1A1A1A]"><strong>Mode Staff:</strong> Anda bisa mengedit barang masuk, staffing, dan progres. Harga disembunyikan.</p>
        </Card>
      )}
    </div>
  );
}
