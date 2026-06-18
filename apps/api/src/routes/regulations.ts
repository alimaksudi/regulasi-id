import { Hono } from "hono"
import { zValidator } from "@hono/zod-validator"
import { ListRegulationsSchema } from "@regulasi-id/shared/schemas"
import type { Env } from "../types"
import { createSupabaseClient } from "../lib/supabase"
import { rateLimiter } from "../middleware/ratelimit"
import { encodeCursor, decodeCursor } from "../lib/cursor"

const regulations = new Hono<{ Bindings: Env }>()

// GET /api/v1/regulations — cursor-paginated list (keyset on year DESC, id DESC).
regulations.get(
  "/",
  rateLimiter({ max: 60, window: "60 s", prefix: "reg-list" }),
  zValidator("query", ListRegulationsSchema),
  async (c) => {
    const f = c.req.valid("query")
    const sb = createSupabaseClient(c.env)

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const applyFilters = (q: any) => {
      if (f.sector) q = q.eq("sectors.code", f.sector)
      if (f.type) q = q.in("regulation_types.code", f.type)
      if (f.year) q = q.eq("year", f.year)
      if (f.year_from) q = q.gte("year", f.year_from)
      if (f.year_to) q = q.lte("year", f.year_to)
      if (f.status) q = q.in("status", f.status)
      return q
    }

    const sectorEmbed = f.sector ? "sectors!inner(code)" : "sectors(code)"
    const select = `id, frbr_uri, title_id, number, year, status, date_enacted, regulation_types!inner(code), ${sectorEmbed}`

    const { count } = await applyFilters(
      sb.from("works").select(select, { count: "exact", head: true })
    )

    let q = applyFilters(
      sb
        .from("works")
        .select(select)
        .order("year", { ascending: false })
        .order("id", { ascending: false })
        .limit(f.per_page + 1)
    )

    if (f.cursor) {
      const cur = decodeCursor(f.cursor)
      if (cur) q = q.or(`year.lt.${cur.year},and(year.eq.${cur.year},id.lt.${cur.id})`)
    }

    const { data, error } = await q
    if (error) throw new Error(error.message)

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rows = (data ?? []) as any[]
    let nextCursor: string | null = null
    if (rows.length > f.per_page) {
      const last = rows[f.per_page - 1]
      nextCursor = encodeCursor({ year: last.year, id: last.id })
      rows.length = f.per_page
    }

    const out = rows.map((r) => ({
      frbr_uri: r.frbr_uri,
      title: r.title_id,
      number: r.number,
      year: r.year,
      status: r.status,
      type: r.regulation_types?.code,
      sector: r.sectors?.code,
      date_enacted: r.date_enacted,
    }))

    return c.json({ total: count ?? 0, next_cursor: nextCursor, regulations: out })
  }
)

// GET /api/v1/regulations/akn/id/act/:type/:year/:number — single regulation + nodes.
regulations.get(
  "/akn/id/act/:type/:year/:number",
  rateLimiter({ max: 120, window: "60 s", prefix: "reg-detail" }),
  async (c) => {
    const { type, year, number } = c.req.param()
    const frbr = `/akn/id/act/${type}/${year}/${number}`
    const sb = createSupabaseClient(c.env)

    const { data: work, error } = await sb
      .from("works")
      .select(
        "id, frbr_uri, title_id, number, year, status, date_enacted, source_url, regulation_types!inner(code), sectors(code), abstracts(id), faqs(id)"
      )
      .eq("frbr_uri", frbr)
      .maybeSingle()

    if (error) throw new Error(error.message)
    if (!work) return c.json({ error: "Regulasi tidak ditemukan.", code: "NOT_FOUND" }, 404)

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = work as any

    const { data: nodes } = await sb
      .from("document_nodes")
      .select("id, node_type, number, heading, content_text, sort_order")
      .eq("work_id", w.id)
      .order("sort_order", { ascending: true })

    const { data: rels } = await sb
      .from("work_relationships")
      .select(
        "relationship_types!inner(name_id), works!work_relationships_to_work_id_fkey(frbr_uri, title_id)"
      )
      .eq("from_work_id", w.id)

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const related = ((rels ?? []) as any[])
      .filter((r) => r.works)
      .map((r) => ({
        relationship: r.relationship_types?.name_id,
        frbr_uri: r.works?.frbr_uri,
        title: r.works?.title_id,
      }))

    c.header("Cache-Control", "public, max-age=86400, stale-while-revalidate=3600")
    return c.json({
      work: {
        frbr_uri: w.frbr_uri,
        title: w.title_id,
        number: w.number,
        year: w.year,
        status: w.status,
        date_enacted: w.date_enacted,
        source_url: w.source_url,
        sector: w.sectors?.code,
        type: w.regulation_types?.code,
        has_abstract: Array.isArray(w.abstracts) && w.abstracts.length > 0,
        has_faq: Array.isArray(w.faqs) && w.faqs.length > 0,
        related,
      },
      nodes: nodes ?? [],
    })
  }
)

export default regulations
