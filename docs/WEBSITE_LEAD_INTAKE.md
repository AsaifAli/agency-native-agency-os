# Website lead intake — Agency OS side

The public website remains a separate Next.js/Supabase application. It forwards a minimal lead envelope to the OS using HMAC-SHA256 over `timestamp + "." + raw_body`. The OS validates the configured key ID, signature, timestamp window, body size, Pydantic schema and idempotency key.

The request does not choose an organization or workspace. The API maps it to the fixed `WEBSITE_LEAD_INTAKE_ORG_ID` and `WEBSITE_LEAD_INTAKE_WORKSPACE_ID` server settings. A unique external key on the Lead prevents duplicate CRM records. The Contact, Lead, audit event and transactional outbox event are committed in one database transaction.

## Configuration

In the OS environment, keep intake disabled until the website side is ready:

- `WEBSITE_LEAD_INTAKE_ENABLED=false`
- `WEBSITE_LEAD_INTAKE_SECRET` — random secret, minimum 32 characters
- `WEBSITE_LEAD_INTAKE_KEY_ID=website-v1`
- `WEBSITE_LEAD_INTAKE_ORG_ID`
- `WEBSITE_LEAD_INTAKE_WORKSPACE_ID`
- `WEBSITE_LEAD_INTAKE_CLOCK_SKEW_SECONDS=300`

Website PR #30 was merged to `AsaifAli/asaifali-ai-service-agency` `main` as commit `89bbed3484b11b78db2b0ca3d98744cb409a8c48`. Its quality workflow passed lint, typecheck, production dependency audit, public-site structure checks, Next.js build, Playwright browser smoke tests and Lighthouse accessibility/SEO checks ([run 45467278242](https://github.com/AsaifAli/asaifali-ai-service-agency/actions/runs/45467278242)). The post-merge main workflow was pending at the last check. Website forwarding uses these server-only environment variables:
- `AGENCY_OS_LEAD_INTAKE_URL`
- `AGENCY_OS_LEAD_INTAKE_HMAC_SECRET`
- `AGENCY_OS_LEAD_INTAKE_KEY_ID`

The website migration adds a unique submission ID and sync status. The website keeps the original free-text enquiry in Supabase; the OS stores only name, email, optional company, project type, budget range, timeline and source. Consent remains unknown. No email to the visitor, call, quote, agent execution or other external side effect is triggered.

## Rollout and current status

The OS API endpoint and backend tests are merged to OS `main`. Website forwarding and admin retry are merged to website `main` via PR #30. The website PR quality workflow passed all configured checks, including browser smoke tests and Lighthouse; the post-merge main workflow was pending at the last check. Neither side has production credentials configured or a verified production deployment. Do not enable the bridge until the website Supabase migration and OS Alembic migration are applied, the two server secrets match, HTTPS is verified and a synthetic end-to-end test confirms idempotency, retry recovery and no automatic outreach.

The outbox event is persisted, but no production handler is registered yet.
