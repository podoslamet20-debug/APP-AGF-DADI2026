import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Download, Package } from "lucide-react";
import * as XLSX from "xlsx";
import { saveAs } from "file-saver";

export default function RekapData() {
  const { API, canSeeCraftsman, isGuest } = useAuth();
  const [rekapPO, setRekapPO] = useState([]);
  const [rekapPengrajin, setRekapPengrajin] = useState([]);
  const [staffing, setStaffing] = useState([]);
  const [filterTanggal, setFilterTanggal] = useState("");

  const load = async () => {
    try {
      const [poRes, pgRes, stRes] = await Promise.all([
        axios.get(`${API}/rekap/all-po`),
        !isGuest ? axios.get(`${API}/rekap/per-pengrajin`) : Promise.resolve({ data: [] }),
        axios.get(`${API}/staffing${filterTanggal ? `?tanggal=${filterTanggal}` : ""}`),
      ]);
      setRekapPO(poRes.data);
      setRekapPengrajin(pgRes.data);
      setStaffing(stRes.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, [filterTanggal]);

  const exportPO = (format) => {
    const data = rekapPO.map(r => ({
      "No PO": r.no_po,
      "Nama Barang": r.nama_barang,
      ...(canSeeCraftsman && { "Pengrajin": r.nama_pengrajin }),
      "Qty PO": r.qty_po,
      "Qty Staffing": r.qty_staffing,
      "Remaining": r.remaining,
    }));
    exportData(data, "rekap-po", format);
  };

  const exportPengrajin = (format) => {
    const data = rekapPengrajin.map(r => ({
      "Pengrajin": r.pengrajin,
      "SPK Qty": r.spk_qty,
      "Diterima": r.masuk_qty,
      "Remaining": r.remaining,
    }));
    exportData(data, "rekap-pengrajin", format);
  };

  const exportStaffing = (format) => {
    const data = [];
    staffing.forEach(st => {
      st.items?.forEach(item => {
        data.push({
          "No PO": st.no_po,
          "Tanggal": st.tanggal_keluar,
          "Nama Barang": item.nama_barang,
          ...(canSeeCraftsman && { "Pengrajin": item.nama_pengrajin }),
          "Qty": item.qty,
        });
      });
    });
    exportData(data, "rekap-staffing", format);
  };

  const exportData = (data, name, format) => {
    if (data.length === 0) return;
    if (format === "csv") {
      const ws = XLSX.utils.json_to_sheet(data);
      const csv = XLSX.utils.sheet_to_csv(ws);
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      saveAs(blob, `${name}.csv`);
    } else {
      const wb = XLSX.utils.book_new();
      const ws = XLSX.utils.json_to_sheet(data);
      XLSX.utils.book_append_sheet(wb, ws, name);
      XLSX.writeFile(wb, `${name}.xlsx`);
    }
  };

  return (
    <div className="space-y-6" data-testid="rekap-page">
      <div>
        <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Data</h1>
        <p className="text-[#5C5C5C] mt-1">Laporan komprehensif untuk semua data</p>
      </div>

      <Tabs defaultValue="po" className="w-full">
        <TabsList className="grid grid-cols-3 w-full max-w-md">
          <TabsTrigger value="po" data-testid="tab-rekap-po">Rekap PO</TabsTrigger>
          <TabsTrigger value="pengrajin" data-testid="tab-rekap-pengrajin" disabled={isGuest}>Per Pengrajin</TabsTrigger>
          <TabsTrigger value="staffing" data-testid="tab-rekap-staffing">Staffing</TabsTrigger>
        </TabsList>

        <TabsContent value="po" className="mt-4">
          <Card className="p-6 border border-[#E5E5E5]">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
              <h2 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Semua PO</h2>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => exportPO("csv")} data-testid="export-po-csv"><Download className="w-3 h-3 mr-1" /> CSV</Button>
                <Button variant="outline" size="sm" onClick={() => exportPO("xlsx")} data-testid="export-po-xlsx"><Download className="w-3 h-3 mr-1" /> Excel</Button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#F0E6D6] text-[#1A1A1A]">
                  <tr>
                    <th className="p-2 text-left">Foto</th>
                    <th className="p-2 text-left">No PO</th>
                    <th className="p-2 text-left">Barang</th>
                    {canSeeCraftsman && <th className="p-2 text-left">Pengrajin</th>}
                    <th className="p-2 text-right">Qty PO</th>
                    <th className="p-2 text-right">Staffing</th>
                    <th className="p-2 text-right">Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {rekapPO.map((r, i) => (
                    <tr key={i} className="border-b border-[#E5E5E5]" data-testid={`rekap-po-row-${i}`}>
                      <td className="p-2">
                        {r.gambar_path ? <img src={`${API}/files/${r.gambar_path}`} className="w-10 h-10 object-cover rounded" alt="" /> : <div className="w-10 h-10 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-4 h-4 text-[#8B5A2B]" /></div>}
                      </td>
                      <td className="p-2">{r.no_po}</td>
                      <td className="p-2">{r.nama_barang}</td>
                      {canSeeCraftsman && <td className="p-2">{r.nama_pengrajin}</td>}
                      <td className="p-2 text-right">{r.qty_po}</td>
                      <td className="p-2 text-right">{r.qty_staffing}</td>
                      <td className="p-2 text-right"><span className={`font-medium ${r.remaining > 0 ? 'text-[#F44336]' : 'text-[#4CAF50]'}`}>{r.remaining}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rekapPO.length === 0 && <p className="text-center text-[#5C5C5C] py-8">Belum ada data</p>}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="pengrajin" className="mt-4">
          <Card className="p-6 border border-[#E5E5E5]">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
              <h2 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Per Pengrajin</h2>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => exportPengrajin("csv")} data-testid="export-pengrajin-csv"><Download className="w-3 h-3 mr-1" /> CSV</Button>
                <Button variant="outline" size="sm" onClick={() => exportPengrajin("xlsx")} data-testid="export-pengrajin-xlsx"><Download className="w-3 h-3 mr-1" /> Excel</Button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#F0E6D6]">
                  <tr>
                    <th className="p-2 text-left">Pengrajin</th>
                    <th className="p-2 text-right">SPK Qty</th>
                    <th className="p-2 text-right">Diterima</th>
                    <th className="p-2 text-right">Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {rekapPengrajin.map((r, i) => (
                    <tr key={i} className="border-b border-[#E5E5E5]" data-testid={`rekap-pengrajin-row-${i}`}>
                      <td className="p-2 font-medium">{r.pengrajin}</td>
                      <td className="p-2 text-right">{r.spk_qty}</td>
                      <td className="p-2 text-right">{r.masuk_qty}</td>
                      <td className="p-2 text-right"><span className={`font-medium ${r.remaining > 0 ? 'text-[#F44336]' : 'text-[#4CAF50]'}`}>{r.remaining}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rekapPengrajin.length === 0 && <p className="text-center text-[#5C5C5C] py-8">Belum ada data</p>}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="staffing" className="mt-4">
          <Card className="p-6 border border-[#E5E5E5]">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
              <h2 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Staffing</h2>
              <div className="flex gap-2 flex-wrap items-end">
                <div>
                  <Label className="text-xs">Filter Tanggal</Label>
                  <Input type="date" value={filterTanggal} onChange={(e) => setFilterTanggal(e.target.value)} data-testid="filter-tanggal-staffing" />
                </div>
                <Button variant="outline" size="sm" onClick={() => exportStaffing("csv")} data-testid="export-staffing-csv"><Download className="w-3 h-3 mr-1" /> CSV</Button>
                <Button variant="outline" size="sm" onClick={() => exportStaffing("xlsx")} data-testid="export-staffing-xlsx"><Download className="w-3 h-3 mr-1" /> Excel</Button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#F0E6D6]">
                  <tr>
                    <th className="p-2 text-left">Foto</th>
                    <th className="p-2 text-left">No PO</th>
                    <th className="p-2 text-left">Tanggal</th>
                    <th className="p-2 text-left">Barang</th>
                    {canSeeCraftsman && <th className="p-2 text-left">Pengrajin</th>}
                    <th className="p-2 text-right">Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {staffing.flatMap((st, si) => (st.items || []).map((item, ii) => (
                    <tr key={`${si}-${ii}`} className="border-b border-[#E5E5E5]" data-testid={`rekap-staffing-row-${si}-${ii}`}>
                      <td className="p-2">
                        {item.gambar_path ? <img src={`${API}/files/${item.gambar_path}`} className="w-10 h-10 object-cover rounded" alt="" /> : <div className="w-10 h-10 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-4 h-4 text-[#8B5A2B]" /></div>}
                      </td>
                      <td className="p-2">{st.no_po}</td>
                      <td className="p-2">{st.tanggal_keluar}</td>
                      <td className="p-2">{item.nama_barang}</td>
                      {canSeeCraftsman && <td className="p-2">{item.nama_pengrajin}</td>}
                      <td className="p-2 text-right font-medium">{item.qty}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
              {staffing.length === 0 && <p className="text-center text-[#5C5C5C] py-8">Belum ada data</p>}
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
