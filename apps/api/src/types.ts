export type Env = {
  // vars (wrangler.toml [vars])
  ENVIRONMENT: string
  ALLOWED_ORIGIN: string
  // secrets (wrangler secret put / .dev.vars)
  SUPABASE_URL: string
  SUPABASE_ANON_KEY: string
  SUPABASE_SERVICE_ROLE_KEY: string
  OPENAI_API_KEY: string
  UPSTASH_REDIS_REST_URL: string
  UPSTASH_REDIS_REST_TOKEN: string
  SENTRY_DSN: string
  ADMIN_JWT_SECRET: string
  ADMIN_EMAILS: string
}
