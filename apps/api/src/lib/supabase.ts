import { createClient, type SupabaseClient } from "@supabase/supabase-js"
import type { Env } from "../types"

// Anon key: subject to RLS. Use for all public reads.
export function createSupabaseClient(env: Env): SupabaseClient {
  return createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
}

// Service role: bypasses RLS. Use only for server-side writes/reads that need it
// (suggestion insert returning the row, admin operations). Never reaches the browser.
export function createSupabaseAdminClient(env: Env): SupabaseClient {
  return createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
}
