import { describe, it, expect } from "vitest"
import { buildOpenApiDocument } from "../src/routes/openapi"

describe("OpenAPI document", () => {
  const doc = buildOpenApiDocument() as any

  it("is an OpenAPI 3.1 document", () => {
    expect(doc.openapi).toBe("3.1.0")
    expect(doc.info.title).toBe("regulasi-id API")
  })

  it("documents the public endpoints", () => {
    expect(Object.keys(doc.paths)).toEqual(
      expect.arrayContaining([
        "/api/v1/search",
        "/api/v1/regulations",
        "/api/v1/sectors",
        "/api/v1/compliance",
        "/api/suggestions",
      ])
    )
  })

  it("derives request schemas from the shared Zod schemas", () => {
    const search = doc.components.schemas.SearchRequest
    expect(search.type).toBe("object")
    // q is a required string property on the search request
    expect(search.properties?.q).toBeDefined()
    expect(search.required).toEqual(expect.arrayContaining(["q"]))
  })

  it("is JSON-serializable", () => {
    expect(() => JSON.stringify(doc)).not.toThrow()
  })
})
