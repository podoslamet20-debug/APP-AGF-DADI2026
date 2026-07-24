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
import { Plus, User, Edit, Trash2, Users } from "lucide-react";

export default function UserManagement() {
  const { API, user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "staff" });

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/users`);
      setUsers(data);
    } catch (e) { toast.error("Gagal load users"); }
  };

  useEffect(() => { load(); }, []);

  const submit = async () => {
    try {
      if (editingId) {
        const payload = { ...form };
        if (!payload.password) delete payload.password;
        await axios.put(`${API}/users/${editingId}`, payload);
        toast.success("User berhasil diupdate");
      } else {
        await axios.post(`${API}/users`, form);
        toast.success("User berhasil dibuat");
      }
      setOpen(false);
      setEditingId(null);
      setForm({ email: "", password: "", name: "", role: "staff" });
      load();
    } catch (e) {
      toast.error("Gagal: " + (e.response?.data?.detail || ""));
    }
  };

  const startEdit = (u) => {
    setForm({ email: u.email, password: "", name: u.name, role: u.role });
    setEditingId(u._id);
    setOpen(true);
  };

  const deleteUser = async (id) => {
    try {
      await axios.delete(`${API}/users/${id}`);
      toast.success("User dihapus");
      load();
    } catch (e) { toast.error("Gagal hapus: " + (e.response?.data?.detail || "")); }
  };

  const roleColor = { admin: "bg-[#8B5A2B] text-white", staff: "bg-[#4CAF50] text-white", guest: "bg-[#5C5C5C] text-white" };

  return (
    <div className="space-y-6" data-testid="user-management-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#1A1A1A] tracking-tight" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>User Management</h1>
          <p className="text-[#5C5C5C] mt-1">Kelola user admin, staff, dan tamu</p>
        </div>
        <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setEditingId(null); setForm({ email: "", password: "", name: "", role: "staff" }); }}}>
          <DialogTrigger asChild>
            <Button className="bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="add-user-button"><Plus className="w-4 h-4 mr-2" /> Tambah User</Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader><DialogTitle>{editingId ? "Edit User" : "Tambah User Baru"}</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Nama</Label>
                <Input data-testid="input-user-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <Label>Email</Label>
                <Input type="email" data-testid="input-user-email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
              <div>
                <Label>Password {editingId && <span className="text-xs text-[#5C5C5C]">(kosongkan jika tidak diubah)</span>}</Label>
                <Input type="password" data-testid="input-user-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <div>
                <Label>Role</Label>
                <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                  <SelectTrigger data-testid="select-user-role"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="staff">Staff</SelectItem>
                    <SelectItem value="guest">Tamu</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={submit} className="w-full bg-[#8B5A2B] hover:bg-[#7A4E24] text-white" data-testid="submit-user-button">{editingId ? "Update" : "Simpan"}</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="p-6 border border-[#E5E5E5]">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#F0E6D6]">
              <tr>
                <th className="p-3 text-left">Nama</th>
                <th className="p-3 text-left">Email</th>
                <th className="p-3 text-left">Role</th>
                <th className="p-3 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={i} className="border-b border-[#E5E5E5]" data-testid={`user-row-${i}`}>
                  <td className="p-3 flex items-center gap-2"><div className="w-8 h-8 rounded-full bg-[#F0E6D6] flex items-center justify-center"><User className="w-4 h-4 text-[#8B5A2B]" /></div>{u.name}</td>
                  <td className="p-3">{u.email}</td>
                  <td className="p-3"><span className={`text-xs px-2 py-1 rounded ${roleColor[u.role]}`}>{u.role.toUpperCase()}</span></td>
                  <td className="p-3 text-right">
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" size="sm" onClick={() => startEdit(u)} data-testid={`edit-user-${i}`}><Edit className="w-3 h-3" /></Button>
                      {u._id !== currentUser._id && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button variant="outline" size="sm" className="text-[#F44336]" data-testid={`delete-user-${i}`}><Trash2 className="w-3 h-3" /></Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Hapus User?</AlertDialogTitle>
                              <AlertDialogDescription>User {u.email} akan dihapus permanen. Yakin?</AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Batal</AlertDialogCancel>
                              <AlertDialogAction className="bg-[#F44336]" onClick={() => deleteUser(u._id)} data-testid={`confirm-delete-user-${i}`}>Hapus</AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr><td colSpan="4" className="p-8 text-center text-[#5C5C5C]">Belum ada user</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
