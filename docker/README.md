# Docker delivery for godot-mcp

Containerized HTTP transport for the godot-mcp server. This lets consumers deploy or run
the MCP server without a local Python toolchain.

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

The default `GODOT_MCP_BRIDGE_URL` is `ws://host.docker.internal:9080`, which reaches a
Godot editor running on the Docker host. On Linux you may need to add
`extra_hosts: ["host.docker.internal:host-gateway"]` to the compose service.

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
