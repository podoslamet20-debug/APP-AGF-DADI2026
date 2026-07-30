import { createContext, useContext, useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const TOKEN_STORAGE_KEY = "auth_token";

axios.defaults.withCredentials = true;

// Some mobile browsers (iOS Safari, in-app webviews on Android, etc.) apply
// stricter cookie policies and don't reliably persist the `Set-Cookie` header
// returned by the login endpoint. To work around this, we keep a copy of the
// access token in localStorage and attach it as an `Authorization: Bearer`
// header on every request. The backend accepts either the cookie or the
// header, so this acts as a fallback without breaking the cookie-based flow
// that already works on desktop browsers.
const getStoredToken = () => {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
};

const setStoredToken = (token) => {
  try {
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // localStorage may be unavailable (e.g. private browsing) — ignore.
  }
};

// Attach the Authorization header from localStorage as a fallback on every
// outgoing request. If the cookie is present and valid, the backend will use
// that first; the header is only needed when the cookie failed to persist.
axios.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers = config.headers || {};
    if (!config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

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
        setStoredToken(null);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
    const { data } = await axios.post(`${API}/auth/login`, { email, password });

    // The backend also returns the access token in the response body (in
    // addition to setting the cookie) so we can persist it as a fallback for
    // browsers that don't reliably store cookies on mobile.
    const { access_token, ...userData } = data;
    if (access_token) {
      setStoredToken(access_token);
    }

    setUser(userData);
    return userData;
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/auth/logout`);
    } finally {
      setStoredToken(null);
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
