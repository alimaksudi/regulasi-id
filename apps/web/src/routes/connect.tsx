import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/connect")({
  component: ConnectPage,
})

const SNIPPET = "claude mcp add --transport http regulasi-id https://mcp.regulasi.id/mcp"

function ConnectPage() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-bold">Hubungkan ke Claude (MCP)</h1>
      <p className="mt-2 text-neutral-600">
        Beri Claude akses langsung ke teks peraturan OJK melalui MCP server kami.
      </p>

      <ol className="mt-6 list-decimal space-y-3 pl-5 text-neutral-800">
        <li>Pastikan Claude Code atau Claude Desktop terpasang.</li>
        <li>Jalankan perintah berikut di terminal:</li>
      </ol>

      <pre className="mt-3 overflow-x-auto rounded-md bg-neutral-900 p-4 text-sm text-neutral-100">
        <code>{SNIPPET}</code>
      </pre>

      <p className="mt-4 text-sm text-neutral-500">
        Tanpa garis miring di akhir <code>/mcp</code>. Tools yang tersedia:
        search_regulations, get_article, get_regulation_status,
        get_compliance_checklist, list_regulations.
      </p>
    </main>
  )
}
