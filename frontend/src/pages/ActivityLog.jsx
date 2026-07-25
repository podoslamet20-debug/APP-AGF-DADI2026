import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { History, User, RefreshCw, Filter, Trash2 } from "lucide-react";

const ACTION_COLORS = {
  login: "#4CAF50",
  logout: "#5C5C5C",
  login_failed: "#F44336",
  create: "#2196F3",
  update: "#FFC107",
  delete: "#F44336",
};

const RESOURCES = [
  { key: "auth", label: "Auth (Login/Logout)" },
  { key: "barang", label: "Database Barang" },
  { key: "po", label: "PO" },
  { key: "barang-masuk", label: "Barang Masuk" },
  { key: "staffing", label: "Staffing" },
  { key: "spk", label: "SPK" },
  { key: "progres", label: "Progres Barang" },
  { key: "users", label: "User Management" },
];

const ACTIONS = ["login", "logout", "login_failed", "create", "update", "delete"];

export default function ActivityLog() {
  const { API } = useAuth();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ action: "all", resource: "all", user_id: "", date_from: "", date_to: "" });
  const [users, setUsers] = useState([]);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.action !== "all") params.action = filters.action;
      if (filters.resource !== "all") params.resource = filters.resource;
      if (filters.user_id) params.user_id = filters.user_id;
      if (filters.date_from) params.date_from = filters.date_from;
      if (filters.date_to) params.date_to = filters.date_to;
      const { data } = await axios.get(`${API}/activity-log`, { params });
      setEntries(data);
    } catch (e) {
      toast.error("Gagal load activity log: " + (e.response?.data?.detail || e.message));
    } finally { setLoading(false); }
  };

  const loadUsers = async () => {
    try { const { data } = await axios.get(`${API}/users`); setUsers(data); } catch (e) { /* ignore */ }
  };

  useEffect(() => { load(); loadUsers(); }, []);

  const formatDateTime = (iso) => {
    if (!iso) return "-";
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const purgeOld = async () => {
    const before = window.prompt("Hapus semua log SEBELUM tanggal (YYYY-MM-DD):");
    if (!before) return;
    try {
      const { data } = await axios.delete(`${API}/activity-log/purge`, { params: { before } });
      toast.success(`${data.deleted} log dihapus`);
      load();
    } catch (e) { toast.error("Gagal purge: " + (e.response?.data?.detail || e.message)); }
  };

  return (
    <div className="space-y-6" data-testid="activity-log-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>Activity Log</h1>
          <p className="text-[#5C5C5C] mt-1">Riwayat login user dan semua perubahan (create/update/delete) di semua menu.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="refresh-activity"><RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Refresh</Button>
          <Button variant="outline" size="sm" onClick={purgeOld} className="text-[#F44336]" data-testid="purge-activity"><Trash2 className="w-4 h-4 mr-2" /> Hapus Lama</Button>
        </div>
      </div>

      <Card className="p-4 border border-[#E5E5E5]">
        <div className="flex items-center gap-2 mb-3 text-sm text-[#8B5A2B]"><Filter className="w-4 h-4" /> Filter</div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div>
            <Label className="text-xs">Action</Label>
            <Select value={filters.action} onValueChange={(v) => setFilters({ ...filters, action: v })}>
              <SelectTrigger data-testid="filter-action"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Action</SelectItem>
                {ACTIONS.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Resource</Label>
            <Select value={filters.resource} onValueChange={(v) => setFilters({ ...filters, resource: v })}>
              <SelectTrigger data-testid="filter-resource"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua Menu</SelectItem>
                {RESOURCES.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">User</Label>
            <Select value={filters.user_id || "all"} onValueChange={(v) => setFilters({ ...filters, user_id: v === "all" ? "" : v })}>
              <SelectTrigger data-testid="filter-user"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua User</SelectItem>
                {users.map((u) => <SelectItem key={u._id} value={u._id}>{u.name} ({u.role})</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Dari Tanggal</Label>
            <Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} data-testid="filter-date-from" />
          </div>
          <div>
            <Label className="text-xs">Sampai Tanggal</Label>
            <Input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} data-testid="filter-date-to" />
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <Button onClick={load} className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" size="sm" data-testid="apply-filters">Terapkan Filter</Button>
          <Button variant="outline" size="sm" onClick={() => { setFilters({ action: "all", resource: "all", user_id: "", date_from: "", date_to: "" }); setTimeout(load, 0); }} data-testid="reset-filters">Reset</Button>
        </div>
      </Card>

      <Card className="border border-[#E5E5E5] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#F0E6D6]">
              <tr>
                <th className="p-3 text-left text-xs font-semibold text-[#5C5C5C] uppercase tracking-wider">Tanggal & Jam</th>
                <th className="p-3 text-left text-xs font-semibold text-[#5C5C5C] uppercase tracking-wider">User</th>
                <th className="p-3 text-left text-xs font-semibold text-[#5C5C5C] uppercase tracking-wider">Action</th>
                <th className="p-3 text-left text-xs font-semibold text-[#5C5C5C] uppercase tracking-wider">Menu</th>
                <th className="p-3 text-left text-xs font-semibold text-[#5C5C5C] uppercase tracking-wider">Detail</th>
                <th className="p-3 text-right text-xs font-semibold text-[#5C5C5C] uppercase tracking-wider">IP</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 ? (
                <tr><td colSpan={6} className="p-12 text-center text-[#5C5C5C]"><History className="w-8 h-8 mx-auto mb-2 opacity-50" />Belum ada activity log.</td></tr>
              ) : (
                entries.map((e, i) => (
                  <tr key={e._id} className="border-t border-[#E5E5E5] hover:bg-[#FAFAFA]" data-testid={`activity-row-${i}`}>
                    <td className="p-3 text-xs font-mono text-[#1A1A1A] whitespace-nowrap" data-testid={`activity-time-${i}`}>{formatDateTime(e.timestamp)}</td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-[#F0E6D6] flex items-center justify-center flex-shrink-0"><User className="w-3 h-3 text-[#8B5A2B]" /></div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{e.user_email || "anonymous"}</p>
                          <p className="text-[10px] text-[#5C5C5C] uppercase">{e.user_role || "-"}</p>
                        </div>
                      </div>
                    </td>
                    <td className="p-3">
                      <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ backgroundColor: (ACTION_COLORS[e.action] || "#8B5A2B") + "22", color: ACTION_COLORS[e.action] || "#8B5A2B" }} data-testid={`activity-action-${i}`}>{e.action}</span>
                    </td>
                    <td className="p-3 text-sm text-[#1A1A1A]" data-testid={`activity-resource-${i}`}>{e.resource_label || e.resource}</td>
                    <td className="p-3 text-xs text-[#5C5C5C] font-mono truncate max-w-xs">
                      {e.detail || `${e.method} ${e.path}${e.resource_id ? ` (id: ${e.resource_id.slice(0, 12)}${e.resource_id.length > 12 ? '…' : ''})` : ''}`}
                    </td>
                    <td className="p-3 text-xs text-right text-[#5C5C5C] font-mono">{e.ip || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {entries.length > 0 && <p className="p-3 text-xs text-[#5C5C5C] border-t border-[#E5E5E5]">Menampilkan {entries.length} entri (paling baru dulu, maksimum 500 per query).</p>}
      </Card>
    </div>
  );
}
