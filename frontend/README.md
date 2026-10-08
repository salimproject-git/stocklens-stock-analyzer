# StockLens frontend

Next.js 16 (App Router) + React 19 + Tailwind CSS 4 application for StockLens.

The frontend is a **read-only consumer of the database**. It holds no market data of
its own and recomputes no business metric: every figure on screen either arrives from
a Supabase RPC or is a presentation-only transform (rounding, locale, unit label,
colour). See the root [`README.md`](../README.md) for the full data flow.

## Run

```powershell
Set-Location 'D:\Stock Analyzer\frontend'
Copy-Item .env.example .env.local   # then fill in the two values
npm install
npm run dev                         # http://localhost:3000
```

## Environment

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | yes | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | yes | Publishable (`sb_publishable_...`) or legacy `anon` key |

Both are read inside `src/lib/stock-data.ts`, which begins with `import "server-only"`.
That guard is what keeps the client out of the browser bundle, so the keys must stay
**unprefixed** — do not rename them to `NEXT_PUBLIC_*`. The Supabase `service_role`
key must never be added here at all.

## Structure

```text
src/app/
  page.tsx                     redirects to /market
  market/page.tsx              server component; calls get_market_overview_page
  market/[ticker]/page.tsx     server component; calls the three per-ticker RPCs
src/lib/
  stock-data.ts                the only module that talks to Supabase
  stock-detail-adapter.ts      maps RPC payload -> view model
  stock-types.ts               market row types
  analysis/                    classification rules (signals, MoS, growth labels)
src/components/
  app-shell.tsx                sidebar + layout
  market-overview-page.tsx     screener: filters, sorting, grid/table views
  stock-research/              the five research tabs
```

## Scripts

```powershell
npm run dev      # development server
npm run build    # production build
npm run start    # serve the production build
npm run lint     # eslint
```

## Notes

- `src/data/mock-stock-details.ts` is a **retired sample-data fixture** kept only so the
  offline frontend tests still resolve. No application route imports it; the live pages
  read Supabase exclusively.
- There is no client-side data fetching and no Supabase call from the browser. The
  publishable key is used from the server only.