import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { Toaster } from "sonner";
import LoginPage from "@/pages/LoginPage";
import DashboardLayout from "@/layouts/DashboardLayout";
import DatabaseBarang from "@/pages/DatabaseBarang";
import POPage from "@/pages/POPage";
import BarangMasuk from "@/pages/BarangMasuk";
import Staffing from "@/pages/Staffing";
import SPKPage from "@/pages/SPKPage";
import ProgresBarang from "@/pages/ProgresBarang";
import RekapData from "@/pages/RekapData";
import Dashboard from "@/pages/Dashboard";
import UserManagement from "@/pages/UserManagement";
import ActivityLog from "@/pages/ActivityLog";
import Pengrajin from "@/pages/Pengrajin";

function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-lg" data-testid="loading-screen">Memuat...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

function App() {
  return (
    <div className="App min-h-screen bg-[#FAFAFA]">
      <AuthProvider>
        <BrowserRouter>
          <Toaster position="top-right" richColors />
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
              <Route index element={<Dashboard />} />
              <Route path="barang" element={<DatabaseBarang />} />
              <Route path="pengrajin" element={<Pengrajin />} />
              <Route path="po" element={<POPage />} />
              <Route path="barang-masuk" element={<BarangMasuk />} />
              <Route path="staffing" element={<Staffing />} />
              <Route path="spk" element={<SPKPage />} />
              <Route path="progres" element={<ProgresBarang />} />
              <Route path="rekap" element={<RekapData />} />
              <Route path="users" element={<ProtectedRoute roles={["admin"]}><UserManagement /></ProtectedRoute>} />
              <Route path="activity-log" element={<ProtectedRoute roles={["admin", "owner"]}><ActivityLog /></ProtectedRoute>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
