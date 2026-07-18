# Activity Policy Control Plane

Security activity monitoring and policy enforcement across connected developer, cloud, project-management, and identity vendors.

## Documentation

Start with the [project documentation index](./docs/README.md):

- [Product requirements](./docs/PRODUCT_REQUIREMENTS.md)
- [Technical specification](./docs/TECHNICAL_SPECIFICATION.md)
- [Implementation architecture](./docs/IMPLEMENTATION_ARCHITECTURE.md)
- [Architectural flow diagram](./docs/ARCHITECTURAL_FLOW.md)

The documents describe the four dashboard areas—Vendors, Policy Agent, Deployed Policies, and Actions—and define the first implementation as a GitHub-to-policy-to-monitoring vertical slice.

The planned stack uses self-hosted open-source/free components: React/Vite, FastAPI, PostgreSQL, NATS JetStream, Valkey, Keycloak, OpenBao, MinIO, Ollama, Prometheus, Grafana, Loki, Docker, and Kubernetes.

## Demo video

[Watch the product walkthrough](./Screencast%20from%202026-07-18%2017-29-48.webm)

The walkthrough covers GitHub connection setup, connection diagnostics, repository discovery, live activity events, policy generation, policy testing, and deployment.

## Run locally

For the fastest UI demo, run the frontend without an API configured:

```bash
cd frontend
npm install
npm run dev
```

The UI uses realistic demo data only when no API URL is configured and clearly labels demo mode. To run the backend vertical slice locally:

```bash
python3 -m pip install -e backend
python3 -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Then start the frontend with `VITE_API_BASE_URL=http://localhost:8000 npm run dev` to use the live API. Open `http://localhost:5173`; the backend is available at `http://localhost:8000` and its OpenAPI UI is at `/docs`.

The working local persistence adapter is SQLite at `backend/data/activity.db` (override with `ACTIVITY_DB_PATH`). It persists connections, normalized events, policy drafts, policies, evaluations, actions, and audit state, while intentionally keeping raw credential values out of SQLite. The GitHub PAT remains process-held in this local adapter; production should replace that adapter with OpenBao before relying on restart-persistent credentials. The PostgreSQL/NATS/Valkey/OpenBao services in `docker-compose.yml` are self-hosted infrastructure scaffolding; the current vertical slice does not claim those services are already wired into the API.

Without `VITE_API_BASE_URL`, the frontend runs an explicitly labeled local demo dataset. With the API URL configured, API errors produce an empty/error state rather than substituting demo records.

## Usage: live GitHub-to-policy demo

1. Start the backend and frontend using the live API commands above.
2. Open `http://localhost:5173` and go to **Vendors**.
3. Select **Connect vendor**, choose GitHub, and enter the organization login, organization URL, `https://api.github.com`, and a GitHub personal access token. The token is tested by the backend and is not displayed back in the UI.
4. Click **Test GitHub connection**. The connector validates the token, lists accessible organization repositories, polls repository activity, and displays the normalized events. If organization repositories are empty, it falls back to repositories accessible to the authenticated account.
5. Open **Policy Agent** and use this demo prompt:

   > Flag GitHub repository commits made between 01:00 and 05:00 UTC. Commits outside that window should pass.

6. Click **Generate policy**, review the generated artifact, then click **Test policy**. The built-in scenarios include both a matching after-hours commit and non-matching daytime/boundary events; all scenarios must pass before deployment is allowed.
7. Click **Deploy policy**. The enabled policy evaluates subsequent normalized GitHub events. A commit at `02:30 UTC` should produce a `SUSPICIOUS_QUIET_HOURS` match; a commit at `12:30 UTC` should produce `OUTSIDE_POLICY_SCOPE`.
8. Review evaluations under **Deployed Policies** and configure an **Action**. Dry-run and approval modes are safe for demonstrations; external provider-side blocking/MFA integrations require provider configuration.

### Live API endpoints

- `POST /api/v1/connections` — create a GitHub connection.
- `POST /api/v1/connections/{id}/test` — validate credentials and ingest a sample.
- `GET /api/v1/connections/{id}/events?refresh=true` — refresh repository events.
- `GET /api/v1/connections/{id}/repositories` — list accessible repositories.
- `POST /api/v1/webhooks/github/{id}` — accept a normalized GitHub webhook event.
- `POST /api/v1/policy-drafts/{id}/generate` — generate a policy artifact.
- `POST /api/v1/policy-drafts/{id}/test` — run pass/fail policy scenarios.
- `POST /api/v1/policy-drafts/{id}/deploy` — deploy only after all mandatory scenarios pass.

For production use, keep PATs in a secret manager, configure GitHub webhooks for near-real-time delivery, and rotate any credential that has been exposed during testing.

## Verification

```bash
python3 -m pytest backend/tests -q
cd frontend && npm test -- --run && npm run build
```
