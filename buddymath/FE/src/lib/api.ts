// ─── API client cho BuddyMath backend (FastAPI) ──────────────────────────────
// Dev (vite :5173) gọi sang backend :8000 (CORS đã mở *). Khi build & được
// FastAPI phục vụ cùng origin thì base = "" (same-origin).

const env = (import.meta as any).env || {}
export const API_BASE: string =
  env.VITE_API_BASE ?? (env.DEV ? "http://localhost:8000" : "")

// ─── Token ────────────────────────────────────────────────────────────────────
const TOKEN_KEY = "sb_token"
const USER_KEY = "sb_user"

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    return null
  }
}
export function storeUser(u: AuthUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(u))
}

// ─── Types ──────────────────────────────────────────────────────────────────
export interface AuthUser {
  id: string
  email: string
  username: string
  role: "student" | "parent" | "admin"
  grade: number
  avatar?: string
}

export interface ChatResponse {
  answer: string
  sources: { title?: string; source?: string;[k: string]: unknown }[]
  route: string
  session_id: string
  model: string
}

export interface ScoreHistoryItem {
  id: string
  subject: string
  topic: string
  score: number
  total: number
  pct: number
  feedback: string
  created_at: string
}

export interface ScoreSummary {
  total_sessions: number
  by_subject: Record<string, { count: number; avg_pct: number }>
}

// ─── Fetch helper ─────────────────────────────────────────────────────────────
async function request<T>(path: string, opts: RequestInit = {}, auth = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string> | undefined),
  }
  if (auth) {
    const t = getToken()
    if (t) headers.Authorization = "Bearer " + t
  }
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...opts, headers })
  } catch {
    throw new Error("Không kết nối được máy chủ. Hãy chắc chắn backend đang chạy (cổng 8000).")
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as any).detail || `Lỗi ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ─── Auth ──────────────────────────────────────────────────────────────────
export async function apiLogin(email: string, password: string) {
  return request<{ token: string; user: AuthUser }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  })
}

export async function apiRegister(data: {
  username: string
  email: string
  password: string
  role: "student" | "parent"
  grade?: number
}) {
  return request<{ token: string; user: AuthUser }>("/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function apiMe() {
  return request<AuthUser>("/auth/me", {}, true)
}

// ─── Chat ──────────────────────────────────────────────────────────────────
export async function apiChat(message: string, opts: {
  sessionId?: string
  subject?: string
  topic?: string
} = {}) {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      session_id: opts.sessionId || "buddy-main",
      subject: opts.subject ?? null,
      topic: opts.topic ?? null,
    }),
  })
}

export async function apiChatImage(imageBase64: string, opts: {
  mediaType?: string
  prompt?: string
  sessionId?: string
  subject?: string
} = {}) {
  return request<ChatResponse>("/chat/image", {
    method: "POST",
    body: JSON.stringify({
      image_base64: imageBase64,
      media_type: opts.mediaType || "image/jpeg",
      prompt: opts.prompt || "",
      session_id: opts.sessionId || "buddy-main",
      subject: opts.subject ?? null,
    }),
  })
}

// ─── Groq trực tiếp (để tạo nội dung JSON như đề kiểm tra) ───────────────────
export async function apiGroqText(system: string, user: string, opts: { temperature?: number; maxTokens?: number } = {}) {
  const res = await request<{ content: { type: string; text: string }[] }>("/v1/messages", {
    method: "POST",
    body: JSON.stringify({
      system,
      messages: [{ role: "user", content: user }],
      temperature: opts.temperature ?? 0.4,
      max_tokens: opts.maxTokens ?? 1500,
    }),
  })
  return res.content?.[0]?.text || ""
}

// ─── Scores ────────────────────────────────────────────────────────────────
export async function apiScoreHistory(subject?: string, limit = 30) {
  const q = new URLSearchParams()
  if (subject) q.set("subject", subject)
  q.set("limit", String(limit))
  return request<ScoreHistoryItem[]>(`/scores/history?${q}`, {}, true)
}

export async function apiScoreSummary() {
  return request<ScoreSummary>("/scores/summary", {}, true)
}

export async function apiRecordScore(data: {
  subject: string
  topic?: string
  score: number
  total?: number
  details?: string
  feedback?: string
}) {
  return request<{ success: boolean; id: string }>("/scores/record", {
    method: "POST",
    body: JSON.stringify(data),
  }, true)
}
