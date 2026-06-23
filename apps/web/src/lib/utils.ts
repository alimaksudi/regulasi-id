import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

// "pojk-10-2022" -> "/akn/id/act/pojk/2022/10"
export function slugToFrbr(slug: string): string {
  const parts = slug.split("-")
  const type = parts[0]
  const year = parts[parts.length - 1]
  const number = parts.slice(1, -1).join("-")
  return `/akn/id/act/${type}/${year}/${number}`
}
