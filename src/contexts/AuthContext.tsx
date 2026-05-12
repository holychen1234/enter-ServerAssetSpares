import { useEffect, useState, ReactNode } from "react";
import type { AppUser, Role } from "@/types/cmdb";
import { login as apiLogin } from "@/lib/mockApi";
import { AuthContext, AUTH_STORAGE_KEY } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(AUTH_STORAGE_KEY);
      if (raw) setUser(JSON.parse(raw));
    } catch {
      // ignore parse errors
    }
    setLoading(false);
  }, []);

  const signIn = async (username: string, password: string) => {
    const u = await apiLogin(username, password);
    setUser(u);
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(u));
    return u;
  };

  const signOut = () => {
    setUser(null);
    localStorage.removeItem(AUTH_STORAGE_KEY);
  };

  const hasRole = (...roles: Role[]) => {
    if (!user) return false;
    return roles.includes(user.role);
  };

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}
