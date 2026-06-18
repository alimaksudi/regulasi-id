import {
  Outlet,
  createRootRoute,
  HeadContent,
  Scripts,
  Link,
} from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import appCss from "~/styles/globals.css?url"

// A per-request client is the production pattern; module-level is fine for the shell.
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000 } },
})

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "regulasi.id — Akses Terbuka Regulasi OJK" },
    ],
    links: [{ rel: "stylesheet", href: appCss }],
  }),
  component: RootComponent,
})

function RootComponent() {
  return (
    <RootDocument>
      <QueryClientProvider client={queryClient}>
        <Header />
        <Outlet />
      </QueryClientProvider>
    </RootDocument>
  )
}

function Header() {
  return (
    <header className="border-b border-neutral-200">
      <nav className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link to="/" className="font-semibold">
          regulasi.id
        </Link>
        <div className="flex gap-4 text-sm">
          <Link to="/search" search={{ q: "" }}>
            Cari
          </Link>
          <Link to="/connect">Connect MCP</Link>
        </div>
      </nav>
    </header>
  )
}

function RootDocument({ children }: { children: ReactNode }) {
  return (
    <html lang="id">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  )
}
