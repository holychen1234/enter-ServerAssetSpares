// Internal FastAPI backend — the only backend mode for on-prem deployment.
// The API base path is configurable via VITE_INTERNAL_API_BASE (default "/api").

export const INTERNAL_API_BASE: string =
  (import.meta.env.VITE_INTERNAL_API_BASE as string | undefined) ?? "/api";
