import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Download, Package, Printer } from "lucide-react";
import * as XLSX from "xlsx";
import { saveAs } from "file-saver";

export default function RekapData() {
  const { API, canSeeCraftsman, isGuest } = useAuth();
  const [rekapPO, setRekapPO] = useState([]);
  const [rekapPengrajin, setRekapPengrajin] = useState([]);
  const [rekapBarang, setRekapBarang] = useState([]);
  const [rekapProgres, setRekapProgres] = useState([]);
  const [staffing, setStaffing] = useState([]);
  const [staffingSummary, setStaffingSummary] = useState([]);
  const [poList, setPoList] = useState([]);
  const [filterTanggal, setFilterTanggal] = useState("");
  const [filterNoPO, setFilterNoPO] = useState("all");

  const load = async () => {
    try {
      const [poRes, pgRes, brRes, prRes, stRes, poListRes, sumRes] = await Promise.all([
        axios.get(`${API}/rekap/all-po${filterNoPO !== "all" ? `?no_po=${filterNoPO}` : ""}`),
        !isGuest ? axios.get(`${API}/rekap/per-pengrajin`) : Promise.resolve({ data: [] }),
        axios.get(`${API}/rekap/per-barang`),
        axios.get(`${API}/rekap/progres`),
        axios.get(`${API}/staffing${filterTanggal ? `?tanggal=${filterTanggal}` : ""}`),
        axios.get(`${API}/po`),
        axios.get(`${API}/rekap/staffing-summary${filterNoPO !== "all" ? `?no_po=${filterNoPO}` : ""}`),
      ]);
      setRekapPO(poRes.data);
      setRekapPengrajin(pgRes.data);
      setRekapBarang(brRes.data);
      setRekapProgres(prRes.data);
      setStaffing(stRes.data);
      setPoList(poListRes.data);
      setStaffingSummary(sumRes.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { load(); }, [filterTanggal, filterNoPO]);

  const exportPO = (format) => {
    const data = rekapPO.map(r => ({
      "No PO": r.no_po,
      "Nama Barang": r.nama_barang,
      ...(canSeeCraftsman && { "Pengrajin": r.nama_pengrajin }),
      "Qty PO": r.qty_po,
      "Qty Staffing": r.qty_staffing,
      "Kurang Kirim": r.kurang_kirim,
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
    const data = staffingSummary.map(r => ({
      "No PO": r.no_po,
      "Nama Barang": r.nama_barang,
      "Qty PO": r.qty_po,
      "Qty Staffing": r.qty_staffing,
      "Kurang Kirim": r.kurang_kirim,
    }));
    exportData(data, "rekap-staffing", format);
  };

  const exportBarang = (format) => {
    const data = rekapBarang.map(r => ({
      "Nama Barang": r.nama_barang,
      ...(canSeeCraftsman && { "Pengrajin": r.nama_pengrajin }),
      "Qty Masuk": r.qty_masuk,
      "Qty Packing": r.qty_packing,
      "Kurang": r.kurang,
    }));
    exportData(data, "rekap-per-barang", format);
  };

  const printPage = () => window.print();

  const exportProgres = (format) => {
    const data = rekapProgres.map(r => ({
      "No PO": r.no_po,
      "Nama Barang": r.nama_barang,
      ...(canSeeCraftsman && { "Pengrajin": r.nama_pengrajin }),
      "Qty Masuk": r.qty_masuk,
      "Grinda": r.grinda,
      "Servis": r.servis,
      "Finishing": r.finishing,
      "Packing/Ready": r.packing,
      "Status": r.komplit ? "KOMPLIT" : "PROSES",
    }));
    exportData(data, "rekap-progres", format);
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
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 print:hidden">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Data</h1>
          <p className="text-[#5C5C5C] mt-1">Laporan komprehensif untuk semua data</p>
        </div>
        <Button variant="outline" onClick={printPage} data-testid="print-rekap"><Printer className="w-4 h-4 mr-2" /> Print</Button>
      </div>

      <div className="hidden print:block print-header mb-4">
        <h1 className="text-2xl font-bold">AGFDATA - Rekap Data</h1>
      </div>

      <Tabs defaultValue="po" className="w-full">
        <TabsList className="grid grid-cols-3 md:grid-cols-5 w-full">
          <TabsTrigger value="po" data-testid="tab-rekap-po">Rekap PO</TabsTrigger>
          <TabsTrigger value="barang" data-testid="tab-rekap-barang">Per Barang</TabsTrigger>
          <TabsTrigger value="progres" data-testid="tab-rekap-progres">Progres</TabsTrigger>
          <TabsTrigger value="pengrajin" data-testid="tab-rekap-pengrajin" disabled={isGuest}>Per Pengrajin</TabsTrigger>
          <TabsTrigger value="staffing" data-testid="tab-rekap-staffing">Staffing</TabsTrigger>
        </TabsList>

        <TabsContent value="po" className="mt-4">
          <Card className="p-6 border border-[#E5E5E5]">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
              <h2 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Semua PO</h2>
              <div className="flex gap-2 flex-wrap items-end">
                <div>
                  <Label className="text-xs">Filter No PO</Label>
                  <Select value={filterNoPO} onValueChange={setFilterNoPO}>
                    <SelectTrigger className="w-48" data-testid="filter-no-po"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Semua PO</SelectItem>
                      {poList.map((p, i) => <SelectItem key={i} value={p.no_po}>{p.no_po}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
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
                    <th className="p-2 text-right">Kurang Kirim</th>
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
                      <td className="p-2 text-right"><span className={`font-medium ${r.kurang_kirim > 0 ? 'text-[#F44336]' : 'text-[#4CAF50]'}`}>{r.kurang_kirim}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rekapPO.length === 0 && <p className="text-center text-[#5C5C5C] py-8">Belum ada data</p>}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="barang" className="mt-4">
          <Card className="p-6 border border-[#E5E5E5]">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
              <h2 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Per Barang</h2>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => exportBarang("csv")} data-testid="export-barang-csv"><Download className="w-3 h-3 mr-1" /> CSV</Button>
                <Button variant="outline" size="sm" onClick={() => exportBarang("xlsx")} data-testid="export-barang-xlsx"><Download className="w-3 h-3 mr-1" /> Excel</Button>
              </div>
            </div>
            <p className="text-xs text-[#5C5C5C] mb-3">Barang Masuk dikurangi Progres Packing</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#F0E6D6]">
                  <tr>
                    <th className="p-2 text-left">Foto</th>
                    <th className="p-2 text-left">Nama Barang</th>
                    {canSeeCraftsman && <th className="p-2 text-left">Pengrajin</th>}
                    <th className="p-2 text-right">Qty Masuk</th>
                    <th className="p-2 text-right">Qty Packing</th>
                    <th className="p-2 text-right">Kurang</th>
                  </tr>
                </thead>
                <tbody>
                  {rekapBarang.map((r, i) => (
                    <tr key={i} className="border-b border-[#E5E5E5]" data-testid={`rekap-barang-row-${i}`}>
                      <td className="p-2">{r.gambar_path ? <img src={`${API}/files/${r.gambar_path}`} className="w-10 h-10 object-cover rounded" alt="" /> : <div className="w-10 h-10 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-4 h-4 text-[#8B5A2B]" /></div>}</td>
                      <td className="p-2 font-medium">{r.nama_barang}</td>
                      {canSeeCraftsman && <td className="p-2">{r.nama_pengrajin}</td>}
                      <td className="p-2 text-right">{r.qty_masuk}</td>
                      <td className="p-2 text-right">{r.qty_packing}</td>
                      <td className="p-2 text-right"><span className={`font-medium ${r.kurang > 0 ? 'text-[#F44336]' : 'text-[#4CAF50]'}`}>{r.kurang}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rekapBarang.length === 0 && <p className="text-center text-[#5C5C5C] py-8">Belum ada data</p>}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="progres" className="mt-4">
          <Card className="p-6 border border-[#E5E5E5]">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
              <h2 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Rekap Progres Barang</h2>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => exportProgres("csv")} data-testid="export-progres-csv"><Download className="w-3 h-3 mr-1" /> CSV</Button>
                <Button variant="outline" size="sm" onClick={() => exportProgres("xlsx")} data-testid="export-progres-xlsx"><Download className="w-3 h-3 mr-1" /> Excel</Button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#F0E6D6]">
                  <tr>
                    <th className="p-2 text-left">Foto</th>
                    <th className="p-2 text-left">No PO</th>
                    <th className="p-2 text-left">Barang</th>
                    {canSeeCraftsman && <th className="p-2 text-left">Pengrajin</th>}
                    <th className="p-2 text-right">Masuk</th>
                    <th className="p-2 text-right">Grinda</th>
                    <th className="p-2 text-right">Servis</th>
                    <th className="p-2 text-right">Finishing</th>
                    <th className="p-2 text-right">Packing/Ready</th>
                    <th className="p-2 text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rekapProgres.map((r, i) => (
                    <tr key={i} className="border-b border-[#E5E5E5]" data-testid={`rekap-progres-row-${i}`}>
                      <td className="p-2">{r.gambar_path ? <img src={`${API}/files/${r.gambar_path}`} className="w-10 h-10 object-cover rounded" alt="" /> : <div className="w-10 h-10 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-4 h-4 text-[#8B5A2B]" /></div>}</td>
                      <td className="p-2">{r.no_po}</td>
                      <td className="p-2 font-medium">{r.nama_barang}</td>
                      {canSeeCraftsman && <td className="p-2">{r.nama_pengrajin}</td>}
                      <td className="p-2 text-right">{r.qty_masuk}</td>
                      <td className="p-2 text-right">{r.grinda}</td>
                      <td className="p-2 text-right">{r.servis}</td>
                      <td className="p-2 text-right">{r.finishing}</td>
                      <td className="p-2 text-right font-medium">{r.packing}</td>
                      <td className="p-2 text-center">{r.komplit ? <span className="text-xs px-2 py-0.5 bg-[#4CAF50] text-white rounded">KOMPLIT</span> : <span className="text-xs px-2 py-0.5 bg-[#FFC107] text-white rounded">PROSES</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rekapProgres.length === 0 && <p className="text-center text-[#5C5C5C] py-8">Belum ada data</p>}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="pengrajin" className="mt-4">          <Card className="p-6 border border-[#E5E5E5]">
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
                <Button variant="outline" size="sm" onClick={() => exportStaffing("csv")} data-testid="export-staffing-csv"><Download className="w-3 h-3 mr-1" /> CSV</Button>
                <Button variant="outline" size="sm" onClick={() => exportStaffing("xlsx")} data-testid="export-staffing-xlsx"><Download className="w-3 h-3 mr-1" /> Excel</Button>
              </div>
            </div>
            <p className="text-xs text-[#5C5C5C] mb-3">Total Qty PO dan Qty Kurang Kirim (PO - Staffing)</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#F0E6D6]">
                  <tr>
                    <th className="p-2 text-left">Foto</th>
                    <th className="p-2 text-left">No PO</th>
                    <th className="p-2 text-left">Barang</th>
                    <th className="p-2 text-right">Qty PO</th>
                    <th className="p-2 text-right">Qty Staffing</th>
                    <th className="p-2 text-right">Kurang Kirim</th>
                  </tr>
                </thead>
                <tbody>
                  {staffingSummary.map((r, i) => (
                    <tr key={i} className="border-b border-[#E5E5E5]" data-testid={`rekap-staffing-row-${i}`}>
                      <td className="p-2">
                        {r.gambar_path ? <img src={`${API}/files/${r.gambar_path}`} className="w-10 h-10 object-cover rounded" alt="" /> : <div className="w-10 h-10 bg-[#F0E6D6] rounded flex items-center justify-center"><Package className="w-4 h-4 text-[#8B5A2B]" /></div>}
                      </td>
                      <td className="p-2">{r.no_po}</td>
                      <td className="p-2 font-medium">{r.nama_barang}</td>
                      <td className="p-2 text-right">{r.qty_po}</td>
                      <td className="p-2 text-right">{r.qty_staffing}</td>
                      <td className="p-2 text-right"><span className={`font-medium ${r.kurang_kirim > 0 ? 'text-[#F44336]' : 'text-[#4CAF50]'}`}>{r.kurang_kirim}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {staffingSummary.length === 0 && <p className="text-center text-[#5C5C5C] py-8">Belum ada data</p>}
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
