import { Hono } from "hono"
import { z } from "zod"
import {
  SearchSchema,
  ListRegulationsSchema,
  ComplianceSchema,
  SuggestionSchema,
} from "@regulasi-id/shared/schemas"
import type { Env } from "../types"

// Convert a Zod schema to JSON Schema (input side). Falls back to a generic
// object if a schema uses a construct that cannot be represented.
function jsonSchema(schema: z.ZodType): Record<string, unknown> {
  try {
    return z.toJSONSchema(schema, { io: "input" }) as Record<string, unknown>
  } catch {
    return { type: "object" }
  }
}

// OpenAPI 3.1 document built from the shared Zod schemas (single source of truth).
export function buildOpenApiDocument(): Record<string, unknown> {
  return {
    openapi: "3.1.0",
    info: {
      title: "regulasi-id API",
      version: "1.0.0",
      description: "Open API for Indonesian OJK financial regulations.",
    },
    servers: [{ url: "https://api.regulasi.id" }],
    components: {
      schemas: {
        SearchRequest: jsonSchema(SearchSchema),
        ListRegulationsQuery: jsonSchema(ListRegulationsSchema),
        ComplianceQuery: jsonSchema(ComplianceSchema),
        SuggestionRequest: jsonSchema(SuggestionSchema),
      },
    },
    paths: {
      "/api/v1/search": {
        post: {
          summary: "Hybrid search over OJK regulations",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: { $ref: "#/components/schemas/SearchRequest" },
              },
            },
          },
          responses: { "200": { description: "Search results" } },
        },
      },
      "/api/v1/regulations": {
        get: {
          summary: "List regulations (cursor-paginated)",
          responses: { "200": { description: "Regulation list" } },
        },
      },
      "/api/v1/regulations/akn/id/act/{type}/{year}/{number}": {
        get: {
          summary: "Get a regulation with its document nodes",
          parameters: [
            { name: "type", in: "path", required: true, schema: { type: "string" } },
            { name: "year", in: "path", required: true, schema: { type: "string" } },
            { name: "number", in: "path", required: true, schema: { type: "string" } },
          ],
          responses: {
            "200": { description: "Regulation detail" },
            "404": { description: "Not found" },
          },
        },
      },
      "/api/v1/sectors": {
        get: {
          summary: "Sector list with stats",
          responses: { "200": { description: "Sectors" } },
        },
      },
      "/api/v1/compliance": {
        get: {
          summary: "Compliance checklist by sector and business type",
          responses: { "200": { description: "Applicable regulations" } },
        },
      },
      "/api/suggestions": {
        post: {
          summary: "Submit a correction",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: { $ref: "#/components/schemas/SuggestionRequest" },
              },
            },
          },
          responses: { "201": { description: "Created" } },
        },
      },
    },
  }
}

const openapi = new Hono<{ Bindings: Env }>()

openapi.get("/", (c) => {
  c.header("Cache-Control", "public, max-age=3600")
  return c.json(buildOpenApiDocument())
})

export default openapi
