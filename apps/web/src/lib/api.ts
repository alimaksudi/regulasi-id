// Request shapes are validated server-side by the shared Zod schemas. The client
// uses loose string types to stay decoupled from the enum branding.
//
// SSR (server) and the browser may reach the API at different hosts: in Docker the
// server render talks to the API over the internal network while the browser uses
// the public URL. VITE_INTERNAL_API_URL covers the server side when set.
const PUBLIC_API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8787"
const INTERNAL_API_URL = import.meta.env.VITE_INTERNAL_API_URL ?? PUBLIC_API_URL
const API_URL = typeof window === "undefined" ? INTERNAL_API_URL : PUBLIC_API_URL

export type SearchBody = {
  q: string
  sector?: string
  type?: string
  year_from?: number
  year_to?: number
  status?: string
  limit?: number
}

export type ListParams = {
  sector?: string
  type?: string
  year?: number
  status?: string
  cursor?: string
  per_page?: number
}

export type SearchResult = {
  work_id: number
  frbr_uri: string
  title_id: string
  number: string
  year: number
  status: string
  snippet: string | null
  score: number
  node_id: number | null
  node_type: string | null
  node_number: string | null
}

export type SearchResponse = {
  query: string
  total: number
  semantic_used: boolean
  results: SearchResult[]
}

export type RegulationListItem = {
  frbr_uri: string
  title: string
  number: string
  year: number
  status: string
  type: string
  sector: string | null
  date_enacted: string | null
}

export type RegulationListResponse = {
  total: number
  next_cursor: string | null
  regulations: RegulationListItem[]
}

export type RegulationDetail = {
  work: {
    frbr_uri: string
    title: string
    number: string
    year: number
    status: string
    date_enacted: string | null
    source_url: string | null
    sector: string | null
    type: string | null
    has_abstract: boolean
    has_faq: boolean
    related: { relationship: string; frbr_uri: string; title: string }[]
  }
  nodes: {
    id: number
    node_type: string
    number: string | null
    heading: string | null
    content_text: string | null
    sort_order: number
  }[]
}

export type SectorStat = {
  code: string
  name_id: string
  name_en: string | null
  regulation_count: number
  berlaku_count: number
  latest_year: number | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`)
  }
  return res.json() as Promise<T>
}

function query(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") usp.set(k, String(v))
  }
  const s = usp.toString()
  return s ? `?${s}` : ""
}

export const apiClient = {
  search: (body: SearchBody) =>
    request<SearchResponse>("/api/v1/search", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listRegulations: (params: ListParams = {}) =>
    request<RegulationListResponse>(
      `/api/v1/regulations${query({
        sector: params.sector,
        type: params.type,
        year: params.year,
        status: params.status,
        cursor: params.cursor,
        per_page: params.per_page,
      })}`
    ),

  getRegulation: (frbr: string) =>
    request<RegulationDetail>(`/api/v1/regulations${frbr}`),

  getSectors: () => request<{ sectors: SectorStat[] }>("/api/v1/sectors"),
}
