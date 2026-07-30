import { createContext, useContext, useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const TOKEN_STORAGE_KEY = "access_token";

// Attach the Authorization header to every outgoing request. This replaces
// cookie-based auth (which requires same-domain/subdomain) with a Bearer
// token approach that works across custom domains (e.g. agfdata.com) and
// the Railway-provided backend domain.
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (!token) {
        setUser(null);
        setLoading(false);
        return;
      }
      try {
        const { data } = await axios.get(`${API}/auth/me`);
        setUser(data);
      } catch {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
    const { data } = await axios.post(`${API}/auth/login`, { email, password });
    if (data?.access_token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, data.access_token);
    }
    setUser(data);
    return data;
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/auth/logout`);
    } finally {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setUser(null);
    }
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
