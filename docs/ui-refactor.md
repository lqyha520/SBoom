# UI Refactor

## Scope

- Keep Vue, Pinia, FastAPI, authentication, API contracts, and stored templates.
- Upgrade to Vite 8, Nuxt UI 4, and Tailwind CSS 4. Use TypeScript 6 with vue-tsc.
- Share design tokens between the independently built web and admin applications.
- Bundle Lucide icons locally. Do not require a public font or icon service at runtime.

## Research And Choice

Official documentation and npm metadata checked on 2026-09-13.

| Candidate | Assessment for this project |
| --- | --- |
| [Nuxt UI 4](https://ui.nuxt.com/docs/getting-started/installation/vue) | Selected. Supports plain Vue/Vite, accessible controls, consistent theming, and local icon bundling without introducing a Nuxt server. |
| [PrimeVue 5](https://primevue.org/) | Strong alternative for data-heavy administration. Its wider component suite is useful, but the current workbench benefits more from a shared, compact theme and focused controls. |
| [shadcn-vue](https://www.shadcn-vue.com/) | Strong alternative when owning and extensively customizing component source is the priority. More component maintenance would remain in this repository. |

Validated versions: Vue 3.5.42, Vite 8.3.0, Nuxt UI 4.11.1, Tailwind CSS
4.3.3, TypeScript 6.0.3, vue-tsc 3.3.11, and Vitest 5.0.0. Node.js 22.12+
is required; verification used Node.js 22.23.2 and pnpm 10.14.0.

TypeScript 7.0.2 is already stable, but is deliberately not selected here.
vue-tsc 3.3.11 still resolves `typescript/lib/tsc` and uses the legacy compiler
API; the TypeScript 7 package no longer exports that path. The TypeScript
dependency stays on `~6.0.3` until the Vue checking pipeline is compatible.
See the [TypeScript 7 package metadata](https://registry.npmjs.org/typescript/7.0.2)
and [vue-tsc source](https://github.com/vuejs/language-tools/tree/v3.3.11/packages/tsc).

The official [Nuxt UI Agent Skill](https://ui.nuxt.com/docs/getting-started/ai/skills)
is a good match for future iterations: it covers installation, components,
theming, forms, and overlays, and supports Codex. The
[OpenAI curated skills](https://github.com/openai/skills/tree/main/skills/.curated)
also include Figma implementation and Playwright skills. No third-party skill
or MCP server was installed globally during this refactor. Browser validation
used the existing computer-use integration and its Playwright interface.

## Design

- White work surfaces, neutral gray canvas, emerald primary actions, sky information,
  amber warnings, and red destructive actions. Typography uses local system fonts.
- Desktop workbench: conditions, section editor, and the actual A4 preview.
- Small screens: accessible workspace tabs, with one full-width panel at a time.
- Admin: persistent navigation, dense tables, clear forms, and accessible overlays.
- Use Nuxt UI controls for forms, dialogs, tooltips, menus, status, and navigation.
- Keep decorative elements minimal. No marketing homepage or nested surface cards.

## Migration Boundaries

- Paper dimensions, pagination, rich-text editing, and export behavior remain intact.
- Paper CSS uses an isolated RGB token set, independent of Tailwind's OKLCH palette.
- Preserve separate frontend builds and same-origin production paths `/` and `/admin/`.
- Development proxies `/admin/` to the admin Vite server and `/api` to FastAPI.
- Do not modify user data or overwrite existing local configuration.

## Implementation

- Share `ui/theme.css` and `ui/config.mts` across both frontends.
- Split the workbench into conditions, type selection, section editing, templates,
  preview, and result views. Load dialogs and export code on demand.
- Split the admin console into overview, model settings, users, feedback, and logs.
- Keep loading, retry, empty, validation, confirmation, and permission states.
- Preserve template content and rich-text edits when reordering or loading papers.
- Match backend generation limits: 1-30 questions per section and at most ten
  unique generation types. Existing invalid templates are preserved, with
  generation blocked until corrected.
- Ignore stale knowledge responses, lock conditions while generating, distinguish
  local template saving from server synchronization, and repair fit-width reset.
- Preserve the existing local `admin/node_modules` Junction and use separate
  Vite cache directories for the two dev servers.

## Verification

Completed on 2026-09-13:

| Check | Result |
| --- | --- |
| `pnpm typecheck` in `web/` and `admin/` | Both passed |
| `pnpm build` in `web/` and `admin/` | Both passed |
| `pnpm test` in `web/` | 20 tests passed |
| `python tests/test_ui_contracts.py` | 6 isolated API contract tests passed |
| `python scripts/admin_console_check.py` against the fixture | 12 checks passed |
| Desktop and 390px mobile layouts | Verified workbench, results, and admin; no page-level horizontal overflow |
| Workbench interactions | Login, conditions, type selection, sorting, layout, editing, template round trips, multi-paper generation, answers, and result selection verified |
| Admin interactions | Role rejection, navigation, model form/test UI, self-protection, template inspection, search, empty create-form validation, feedback filtering, and logs verified |
| Actual downloads | PDF, PNG, and ZIP created and inspected |
| Development routing | Workbench `/` and proxied `/admin/` load with icons and no console errors |

The sample PDF is one A4 page (595.28 x 841.89 pt); the PNG is 2382 x 3369
and nonblank. The ZIP passes its integrity check and contains five PDFs:
two student papers, two answer papers, and one two-page combined paper.
Screenshots and sample exports are in the ignored `artifacts/ui-refactor/` folder.

The production web entry chunk is 265.60 kB (71.22 kB gzip). Export libraries
and secondary views are separate lazy-loaded chunks; this is not a total-page
transfer-size measurement.

### Isolated Test Service

After building both frontends, run these in separate terminals from the
repository root using a Python environment with the backend requirements:

```powershell
python tests/ui_fixture.py --port 8105
```

```powershell
$env:LC_TEST_BASE = 'http://127.0.0.1:8105'
python tests/test_ui_contracts.py
python scripts/admin_console_check.py
```

The fixture binds to loopback, creates a disposable SQLite database, reuses real
authentication/admin/template APIs, and stubs model generation and connection
tests. `test_ui_contracts.py` refuses to modify a service without the fixture
health marker. Never point mutation tests at an existing user database.

Real model output quality, paid API calls, and the native print dialog were not
tested. Existing backend configuration and user data were not changed.
Tailwind 4 requires modern browsers: Chrome 111+, Safari 16.4+, Firefox 128+.
