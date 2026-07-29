import { createContext, useContext, useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

axios.defaults.withCredentials = true;

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const { data } = await axios.get(`${API}/auth/me`);
        setUser(data);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
    const { data } = await axios.post(`${API}/auth/login`, { email, password });
    setUser(data);
    return data;
  };

  const logout = async () => {
    await axios.post(`${API}/auth/logout`);
    setUser(null);
  };

  const isAdmin = user?.role === "admin";
  const isStaff = user?.role === "staff";
  const isGuest = user?.role === "guest";
  const isOwner = user?.role === "owner";
  const canEdit = isAdmin;                          // full CRUD (create/edit/delete)
  const canEditPartial = isAdmin || isStaff;        // partial editors: BM, staffing, progres
  const canSeePrice = isAdmin || isOwner;           // owner sees prices (view-only)
  const canSeeCraftsman = isAdmin || isStaff || isOwner;
  const canSeeActivityLog = isAdmin || isOwner;

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, isAdmin, isStaff, isGuest, isOwner, canEdit, canEditPartial, canSeePrice, canSeeCraftsman, canSeeActivityLog, API }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
