import { Hono } from "hono"
import { zValidator } from "@hono/zod-validator"
import { z } from "zod"
import { ComplianceMappingSchema } from "@regulasi-id/shared/schemas"
import type { Env } from "../../types"
import { type AdminVariables, adminAuth } from "../../middleware/auth"
import { createSupabaseAdminClient } from "../../lib/supabase"
import { createRedis } from "../../lib/cache"

const admin = new Hono<{ Bindings: Env; Variables: AdminVariables }>()

// Every admin route requires a valid Supabase JWT for an allowlisted email.
admin.use("*", adminAuth)

const now = () => new Date().toISOString()

// --- suggestions ---

admin.get("/suggestions", async (c) => {
  const sb = createSupabaseAdminClient(c.env)
  const { data, error } = await sb
    .from("suggestions")
    .select("*")
    .eq("status", "pending")
    .order("created_at", { ascending: false })
    .limit(100)
  if (error) throw new Error(error.message)
  return c.json({ suggestions: data ?? [] })
})

admin.post("/suggestions/:id/approve", async (c) => {
  const id = Number(c.req.param("id"))
  const sb = createSupabaseAdminClient(c.env)
  const { data: sug, error: e1 } = await sb
    .from("suggestions")
    .select("id, node_id, suggested_content")
    .eq("id", id)
    .maybeSingle()
  if (e1) throw new Error(e1.message)
  if (!sug) return c.json({ error: "Saran tidak ditemukan.", code: "NOT_FOUND" }, 404)

  // apply_revision() does the audit + content update + status flip atomically.
  const { error } = await sb.rpc("apply_revision", {
    p_node_id: (sug as { node_id: number }).node_id,
    p_new_content: (sug as { suggested_content: string }).suggested_content,
    p_reason: "Disetujui admin",
    p_actor: `admin:${c.get("adminEmail")}`,
    p_suggestion_id: id,
  })
  if (error) throw new Error(error.message)
  return c.json({ id, status: "approved" })
})

admin.post(
  "/suggestions/:id/reject",
  zValidator("json", z.object({ note: z.string().max(2000).optional() })),
  async (c) => {
    const id = Number(c.req.param("id"))
    const { note } = c.req.valid("json")
    const sb = createSupabaseAdminClient(c.env)
    const { error } = await sb
      .from("suggestions")
      .update({ status: "rejected", admin_note: note ?? null, updated_at: now() })
      .eq("id", id)
    if (error) throw new Error(error.message)
    return c.json({ id, status: "rejected" })
  }
)

// --- compliance mappings CRUD ---

admin.get("/compliance", async (c) => {
  const sb = createSupabaseAdminClient(c.env)
  const { data, error } = await sb
    .from("compliance_mappings")
    .select("*, sectors(code), works(frbr_uri, title_id)")
    .order("id")
  if (error) throw new Error(error.message)
  return c.json({ mappings: data ?? [] })
})

async function resolveSectorId(sb: ReturnType<typeof createSupabaseAdminClient>, code: string) {
  const { data } = await sb.from("sectors").select("id").eq("code", code).maybeSingle()
  return (data as { id: number } | null)?.id ?? null
}

admin.post("/compliance", zValidator("json", ComplianceMappingSchema), async (c) => {
  const body = c.req.valid("json")
  const sb = createSupabaseAdminClient(c.env)
  const sectorId = await resolveSectorId(sb, body.sector)
  if (!sectorId) return c.json({ error: "Sektor tidak valid.", code: "VALIDATION_ERROR" }, 400)
  const { data, error } = await sb
    .from("compliance_mappings")
    .insert({
      sector_id: sectorId,
      business_type: body.business_type ?? null,
      work_id: body.work_id,
      priority: body.priority,
      notes: body.notes ?? null,
    })
    .select("id")
    .single()
  if (error) throw new Error(error.message)
  return c.json(data, 201)
})

admin.put(
  "/compliance/:id",
  zValidator("json", ComplianceMappingSchema.partial()),
  async (c) => {
    const id = Number(c.req.param("id"))
    const body = c.req.valid("json")
    const sb = createSupabaseAdminClient(c.env)
    const patch: Record<string, unknown> = {}
    if (body.business_type !== undefined) patch.business_type = body.business_type
    if (body.work_id !== undefined) patch.work_id = body.work_id
    if (body.priority !== undefined) patch.priority = body.priority
    if (body.notes !== undefined) patch.notes = body.notes
    if (body.sector !== undefined) {
      const sectorId = await resolveSectorId(sb, body.sector)
      if (!sectorId) return c.json({ error: "Sektor tidak valid.", code: "VALIDATION_ERROR" }, 400)
      patch.sector_id = sectorId
    }
    const { error } = await sb.from("compliance_mappings").update(patch).eq("id", id)
    if (error) throw new Error(error.message)
    return c.json({ id, updated: true })
  }
)

admin.delete("/compliance/:id", async (c) => {
  const id = Number(c.req.param("id"))
  const sb = createSupabaseAdminClient(c.env)
  const { error } = await sb.from("compliance_mappings").delete().eq("id", id)
  if (error) throw new Error(error.message)
  return c.json({ id, deleted: true })
})

// --- analytics ---

admin.get("/analytics", async (c) => {
  const sb = createSupabaseAdminClient(c.env)
  const { data, error } = await sb
    .from("search_analytics")
    .select("query, zero_results, source, created_at")
    .order("created_at", { ascending: false })
    .limit(500)
  if (error) throw new Error(error.message)
  const rows = (data ?? []) as { zero_results: boolean }[]
  return c.json({
    total_logged: rows.length,
    zero_result_count: rows.filter((r) => r.zero_results).length,
    recent: rows.slice(0, 50),
  })
})

// --- crawl jobs ---

admin.get("/jobs", async (c) => {
  const status = c.req.query("status")
  const sb = createSupabaseAdminClient(c.env)
  let q = sb.from("crawl_jobs").select("*").order("updated_at", { ascending: false }).limit(200)
  if (status) q = q.eq("status", status)
  const { data, error } = await q
  if (error) throw new Error(error.message)
  return c.json({ jobs: data ?? [] })
})

admin.post("/jobs/:id/retry", async (c) => {
  const id = Number(c.req.param("id"))
  const sb = createSupabaseAdminClient(c.env)
  const { error } = await sb
    .from("crawl_jobs")
    .update({ status: "pending", next_retry_at: null, retry_count: 0, updated_at: now() })
    .eq("id", id)
  if (error) throw new Error(error.message)
  return c.json({ id, status: "pending" })
})

// --- cache invalidation ---

admin.post(
  "/revalidate",
  zValidator("json", z.object({ pattern: z.string().min(1).max(200) })),
  async (c) => {
    const { pattern } = c.req.valid("json")
    const redis = createRedis(c.env)
    const keys = await redis.keys(pattern)
    const deleted = keys.length ? await redis.del(...keys) : 0
    return c.json({ pattern, deleted })
  }
)

export default admin
