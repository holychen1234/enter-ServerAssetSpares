import { useEffect, useState, ReactNode } from "react";
import type { AppUser, Role } from "@/types/cmdb";
import {
  signInWithUsername,
  signOut as apiSignOut,
  fetchCurrentProfile,
} from "@/lib/api/cmdb";
import { supabase } from "@/integrations/supabase/client";
import { AuthContext } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    // Subscribe FIRST, then check session — avoids missing the initial event.
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!mounted) return;
      if (!session) {
        setUser(null);
        return;
      }
      // Defer DB read out of the auth callback.
      setTimeout(() => {
        fetchCurrentProfile()
          .then((p) => mounted && setUser(p))
          .catch(() => mounted && setUser(null));
      }, 0);
    });

    fetchCurrentProfile()
      .then((p) => {
        if (mounted) setUser(p);
      })
      .catch(() => {
        if (mounted) setUser(null);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const signIn = async (username: string, password: string) => {
    const u = await signInWithUsername(username, password);
    setUser(u);
    return u;
  };

  const signOut = async () => {
    await apiSignOut();
    setUser(null);
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
