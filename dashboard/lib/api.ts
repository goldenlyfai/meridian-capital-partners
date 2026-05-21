// In production (Vercel) both frontend and API are on the same domain → relative paths.
// In local dev, point to the local FastAPI server via NEXT_PUBLIC_API_URL.
const BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "")      // browser: relative = same domain
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"); // SSR fallback

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export const api = {
  portfolio: {
    positions: () => get<any>("/api/portfolio/positions"),
    beta: () => get<any>("/api/portfolio/beta"),
  },
  research: {
    candidates: (limit = 20) => get<any>(`/api/research/candidates?limit=${limit}`),
    crowding: () => get<any>("/api/research/crowding"),
    vix: () => get<any>("/api/research/vix"),
    analysis: (ticker: string) => get<any>(`/api/research/analysis/${ticker}`),
  },
  risk: {
    state: () => get<any>("/api/risk/state"),
    stressTests: () => get<any>("/api/risk/stress-tests"),
    preTrade: (ticker: string, action: string, shares: number) =>
      get<any>(`/api/risk/pre-trade/${ticker}?action=${action}&shares=${shares}`),
  },
  performance: {
    attribution: (days = 90) => get<any>(`/api/performance/attribution?days=${days}`),
    equityCurve: () => get<any>("/api/performance/equity-curve"),
  },
  execution: {
    slippage: (days = 30) => get<any>(`/api/execution/slippage?days=${days}`),
    account: () => get<any>("/api/execution/account"),
    approve: (ticker: string, action: string) =>
      post<any>(`/api/execution/approve/${ticker}?action=${action}`, {}),
  },
  letter: {
    daily: (refresh = false) => get<any>(`/api/letter/daily?refresh=${refresh}`),
    weeklyCommentary: () => get<any>("/api/letter/weekly-commentary"),
  },
  universe: {
    stats: () => get<any>("/api/universe/stats"),
    addTicker: (ticker: string, companyName?: string, sector?: string) => {
      const params = new URLSearchParams({ ticker });
      if (companyName) params.set("company_name", companyName);
      if (sector) params.set("sector", sector);
      return post<any>(`/api/universe/add-ticker?${params}`, {});
    },
    search: (q: string) => get<any>(`/api/universe/search?q=${encodeURIComponent(q)}`),
  },
  jarvis: {
    chat: (message: string, history: any[] = []) =>
      post<any>("/api/jarvis/chat", { message, history }),
  },
};
