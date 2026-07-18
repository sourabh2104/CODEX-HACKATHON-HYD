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

## Verification

```bash
python3 -m pytest backend/tests -q
cd frontend && npm test -- --run && npm run build
```
