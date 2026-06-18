import { createClient } from "@supabase/supabase-js"

// Browser client (anon key). Subject to RLS. Never the service role key here.
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
  { auth: { persistSession: true } }
)
