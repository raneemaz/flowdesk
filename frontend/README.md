# FlowDesk Frontend

React + TypeScript SPA for FlowDesk. Feature pages (auth, dashboards,
domain modules) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
only the application skeleton exists so far (FD-003).

## Stack

Vite, React 19, TypeScript (strict mode), React Router, TanStack Query,
Tailwind CSS v4, shadcn/ui primitives, Vitest + React Testing Library.

## Structure

```
frontend/
  index.html
  vite.config.ts / vitest.config.ts
  tsconfig.json / tsconfig.app.json / tsconfig.node.json
  components.json        shadcn/ui CLI config (so `npx shadcn add <component>` works)
  src/
    main.tsx             React entry point
    App.tsx               QueryClientProvider + RouterProvider
    index.css             Tailwind import + design tokens (spec Section 12.1)
    lib/
      utils.ts            cn() class-merging helper
      queryClient.ts       shared TanStack Query client
    routes/
      router.tsx           route table (one smoke route so far)
    components/ui/
      button.tsx            shadcn Button primitive
    test/setup.ts           Vitest + jest-dom setup
```

Design tokens in `src/index.css` map directly to the colors in the spec's
design direction table (primary `#4F46E5`, background `#F8FAFC`, sidebar
`#111827`, etc.). Dark theme is explicitly optional in the spec and is not
implemented yet.

## Setup

```bash
cd frontend
npm install
```

Backend API base URL is read from `VITE_API_BASE_URL` (see the root
`.env.example`); not consumed by any code yet since no API calls exist.

## Running

```bash
npm run dev
```

## Type-checking, testing, building

```bash
npm run typecheck
npm run test
npm run build
```
