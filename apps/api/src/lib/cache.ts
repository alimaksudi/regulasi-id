import { Redis } from "@upstash/redis"
import type { Env } from "../types"

// REST client works in Workers (no TCP sockets).
export function createRedis(env: Env): Redis {
  return new Redis({
    url: env.UPSTASH_REDIS_REST_URL,
    token: env.UPSTASH_REDIS_REST_TOKEN,
  })
}

export async function getCache<T>(env: Env, key: string): Promise<T | null> {
  const redis = createRedis(env)
  const value = await redis.get<T>(key)
  return value ?? null
}

export async function setCache<T>(
  env: Env,
  key: string,
  value: T,
  opts?: { ex?: number }
): Promise<void> {
  const redis = createRedis(env)
  if (opts?.ex) {
    await redis.set(key, value, { ex: opts.ex })
  } else {
    await redis.set(key, value)
  }
}

// Stable short hash of a search query, for caching its embedding.
export async function hashQuery(q: string): Promise<string> {
  const data = new TextEncoder().encode(q.trim().toLowerCase())
  const digest = await crypto.subtle.digest("SHA-256", data)
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32)
}
