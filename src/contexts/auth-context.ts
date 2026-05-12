import { createContext } from "react";
import type { AppUser, Role } from "@/types/cmdb";

export interface AuthContextValue {
  user: AppUser | null;
  loading: boolean;
  signIn: (username: string, password: string) => Promise<AppUser>;
  signOut: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
export const AUTH_STORAGE_KEY = "cmdb.auth.user";
