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

## Pre-built image

A Docker image is published to GitHub Container Registry on every release:

```bash
docker pull ghcr.io/hybridindie/godot-mcp:latest
# or a specific version:
docker pull ghcr.io/hybridindie/godot-mcp:2026.08.26b1
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

- `ghcr.io/hybridindie/godot-mcp:<version>` (e.g. `2026.08.26b1`)
- `ghcr.io/hybridindie/godot-mcp:latest`