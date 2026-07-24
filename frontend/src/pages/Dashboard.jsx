import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Package, ShoppingCart, PackageOpen, Truck, FileText, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

export default function Dashboard() {
  const { API, user } = useAuth();
  const [stats, setStats] = useState({ barang: 0, po: 0, barangMasuk: 0, staffing: 0, spk: 0 });

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
        setStats({
          barang: barang.data.length,
          po: po.data.length,
          barangMasuk: bm.data.length,
          staffing: st.data.length,
          spk: spk.data.length,
        });
      } catch (e) {
        console.error(e);
      }
    };
    load();
  }, [API]);

  const cards = [
    { label: "Database Barang", value: stats.barang, icon: Package, color: "#8B5A2B", link: "/barang" },
    { label: "Total PO", value: stats.po, icon: ShoppingCart, color: "#4CAF50", link: "/po" },
    { label: "Barang Masuk", value: stats.barangMasuk, icon: PackageOpen, color: "#FFC107", link: "/barang-masuk" },
    { label: "Staffing", value: stats.staffing, icon: Truck, color: "#2196F3", link: "/staffing" },
    { label: "Total SPK", value: stats.spk, icon: FileText, color: "#9C27B0", link: "/spk" },
    { label: "Progres Barang", value: "Lihat", icon: TrendingUp, color: "#F44336", link: "/progres" },
  ];

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
