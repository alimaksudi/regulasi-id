import { defineConfig } from "vitest/config"

// Node environment for pure-logic tests (schemas, cursor, OpenAPI doc).
// Live route tests against workerd need the Cloudflare pool and Node 22.
export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"],
  },
})
