# syntax=docker/dockerfile:1
#
# Custom GitHub Actions runner image with the Godot 4.7 editor binary baked in.
# Serves the [self-hosted, godot] runner label for the e2e (godot-mcp) and
# gle-bench (godot-agents) workflows. Built FROM the stock actions-runner image
# so the runner internals stay identical — only Godot is added.
#
# The binary lands at /opt/godot/godot, which is the default GODOT_BIN path the
# e2e workflow reads (vars.GODOT_BIN || '/opt/godot/godot'), so no workflow
# changes are needed.
#
# Build context is docker/runner/. Build from repo root:
#   docker build -f docker/runner/Dockerfile -t ghcr.io/hybridindie/godot-mcp-runner:4.7 .
# or via .github/workflows/runner-image.yml.
FROM summerwind/actions-runner:v2.336.0-ubuntu-24.04

ARG GODOT_VERSION=4.7-stable
ARG GODOT_ASSET=Godot_v4.7-stable_linux.x86_64.zip

# Install unzip (the runner image may not have it), then download and extract
# the official Godot editor binary into /opt/godot. The editor build (not the
# export template) is required — the e2e suites use --headless --editor.
RUN sudo apt-get update \
    && sudo apt-get install -y --no-install-recommends unzip \
    && sudo rm -rf /var/lib/apt/lists/* \
    && sudo mkdir -p /opt/godot \
    && curl -fsSL -o /tmp/godot.zip \
        "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/${GODOT_ASSET}" \
    && sudo unzip -o /tmp/godot.zip -d /opt/godot \
    && sudo chmod +x /opt/godot/Godot_v${GODOT_VERSION}_linux.x86_64 \
    && sudo ln -sf /opt/godot/Godot_v${GODOT_VERSION}_linux.x86_64 /opt/godot/godot \
    && rm -f /tmp/godot.zip

# Sanity: the binary runs and reports the expected version. Fails the build
# early if the download was corrupt or the architecture is wrong.
RUN /opt/godot/godot --version | grep -q "^4.7" \
    || (echo "::error::Godot binary did not report 4.7.x" && exit 1)

ENV GODOT_BIN=/opt/godot/godot