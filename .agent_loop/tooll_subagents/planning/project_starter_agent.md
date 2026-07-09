# Project Starter Agent

## Role

Planning agent that picks and materializes a ready-to-use project starter for a client order. Based on the `client_brief` it selects one of four templates (landing, SaaS, portfolio, e-commerce), resolves the target stack, and emits a `starter_package` containing concrete files, install/run commands, README, and `.env.local.example` so execution agents can scaffold the project without human drafting.

## Contract

### Receives
- `client_brief`: from `tooll_subagents/user/client_brief_agent.md`
- `design_blueprint`: optional structured object from `figma_design_analyst.md`
- `copy_package`: optional from `copywriting_agent.md`
- `proposal_package`: optional from `estimation_proposal_agent.md`
- `project_rules`: dict | None

### Returns
- `starter_package`: structured object:
  - `template_id`: enum (`landing`, `saas`, `portfolio`, `ecommerce`)
  - `template_name`: str
  - `stack`: { `framework`, `styling`, `ui_kit`, `auth`, `cms`, `analytics`, `i18n`, `pwa`, `hosting` }
  - `files`: list[{ `path`, `content` }] — concrete files ready to write
  - `commands`: list[str] — install and run commands
  - `readme`: str — project README
  - `env_example`: str — `.env.local.example` contents
  - `next_steps`: list[str]
  - `confidence`: float 0.0–1.0
  - `missing_inputs`: list[str]
  - `next_phase_hint`: enum (`execution`, `result`, `planning`)

### Side effects
- Logs starter selection to `audit_logger.md`
- Does not write files directly; downstream execution agents consume `starter_package.files`

## Decision Flow

1. **Validate inputs** — require `client_brief.business_goal`. If critical fields (`target_audience` or `ctas`) are missing, set `missing_inputs` and lower `confidence`, but continue with defaults.
2. **Select template** from brief signals:
   - `saas` — signals: "SaaS", "подписка", "subscription", "dashboard", "sign-in", "sign up", "auth", "billing", "product"
   - `portfolio` — signals: "portfolio", "портфолио", "кейсы", "работы", "галерея", "projects", "works"
   - `ecommerce` — signals: "ecommerce", "магазин", "товары", "корзина", "checkout", "shop", "store", "buy"
   - `landing` — default or signals: "лендинг", "landing", "продукт", "услуга", "продажа", "product", "service"
3. **Resolve stack** — use `client_brief.technical_stack` or `project_rules.tooling_preferences`:
   - `framework` default `nextjs-app-router`
   - `styling` default `tailwind-css`
   - `ui_kit` default `shadcn-ui` for SaaS/landing, `none` if custom design is explicit
   - `auth`, `cms`, `analytics`, `i18n`, `pwa` enabled only when brief or blueprint explicitly signals them
   - `hosting` default `vercel`
4. **Build file manifest**:
   - `package.json` with dependencies matching the stack (Next.js, React, Tailwind, clsx, tailwind-merge, plus optional next-intl, @clerk/nextjs, @auth0/nextjs-auth0, prismisma, @vercel/postgres, etc.)
   - `next.config.js` or `next.config.ts` with i18n/PWA/image/domain hints when enabled
   - `tailwind.config.ts` + `app/globals.css` (or `src/app/globals.css`)
   - `app/layout.tsx` with metadata, SafeLink/ResponsivePicture/TouchSafeElement providers when needed
   - `app/page.tsx` with starter sections matching template
   - `src/lib/utils.ts` (cn helper)
   - `src/components/safe/SafeLink.tsx`, `ResponsivePicture.tsx`, `TouchSafeElement.tsx`
   - `README.md` with template overview, commands, stack, next steps
   - `.env.local.example` with placeholder vars for enabled integrations
   - Optional i18n: `messages/en.json`, `src/i18n/config.ts`, `middleware.ts`
   - Optional auth: `src/app/sign-in/page.tsx`, `src/components/auth/AuthProvider.tsx`
   - Optional CMS: `src/lib/cms.ts`, sample content directory
5. **Generate starter content** for `page.tsx` using `copy_package` when available; otherwise use template placeholder copy that matches `client_brief.business_goal` and CTAs.
6. **Build commands** — `npm install` (or `pnpm install`), `npm run dev`, and any post-install steps (e.g., `npx prisma migrate dev` if CMS/backend enabled).
7. **Set next_steps** — e.g. "Run dev server", "Connect Figma URL", "Fill .env.local", "Add real copy".
8. **Route** — if request explicitly asks for a starter/scaffold/bootstrap or `output_mode` includes `starter`, set `next_phase_hint=execution` so files are written. Otherwise return to `result` with the starter plan/readme for review, or attach as a planning artifact (`planning`).

## Failure Modes

| Condition | Response |
|---|---|
| `client_brief` is empty or `business_goal` missing | Return low-confidence `landing` starter with generic copy and `missing_inputs` |
| Unknown/unsupported stack requested | Fall back to `nextjs + tailwind + shadcn-ui`; flag `stack_fallback` |
| `design_blueprint` conflicts with template | Prefer blueprint scope (e.g., e-commerce sections override landing default) |
| Policy blocks scaffolding for requested stack | Render neutral plan only (`files=[]`, `readme`); do not emit install commands |
| Output directory already contains files | Include a `safe_overwrite_warning` in `next_steps`; do not force overwrite |
