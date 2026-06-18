import { createClient } from "@supabase/supabase-js"
import type { Context, Next } from "hono"
import { HTTPException } from "hono/http-exception"
import type { Env } from "../types"

export type AdminVariables = { adminEmail: string }

// Verify a Supabase-issued JWT and require the user's email to be in ADMIN_EMAILS.
// getUser() validates the token against Supabase Auth, so no JWT secret is needed here.
export async function adminAuth(
  c: Context<{ Bindings: Env; Variables: AdminVariables }>,
  next: Next
) {
  const header = c.req.header("Authorization") ?? ""
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : null
  if (!token) {
    throw new HTTPException(401, {
      res: c.json({ error: "Token tidak ada.", code: "UNAUTHORIZED" }, 401),
    })
  }

  const sb = createClient(c.env.SUPABASE_URL, c.env.SUPABASE_ANON_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
  const { data, error } = await sb.auth.getUser(token)
  const email = data.user?.email?.toLowerCase()
  const allowed = c.env.ADMIN_EMAILS.split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean)

  if (error || !email || !allowed.includes(email)) {
    throw new HTTPException(403, {
      res: c.json({ error: "Akses ditolak.", code: "FORBIDDEN" }, 403),
    })
  }

  c.set("adminEmail", email)
  await next()
}
