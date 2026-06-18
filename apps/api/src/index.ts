import { Hono } from "hono"
import { cors } from "hono/cors"
import { HTTPException } from "hono/http-exception"
import * as Sentry from "@sentry/cloudflare"
import type { Env } from "./types"
import search from "./routes/search"
import regulations from "./routes/regulations"
import sectors from "./routes/sectors"
import compliance from "./routes/compliance"
import suggestions from "./routes/suggestions"
import openapi from "./routes/openapi"
import admin from "./routes/admin"

const app = new Hono<{ Bindings: Env }>()

// CORS: web app origin in prod, localhost:3000 for wrangler dev.
app.use("*", (c, next) =>
  cors({
    origin: (origin) => {
      const allowed = [c.env.ALLOWED_ORIGIN, "http://localhost:3000"]
      return allowed.includes(origin) ? origin : c.env.ALLOWED_ORIGIN
    },
    allowMethods: ["GET", "POST", "OPTIONS"],
    allowHeaders: ["Content-Type", "Authorization"],
    maxAge: 86400,
  })(c, next)
)

app.get("/", (c) =>
  c.json({ name: "regulasi-id-api", status: "ok", environment: c.env.ENVIRONMENT })
)

app.route("/api/v1/search", search)
app.route("/api/v1/regulations", regulations)
app.route("/api/v1/sectors", sectors)
app.route("/api/v1/compliance", compliance)
app.route("/api/suggestions", suggestions)
app.route("/api/openapi.json", openapi)
app.route("/api/admin", admin)

app.notFound((c) =>
  c.json({ error: "Sumber daya tidak ditemukan.", code: "NOT_FOUND" }, 404)
)

app.onError((err, c) => {
  // Hono throws HTTPException for known cases (rate limit, auth). Pass those through.
  if (err instanceof HTTPException) {
    return err.getResponse()
  }
  // Everything else is unexpected. Capture and return a generic 500.
  Sentry.captureException(err)
  return c.json(
    { error: "Terjadi kesalahan internal. Coba lagi nanti.", code: "INTERNAL_ERROR" },
    500
  )
})

export default Sentry.withSentry(
  (env: Env) => ({
    dsn: env.SENTRY_DSN,
    environment: env.ENVIRONMENT,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  }),
  app
)
