// Opaque keyset cursor for list pagination (year DESC, id DESC).

export type Cursor = { year: number; id: number }

export function encodeCursor(c: Cursor): string {
  return btoa(JSON.stringify(c))
}

export function decodeCursor(s: string): Cursor | null {
  try {
    const o = JSON.parse(atob(s)) as Cursor
    if (typeof o.year === "number" && typeof o.id === "number") return o
    return null
  } catch {
    return null
  }
}
