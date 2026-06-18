import { describe, it, expect } from "vitest"
import { encodeCursor, decodeCursor } from "../src/lib/cursor"

describe("cursor", () => {
  it("round-trips a cursor", () => {
    const c = { year: 2022, id: 42 }
    expect(decodeCursor(encodeCursor(c))).toEqual(c)
  })

  it("returns null for garbage", () => {
    expect(decodeCursor("not-base64-json")).toBeNull()
  })

  it("returns null when fields are missing or wrong type", () => {
    expect(decodeCursor(btoa(JSON.stringify({ year: "2022" })))).toBeNull()
    expect(decodeCursor(btoa(JSON.stringify({ id: 1 })))).toBeNull()
  })
})
