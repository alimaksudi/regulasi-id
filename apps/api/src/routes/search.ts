import { Hono } from "hono"
import { zValidator } from "@hono/zod-validator"
import { SearchSchema } from "@regulasi-id/shared/schemas"
import type { Env } from "../types"
import { createSupabaseClient } from "../lib/supabase"
import { generateEmbedding } from "../lib/embeddings"
import { getCache, setCache, hashQuery } from "../lib/cache"
import { rateLimiter } from "../middleware/ratelimit"

const search = new Hono<{ Bindings: Env }>()

// POST /api/v1/search — hybrid search. Generates the query embedding server-side
// (cached by query hash), then calls the search_regulations() RPC.
search.post(
  "/",
  rateLimiter({ max: 60, window: "60 s", prefix: "search" }),
  zValidator("json", SearchSchema),
  async (c) => {
    const body = c.req.valid("json")

    // Embedding, cached in Upstash by query hash (TTL 1h). Degrade to FTS on failure.
    const cacheKey = `emb:${await hashQuery(body.q)}`
    let embedding = await getCache<number[]>(c.env, cacheKey)
    let semanticUsed = false
    try {
      if (!embedding) {
        embedding = await generateEmbedding(body.q, c.env.OPENAI_API_KEY)
        await setCache(c.env, cacheKey, embedding, { ex: 3600 })
      }
      semanticUsed = embedding !== null
    } catch {
      embedding = null
    }

    const sb = createSupabaseClient(c.env)
    const { data, error } = await sb.rpc("search_regulations", {
      p_query: body.q,
      p_sector: body.sector ?? null,
      p_type: body.type ? body.type.join(",") : null,
      p_year_from: body.year_from ?? null,
      p_year_to: body.year_to ?? null,
      p_status: body.status ? body.status.join(",") : null,
      p_limit: body.limit,
      // pgvector parses the text form "[1,2,3]" (= JSON.stringify of a number array).
      p_query_embedding: embedding ? JSON.stringify(embedding) : null,
    })

    if (error) {
      throw new Error(`search_regulations failed: ${error.message}`)
    }

    const results = data ?? []

    // Fire-and-forget analytics. Zero-result queries drive the content backlog.
    // Promise.resolve wraps the Supabase thenable into a real Promise for waitUntil.
    c.executionCtx.waitUntil(
      Promise.resolve(
        sb.from("search_analytics").insert({
          query: body.q,
          sector_filter: body.sector ?? null,
          type_filter: body.type ? body.type.join(",") : null,
          result_count: results.length,
          embedding_used: semanticUsed,
          source: "api",
        })
      )
    )

    return c.json({
      query: body.q,
      total: results.length,
      semantic_used: semanticUsed,
      results,
    })
  }
)

export default search
