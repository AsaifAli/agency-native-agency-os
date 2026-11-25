const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
let inMemoryAccessToken = "";

export function setInMemoryAccessToken(token: string) {
  inMemoryAccessToken = token.trim();
}

export function clearInMemoryAccessToken() {
  inMemoryAccessToken = "";
}

export function orgId(){return process.env.NEXT_PUBLIC_ORG_ID || ""}
export function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const allowDev = process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH === "true" && process.env.NODE_ENV !== "production";
  const email = process.env.NEXT_PUBLIC_DEV_EMAIL || "founder@example.com";
  const token = inMemoryAccessToken || (allowDev ? `dev:${email}` : "");
  return { "Content-Type":"application/json", ...(token ? { "Authorization":`Bearer ${token}` } : {}) };
}
export async function api<T>(path:string, init:RequestInit={}):Promise<T>{
  const response=await fetch(`${API}${path}`,{...init,headers:{...authHeaders(),...(init.headers||{})},cache:"no-store"});
  if(!response.ok){let detail=`Request failed (${response.status})`;try{const body=await response.json();detail=body.detail||detail}catch{}throw new Error(detail)}
  if(response.status===204)return undefined as T;
  return response.json();
}
export type Workspace={id:string;org_id:string;name:string;created_at:string};
export type Agent={id:string;workspace_id:string;name:string;department:string;runtime:string;data_class:string;enabled:boolean};
export type Task={id:string;workspace_id:string;title:string;description:string;status:string;created_at:string};
export type AuditEvent={id:string;event_type:string;resource_type:string;resource_id:string;payload:Record<string,unknown>;created_at:string};

export type Execution={id:string;workspace_id:string;task_id:string;agent_id:string;runtime:string;data_class:string;status:string;attempt_count:number;max_attempts:number;error_code:string|null;error_message:string|null;queued_at:string;started_at:string|null;finished_at:string|null;created_at:string;updated_at:string};
