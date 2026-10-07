> 历史设计/验收记录，保留原内容供追溯。旧命令和状态不代表当前实现；入口见[项目README](../../README.md)。

# Reliability Improvements

Implemented after the UI refactor on 2026-09-13. The UI research and its earlier
verification baseline remain in [ui-refactor.md](../ui-refactor.md).

## Generation Contracts

- Every requested section has an independent `section_id`. Responses are matched
  by that ID, not by array position or the first occurrence of a question type.
  Legacy responses without IDs are accepted only when the type is unambiguous.
- Counts remain attached to the original request. Invalid and duplicate questions
  are removed, reading passages are preserved, and missing questions are reported
  explicitly. No placeholder stem is substituted for malformed model output.
- QC uses bounded AST arithmetic, not `eval`, for supported numeric expressions.
  It checks option indices, pairs, comparisons, splits, prohibited patterns, and
  duplicates. The fixed evaluation fixture has 26 cases; it is not a claim that
  arbitrary reasoning, language, or curricular correctness can be proven.
- Repair calls are sequential and share one bounded per-request budget. Reading
  sections are excluded from automatic repair to avoid mixing unrelated passages.

## Recovery And Cost Controls

The database admits a `(user_id, request_id)` once. Reusing it with different
parameters conflicts. Successful non-streaming responses can be retrieved without
another model call; uncertain or expired requests are never silently rerun.
The frontend persists immutable conditions and chunk IDs, uses GET-only recovery,
and asks for explicit manual retry before creating replacement request IDs.
Completed chunks are retained when an incomplete paper is retried.

| Setting | Default | Meaning |
| --- | --- | --- |
| `GENERATION_DAILY_LIMIT` | 100 | Accepted requests per user in a rolling 24-hour window |
| `GENERATION_USER_CONCURRENCY` | 3 | Active requests per user |
| `GENERATION_GLOBAL_CONCURRENCY` | 6 | Active requests across the shared database |
| `GENERATION_REPAIR_LIMIT` | 3 | Maximum additional repair calls per request; zero disables repair |
| `GENERATION_LEASE_SECONDS` | 3600 | Admission lease; execution deadline ends five seconds earlier |
| `GENERATION_RESULT_DAYS` | 7 | Retention of successful response bodies |

Single, batch, streaming, and validation endpoints share these controls. One
paper can require multiple requests, and one request can require multiple model
calls. Failed accepted requests count toward the request quota. Streamed content
is not cached for replay. Old result bodies are hidden immediately at expiry and
cleaned opportunistically on later admissions; deduplication metadata is retained.

Only provider-reported prompt/completion tokens are counted. Missing provider
usage is not estimated, so these figures are not a billing statement or monetary
spending cap. `ConnectError` permits bounded retries; read/write/protocol errors
do not. Client cache eviction skips active borrowers and converges to its limit
after borrowers finish.

## Drafts And Templates

- IndexedDB stores account-owned drafts and immutable history. Each page gets a
  separate writer ID; reload restores that page's draft when available, otherwise
  the latest draft for the account. Drafts are not cross-device cloud backups.
- History records generated papers and manual versions. Restoring history or
  replacing previous results/pending requests first saves a recovery copy.
  A failed recovery write blocks replacement instead of discarding current work.
- Drafts retain pending whole-paper and single-section request identities. Reload
  never starts a model request. Storage failures keep the current in-memory content.
- Account changes suspend generation, save under the original owner, and reload
  only after a successful save. Failed logout saves also block leaving the page.
  `X-Workspace-User` detects a stale tab using a different account's session cookie;
  authentication and authorization still use the cookie, not this optional header.
- Templates use optimistic revisions. Updates and deletion reject stale versions;
  per-user monotonic counters prevent delete/recreate revision reuse. Offline
  changes remain local and conflicts can be copied under a new name. Legacy bulk
  imports create missing names only; no silent pruning of older local templates.

## Deployment

1. Use Python 3.11+, Node.js 22.12+, and the committed pnpm lockfiles. Install
   `requirements.txt`, including `cryptography`, and build both frontends.
2. Back up the database and effective secret before restarting the backend.
   New tables, indices, and revision fields are added without replacing user data.
   Test migrations against a copy of production data before a production rollout.
3. Configure a stable `SECRET_KEY` across workers/instances. Older releases ignored
   the value in `.env`; affected sessions need a new login. Keep the historical
   `data/secret_key.txt` until older model credentials have been re-saved. Its
   fallback is decryption-only, not an additional accepted session signing key.
4. New model keys require Fernet encryption. Legacy base64 credentials remain
   readable for compatibility, but new keys never fall back to plaintext/base64.
5. HTTPS deployments should use `FORCE_HTTPS=true`, a restricted origin list, and
   a seeded administrator before allowing public registration. Review the admin
   overview's security warnings and tune quotas for the actual provider budget.

## Verification

Run from the repository root after installing dependencies:

```sh
pnpm --dir web typecheck
pnpm --dir web test
pnpm --dir web build
pnpm --dir admin typecheck
pnpm --dir admin test
pnpm --dir admin build
python -m unittest discover -s tests -p 'test_backend*.py' -v
python tests/run_ui_contracts.py
git diff --check
```

The admin component suite exercises actual Vue event handlers for batch tag
selection, publication consent, knowledge-point creation and server pagination.
Backend tests use disposable PostgreSQL databases and cover independent lock
domains, cross-domain exclusion, readiness timeouts and event-loop responsiveness.
The isolated API runner checks eight API contracts and 12 admin-console cases.
It binds a temporary loopback port and shuts down the fixture on test failure.
LLM calls are stubbed below the real generation routes, so normalization, metering,
request identity, and API responses are exercised without paid traffic.

Browser checks include repeated 4+6 sections, desktop/mobile history layouts,
restoring an eight-question version while preserving a ten-question recovery
copy, draft reload, and pending-request recovery without increasing request usage.
Reading partial-result checks preserve the passage and show requested/actual/missing
counts. Two independent pages exercise a real template revision conflict and save
the local version as a separate template without overwriting the server version.
The admin overview reconciles five requests, four completions, one uncertain
request, 11 model attempts, and ten provider usage reports in the fixture. Desktop
and 390px mobile views were checked, including long warning text and the usage
section; no page-level horizontal overflow or console errors remained.

Both frontends pass typechecking and production builds. The workbench entry chunk
is 292.56 kB (77.93 kB gzip), excluding other lazy chunks and styles. This is a
build artifact measurement, not a browser performance or total transfer budget.

GitHub Actions runs the automated checks on push and pull requests; the remote
workflow has not been executed as part of this local change. Paid model quality,
PostgreSQL integration, and cross-instance load have not been verified locally.
The quotas are admission protection, not a durable background job queue. Browser
storage remains subject to user deletion, origin changes, and storage quotas.

## Database concurrency and readiness

Transactions use explicit PostgreSQL advisory-lock domains in `app/db.py`:

- `content` (`serialized=True` for compatibility): archives, publication,
  dictionaries, favorites and other content operations.
- `accounts`: consumer sessions, orders, refunds, membership grants, manual
  renewals and subscription delivery. These operations keep a shared lock so
  refunds, manual changes and account closure cannot lose entitlement updates.
- `generation`: request deduplication and global/user admission quotas.
- `schema`: startup migrations acquire every domain before applying DDL.

Account deletion, closure approval, permission-checked downloads and inbox
operations acquire both content and account domains. `db()` sorts and deduplicates
lock IDs before acquiring them. Do not nest a second locking `db()` inside an
existing transaction: pass the connection to helpers instead. Any new operation
that crosses domains must acquire all its domains at transaction entry. Deploy
this change by restarting all app workers together; do not mix workers using the
previous single-lock implementation with the new implementation.

Synchronous database/hash/file operations run in FastAPI's worker thread pool;
async generation handlers offload scope/config lookups with `asyncio.to_thread`.

`GET /health` reports process liveness. `GET /readyz` probes the existing database
pool (1 second to acquire a connection, 1 second statement timeout), returns 503
on failure and never exposes connection details. The HTTP response is bounded to
2.5 seconds; overlapping requests share a pending probe to avoid creating more
threads when a connection is stuck. Docker uses readiness for its health check.

`GET /api/v1/admin/users` accepts `limit` (1–100, default 20) and `offset` (>=0),
and returns `{users, total, limit, offset}` with role/search filters applied to
both the count and page. Clients must paginate instead of assuming `users`
contains the complete account list.
