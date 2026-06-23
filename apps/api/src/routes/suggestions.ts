import { Hono } from "hono"
import { zValidator } from "@hono/zod-validator"
import { SuggestionSchema } from "@regulasi-id/shared/schemas"
import type { Env } from "../types"
import { createSupabaseAdminClient } from "../lib/supabase"
import { rateLimiter } from "../middleware/ratelimit"

const suggestions = new Hono<{ Bindings: Env }>()

// POST /api/suggestions — submit a correction. Rate limited 10/IP/hour.
// Service role: RLS allows public insert but not read-back, and we return the new row.
suggestions.post(
  "/",
  rateLimiter({ max: 10, window: "1 h", prefix: "suggest" }),
  zValidator("json", SuggestionSchema),
  async (c) => {
    const body = c.req.valid("json")
    const ip = c.req.header("CF-Connecting-IP") ?? null
    const sb = createSupabaseAdminClient(c.env)

    const { data, error } = await sb
      .from("suggestions")
      .insert({
        work_id: body.work_id,
        node_id: body.node_id,
        current_content: body.current_content,
        suggested_content: body.suggested_content,
        user_reason: body.reason ?? null,
        submitter_email: body.email ?? null,
        submitter_ip: ip,
      })
      .select("id, status")
      .single()

    if (error) throw new Error(error.message)

    return c.json(data, 201)
  }
)

export default suggestions
