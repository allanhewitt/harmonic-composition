# Deploying with Coolify

Same pattern as gdlit-runtime: one Docker image built from the repository, a health check, a persistent `/data` volume.

## Coolify settings

| Setting | Value |
| --- | --- |
| Source | GitHub, `allanhewitt/harmonic-composition`, branch `main` |
| Build pack | Dockerfile |
| Port | 3000 |
| Health check | `/health` (the image also has a Docker `HEALTHCHECK`) |
| Persistent storage | a volume mounted at `/data` (saved scripts in `/data/pieces`, generated runs in `/data/runs`) |
| Build argument (optional) | `HC_BUILD_REVISION` = commit SHA, shown nowhere yet but kept in the image |

## Environment variables

| Variable | Purpose |
| --- | --- |
| `HC_PASSWORD` | Turns on HTTP basic authentication for everything except `/health`. Leave unset to rely on Coolify's own basic auth instead, or for a local test. |
| `HC_USERNAME` | Optional user name for the above (any user name is accepted if unset). |
| `HC_DATA_DIR` | Defaults to `/data`. |
| `PORT` | Defaults to 3000. |

## Before relying on it

1. Push to `main`; wait for the **Tests** and **Container smoke test** workflows to pass.
2. Deploy to a separate rehearsal application first and generate the example piece (Example → night_transit → Generate).
3. Check that a redeploy keeps saved scripts (the `/data` volume).

Runs accumulate in `/data/runs`; delete old ones from the volume when needed (automatic clean-up is a later task).
