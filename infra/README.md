# Infrastructure

Containerized delivery and Kubernetes deployment for godot-mcp.

## Structure

```
infra/
├── Dockerfile              # MCP server image (HTTP transport)
├── docker-compose.yml      # Local container run
├── runner.Dockerfile       # CI runner image (Godot + Python)
├── k8s-runner-godot.yml    # K8s deployment for Godot runner
├── k8s-runner-linux.yml    # K8s deployment for Linux runner
└── README.md               # This file
```

## CI runner images

`runner.Dockerfile` and the `k8s-runner-*.yml` deployments are deliberately owned
here. The `[self-hosted, godot]` runner needs Godot 4.7 baked in for this repo's
e2e suite; moving the runner build into a consumer would couple this repo's CI to
that consumer.

`.github/workflows/runner-image.yml` builds and pushes
`ghcr.io/hybridindie/godot-mcp-runner`. Manual dispatch is the intended rebuild
path; Dockerfile/workflow changes also trigger a build. The GHCR package must
grant `hybridindie/godot-mcp` write access for the workflow's `GITHUB_TOKEN` to
push (issue #706).

## Godot Asset Store

The addon zip (`addon_dist/godot_mcp_addon.zip`) is attached to every GitHub
release. The new store (<https://store.godotengine.org>) uses the coordinates
publisher `john-d-studios`, asset `godot-editor-mcp-addon` (internal asset ID
`3101`).

There is **no public upload/publish endpoint** yet. The beta store's v1 API is
read-only for assets/releases, and the roadmap says a CLI for CI uploads is
planned. Upload the zip through the store's logged-in manage UI for now.

Useful API endpoints:

- Docs: <https://store.godotengine.org/api/v1/redoc>
- OpenAPI: <https://store.godotengine.org/api/v1/openapi.json>
- Verify releases:
  `curl -fsSL 'https://store.godotengine.org/api/v1/releases/john-d-studios/godot-editor-mcp-addon/?stable_only=true'`

The legacy `godotengine.org/asset-library` endpoint is **not** used: its asset
IDs are a different namespace (legacy `3101` is another asset).

## Pre-built image

A Docker image is published to GitHub Container Registry on every release:

```bash
docker pull ghcr.io/hybridindie/godot-mcp:latest
# or a specific version:
docker pull ghcr.io/hybridindie/godot-mcp:2026.10.20.1
```

Run it:

```bash
docker run -d \
  -p 9090:9090 \
  -p 9080:9080 \
  -e GODOT_MCP_AUTH_TOKEN=your-token \
  ghcr.io/hybridindie/godot-mcp:latest
```

The server listens on:
- `http://localhost:9090` — MCP HTTP transport
- `ws://localhost:9080` — WebSocket bridge (the Godot editor connects here)

## Build locally

```bash
docker compose -f infra/docker-compose.yml build
docker compose -f infra/docker-compose.yml up
```

## Run

```bash
docker compose -f infra/docker-compose.yml up
```

The server listens on `http://localhost:9090`.

## Bridge networking

Since the bridge inversion (#276) the **server is the listener** and the Godot editor
connects *in*, so the container publishes the bridge port and binds all interfaces:

- In the container (compose `environment`): `GODOT_MCP_BRIDGE_URL: ws://0.0.0.0:9080`, and
  published: `ports: ["9080:9080"]`.
- On the host, point the editor's addon at the published port:
  `GODOT_MCP_BRIDGE_URL=ws://127.0.0.1:9080`.
- Binding `0.0.0.0` relaxes the localhost-only default — only do this on a trusted host.
  The server refuses a non-loopback bind without `GODOT_MCP_AUTH_TOKEN`; clients pass
  the token as `auth=<token>` (see [#226](https://github.com/hybridindie/godot-mcp/issues/226)).

## Mounting a project

Uncomment the `volumes` line in `docker-compose.yml` to mount a host project directory:

```yaml
volumes:
  - /path/to/your/godot/project:/project:ro
```

Then set `GODOT_MCP_PROJECT_DIR=/project` so tools like `run_and_capture` resolve paths
correctly.

## Healthcheck

The container includes a `HEALTHCHECK` that verifies the HTTP server is listening on
port 9090 via a lightweight socket probe. When healthy, the server is up and accepting
MCP connections.

## Publishing

Docker images are built and pushed automatically by `.github/workflows/publish.yml` on
GitHub release publish. The image is tagged with both the release version and `latest`:

- `ghcr.io/hybridindie/godot-mcp:<version>` (e.g. `2026.10.20.1`)
- `ghcr.io/hybridindie/godot-mcp:latest`