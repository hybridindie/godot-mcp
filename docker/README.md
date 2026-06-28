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

Since the bridge inversion (#276) the **server is the listener** and the Godot editor
connects *in*, so the container must publish the bridge port and bind all interfaces:

- In the container (compose `environment`): `GODOT_MCP_BRIDGE_URL: ws://0.0.0.0:9080`, and
  publish it: `ports: ["9080:9080"]`.
- On the host, point the editor's addon at the published port:
  `GODOT_MCP_BRIDGE_URL=ws://127.0.0.1:9080`.
- Binding `0.0.0.0` relaxes the localhost-only default — only do this on a trusted host.

> The bundled `docker-compose.yml` still carries the pre-inversion
> `ws://host.docker.internal:9080` and doesn't publish `9080` yet (the server dialed *out*
> to the host editor under the old direction). Apply the two changes above until the compose
> fix lands — tracked in [#285](https://github.com/hybridindie/godot-mcp/issues/285).

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
