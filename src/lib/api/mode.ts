// Build-time switch between Enter Cloud (Supabase) and the internal FastAPI
// backend used for on-prem / private deployments.
//
// Set in `.env`:
//   VITE_API_MODE=cloud      # default — talks to Enter Cloud
//   VITE_API_MODE=internal   # talks to FastAPI behind /api
//   VITE_INTERNAL_API_BASE=/api   # only honored when API_MODE=internal
type ApiMode = "cloud" | "internal";

const raw = (import.meta.env.VITE_API_MODE as string | undefined) ?? "cloud";
export const API_MODE: ApiMode = raw === "internal" ? "internal" : "cloud";

export const INTERNAL_API_BASE: string =
  (import.meta.env.VITE_INTERNAL_API_BASE as string | undefined) ?? "/api";
