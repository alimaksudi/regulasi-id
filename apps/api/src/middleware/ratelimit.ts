import { Ratelimit } from "@upstash/ratelimit"
import { Redis } from "@upstash/redis"
import type { Context, Next } from "hono"
import { HTTPException } from "hono/http-exception"
import type { Env } from "../types"

// Upstash Duration string, e.g. "60 s", "1 h".
type Window = `${number} ${"ms" | "s" | "m" | "h" | "d"}`

// Sliding-window limiter keyed by client IP, shared across all edge instances.
export function rateLimiter(opts: { max: number; window: Window; prefix: string }) {
  return async (c: Context<{ Bindings: Env }>, next: Next) => {
    const redis = new Redis({
      url: c.env.UPSTASH_REDIS_REST_URL,
      token: c.env.UPSTASH_REDIS_REST_TOKEN,
    })
    const limiter = new Ratelimit({
      redis,
      limiter: Ratelimit.slidingWindow(opts.max, opts.window),
      prefix: `rl:${opts.prefix}`,
    })

    const ip = c.req.header("CF-Connecting-IP") ?? "unknown"
    const { success, reset } = await limiter.limit(ip)

    if (!success) {
      const retryAfter = Math.max(0, Math.ceil((reset - Date.now()) / 1000))
      throw new HTTPException(429, {
        res: c.json(
          {
            error: "Terlalu banyak permintaan. Coba lagi nanti.",
            code: "RATE_LIMITED",
            details: { retry_after_seconds: retryAfter },
          },
          429
        ),
      })
    }

    await next()
  }
}
