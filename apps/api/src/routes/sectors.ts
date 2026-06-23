import { Hono } from "hono"
import type { Env } from "../types"
import { createSupabaseClient } from "../lib/supabase"
import { getCache, setCache } from "../lib/cache"

const sectors = new Hono<{ Bindings: Env }>()

// GET /api/v1/sectors — from mv_sector_stats, Upstash cached 15 min, edge cached.
sectors.get("/", async (c) => {
  const cacheKey = "sectors:stats"
  let payload = await getCache<unknown[]>(c.env, cacheKey)

  if (!payload) {
    const sb = createSupabaseClient(c.env)
    const { data, error } = await sb.from("mv_sector_stats").select("*").order("code")
    if (error) throw new Error(error.message)
    payload = data ?? []
    await setCache(c.env, cacheKey, payload, { ex: 900 })
  }

  c.header("Cache-Control", "public, max-age=900, stale-while-revalidate=3600")
  return c.json({ sectors: payload })
})

export default sectors
