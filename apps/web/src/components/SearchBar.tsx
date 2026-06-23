import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Search } from "lucide-react"
import { Button } from "~/components/ui/button"

export function SearchBar({ initialQuery = "" }: { initialQuery?: string }) {
  const [q, setQ] = useState(initialQuery)
  const navigate = useNavigate()

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (q.trim()) navigate({ to: "/search", search: { q: q.trim() } })
      }}
      className="flex gap-2"
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Cari peraturan, mis. modal minimum P2P lending"
        className="flex-1 rounded-md border border-neutral-300 px-4 py-2 outline-none focus:border-neutral-500"
      />
      <Button type="submit">
        <Search size={16} /> Cari
      </Button>
    </form>
  )
}
