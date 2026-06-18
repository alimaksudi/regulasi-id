import { Hono } from "hono"
import { zValidator } from "@hono/zod-validator"
import { ComplianceSchema } from "@regulasi-id/shared/schemas"
import type { Env } from "../types"
import { createSupabaseClient } from "../lib/supabase"
import { rateLimiter } from "../middleware/ratelimit"

const compliance = new Hono<{ Bindings: Env }>()

// GET /api/v1/compliance?sector=&business_type= — curated applicable regulations.
compliance.get(
  "/",
  rateLimiter({ max: 60, window: "60 s", prefix: "compliance" }),
  zValidator("query", ComplianceSchema),
  async (c) => {
    const { sector, business_type } = c.req.valid("query")
    const sb = createSupabaseClient(c.env)

    let q = sb
      .from("compliance_mappings")
      .select(
        "priority, notes, business_type, sectors!inner(code), works!inner(frbr_uri, title_id, number, year, status, regulation_types!inner(code))"
      )
      .eq("sectors.code", sector)

    // business_type match: the specific type plus sector-wide (null) mappings.
    if (business_type) {
      q = q.or(`business_type.eq.${business_type},business_type.is.null`)
    }

    const { data, error } = await q
    if (error) throw new Error(error.message)

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const required = ((data ?? []) as any[]).map((m) => ({
      frbr_uri: m.works?.frbr_uri,
      title: m.works?.title_id,
      type: m.works?.regulation_types?.code,
      number: m.works?.number,
      year: m.works?.year,
      status: m.works?.status,
      priority: m.priority,
      notes: m.notes,
    }))

    return c.json({
      sector,
      business_type: business_type ?? null,
      required_regulations: required,
    })
  }
)

export default compliance
