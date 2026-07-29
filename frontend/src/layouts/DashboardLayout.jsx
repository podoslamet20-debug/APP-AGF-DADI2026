import { useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Package, Home, ShoppingCart, PackageOpen, Truck, FileText, TrendingUp, BarChart3, LogOut, Menu, X, User, Users, History, Hammer } from "lucide-react";

const ALL_ROLES = ["admin", "staff", "guest", "owner"];

const navItems = [
  { path: "/", label: "Dashboard", icon: Home, testId: "nav-dashboard" },
  { path: "/barang", label: "Database Barang", icon: Package, testId: "nav-barang", roles: ALL_ROLES },
  { path: "/pengrajin", label: "Pengrajin", icon: Hammer, testId: "nav-pengrajin", roles: ALL_ROLES },
  { path: "/po", label: "PO", icon: ShoppingCart, testId: "nav-po", roles: ALL_ROLES },
  { path: "/barang-masuk", label: "Barang Masuk", icon: PackageOpen, testId: "nav-barang-masuk", roles: ALL_ROLES },
  { path: "/staffing", label: "Staffing", icon: Truck, testId: "nav-staffing", roles: ALL_ROLES },
  { path: "/spk", label: "SPK", icon: FileText, testId: "nav-spk", roles: ALL_ROLES },
  { path: "/progres", label: "Progres Barang", icon: TrendingUp, testId: "nav-progres", roles: ALL_ROLES },
  { path: "/rekap", label: "Rekap Data", icon: BarChart3, testId: "nav-rekap", roles: ALL_ROLES },
  { path: "/users", label: "User Management", icon: Users, testId: "nav-users", roles: ["admin"] },
  { path: "/activity-log", label: "Activity Log", icon: History, testId: "nav-activity-log", roles: ["admin", "owner"] },
];

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const roleBadgeColor = {
    admin: "bg-[#8B5A2B] text-white",
    staff: "bg-[#4CAF50] text-white",
    guest: "bg-[#5C5C5C] text-white",
    owner: "bg-[#1A237E] text-white",
  };

  const filteredNav = navItems.filter((item) => !item.roles || item.roles.includes(user?.role));

  return (
    <div className="min-h-screen flex bg-[#FAFAFA]">
      {/* Sidebar */}
      <aside
        className={`fixed lg:sticky lg:top-0 inset-y-0 left-0 z-40 w-64 h-screen bg-white border-r border-[#E5E5E5] transition-transform duration-200 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="p-6 border-b border-[#E5E5E5] flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#8B5A2B] flex items-center justify-center">
            <Package className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-[#1A1A1A]" style={{ fontFamily: "Cabinet Grotesk, system-ui" }}>AGFDATA</h1>
            <p className="text-xs text-[#5C5C5C]">Furniture Management</p>
          </div>
        </div>
        <nav className="p-4 space-y-1">
          {filteredNav.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              data-testid={item.testId}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-150 ${
                  isActive
                    ? "bg-[#8B5A2B] text-white"
                    : "text-[#1A1A1A] hover:bg-[#F0E6D6]"
                }`
              }
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-[#E5E5E5] bg-white">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-full bg-[#F0E6D6] flex items-center justify-center">
              <User className="w-4 h-4 text-[#8B5A2B]" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[#1A1A1A] truncate">{user?.name}</p>
              <span className={`text-xs px-2 py-0.5 rounded ${roleBadgeColor[user?.role]}`} data-testid="user-role-badge">
                {user?.role?.toUpperCase()}
              </span>
            </div>
          </div>
          <Button
            data-testid="logout-button"
            variant="outline"
            size="sm"
            onClick={handleLogout}
            className="w-full"
          >
            <LogOut className="w-4 h-4 mr-2" /> Keluar
          </Button>
        </div>
      </aside>

      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-20 bg-white border-b border-[#E5E5E5] px-4 lg:px-6 py-3 flex items-center justify-between">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
            data-testid="menu-toggle"
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </Button>
          <div className="flex-1 lg:flex-none">
            <p className="text-sm text-[#5C5C5C]">Selamat datang, <span className="font-medium text-[#1A1A1A]">{user?.name}</span></p>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
