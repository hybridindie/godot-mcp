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

## Build

```bash
cd docker
docker compose build
```

## Run

```bash
docker compose up
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
  Auth for the HTTP transport is tracked in [#226](https://github.com/hybridindie/godot-mcp/issues/226).

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
