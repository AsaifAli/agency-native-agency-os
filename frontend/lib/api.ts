const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
let inMemoryAccessToken = "";
let inMemoryCsrfToken = "";
let lastSessionRefreshAt = 0;
let lastSessionRefreshAttemptAt = 0;
let refreshInFlight: Promise<boolean> | null = null;
const SESSION_REFRESH_INTERVAL_MS = 15 * 60 * 1000;

export function setInMemoryAccessToken(token: string) {
  inMemoryAccessToken = token.trim();
}

export function clearInMemoryAccessToken() {
  inMemoryAccessToken = "";
  inMemoryCsrfToken = "";
  lastSessionRefreshAt = 0;
  lastSessionRefreshAttemptAt = 0;
}

export function orgId(){return process.env.NEXT_PUBLIC_ORG_ID || ""}
export function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const allowDev = process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH === "true" && process.env.NODE_ENV !== "production";
  const email = process.env.NEXT_PUBLIC_DEV_EMAIL || "founder@example.com";
  const token = inMemoryAccessToken || (allowDev ? `dev:${email}` : "");
  return { "Content-Type":"application/json", ...(token ? { "Authorization":`Bearer ${token}` } : {}) };
}
async function csrfHeaders(method: string): Promise<HeadersInit> {
  if (["GET", "HEAD", "OPTIONS", "TRACE"].includes(method.toUpperCase())) return {};
  if (!inMemoryCsrfToken) {
    const response = await fetch(`${API}/v1/auth/csrf`, { credentials: "include", cache: "no-store" });
    if (!response.ok) throw new Error("Unable to establish a secure browser session");
    const body = await response.json();
    inMemoryCsrfToken = String(body.csrf_token || "");
    if (!inMemoryCsrfToken) throw new Error("CSRF token was not issued");
  }
  return { "X-CSRF-Token": inMemoryCsrfToken };
}

export async function refreshBrowserSession(force = false): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const allowDev = process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH === "true" && process.env.NODE_ENV !== "production";
  if (inMemoryAccessToken || allowDev) return false;
  const now = Date.now();
  if (!force && now - lastSessionRefreshAt < SESSION_REFRESH_INTERVAL_MS) return true;
  if (!force && now - lastSessionRefreshAttemptAt < 60 * 1000) return false;
  if (refreshInFlight) return refreshInFlight;

  lastSessionRefreshAttemptAt = now;
  refreshInFlight = (async () => {
    try {
      const csrf = await csrfHeaders("POST");
      const response = await fetch(`${API}/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { ...csrf },
        cache: "no-store",
      });
      if (!response.ok) return false;
      lastSessionRefreshAt = Date.now();
      return true;
    } catch {
      // Keep the current request path usable; the API will still validate the
      // existing cookie and surface authentication/network errors normally.
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export async function api<T>(path:string, init:RequestInit={}):Promise<T>{
  const method = init.method || "GET";
  await refreshBrowserSession();
  const csrf = await csrfHeaders(method);
  const response=await fetch(`${API}${path}`,{...init,credentials:"include",headers:{...authHeaders(),...csrf,...(init.headers||{})},cache:"no-store"});
  if(!response.ok){let detail=`Request failed (${response.status})`;try{const body=await response.json();detail=body.detail||detail}catch{}throw new Error(detail)}
  if(response.status===204)return undefined as T;
  return response.json();
}
export type Workspace={id:string;org_id:string;name:string;created_at:string};
export type Agent={id:string;workspace_id:string;name:string;department:string;runtime:string;data_class:string;enabled:boolean};
export type Task={id:string;workspace_id:string;title:string;description:string;status:string;created_at:string};
export type AuditEvent={id:string;event_type:string;resource_type:string;resource_id:string;payload:Record<string,unknown>;created_at:string};

export type Execution={id:string;workspace_id:string;task_id:string;agent_id:string;runtime:string;data_class:string;status:string;attempt_count:number;max_attempts:number;error_code:string|null;error_message:string|null;queued_at:string;started_at:string|null;finished_at:string|null;created_at:string;updated_at:string};
