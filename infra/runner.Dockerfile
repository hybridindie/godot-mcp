# syntax=docker/dockerfile:1
#
# Custom GitHub Actions runner image with the Godot 4.7 editor binary baked in
# (and the pinned 4.4 floor binary for the `godot-floor` CI job, issue #701).
# Serves the `hybridindie-godot-mcp-godot` runner scale set (fedora-only) for
# the e2e suites, and is the same image the apeiron pool mounts.
#
# The binary lands at /opt/godot/godot, which is the default GODOT_BIN path the
# e2e workflow reads (vars.GODOT_BIN || '/opt/godot/godot'), so no workflow
# changes are needed.
#
# Built FROM the stock actions-runner image so the runner internals stay
# identical — only Godot is added. It MUST be the upstream
# `ghcr.io/actions/actions-runner` image: ARC scale sets exec
# /home/runner/run.sh, and the old summerwind base only shipped
# /runner/run.sh, which exits immediately under a scale set.
#
# Build from the repo root:
#   docker build -f infra/runner.Dockerfile -t ghcr.io/hybridindie/godot-mcp-runner:4.7 .
# or via .github/workflows/runner-image.yml.
FROM ghcr.io/actions/actions-runner:2.338.2

# Build as root; the runner user has no passwordless sudo here. Switched back
# to `runner` at the end so the runtime layout matches the stock image.
USER root
ENV DEBIAN_FRONTEND=noninteractive

ARG GODOT_VERSION=4.7-stable
ARG GODOT_ASSET=Godot_v4.7-stable_linux.x86_64.zip

# Install unzip (the runner image may not have it) plus Godot's runtime deps.
# The editor binary needs the X11/Wayland/fontconfig libs even in --headless
# mode (it probes for a DisplayServer at startup; without the stub libs it
# exits with "all display drivers failed"). xvfb provides a dummy display so
# --headless --editor works in a container with no GPU/display attached.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        unzip \
        xvfb \
        libx11-6 libx11-xcb1 \
        libxcursor1 libxrandr2 libxinerama1 libxi6 \
        libgl1 libglu1-mesa \
        libpulse0 libfontconfig1 \
        libwayland-client0 libwayland-server0 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/godot \
    && curl -fsSL -o /tmp/${GODOT_ASSET} \
        "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/${GODOT_ASSET}" \
    # Supply-chain: verify the download against Godot's published SHA512 checksum
    # before extracting/executing. Never run an unverified binary.
    && curl -fsSL -o /tmp/SHA512-SUMS.txt \
        "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/SHA512-SUMS.txt" \
    && (cd /tmp && awk -v f="${GODOT_ASSET}" '$2==f' SHA512-SUMS.txt | sha512sum -c -) \
    && unzip -o /tmp/${GODOT_ASSET} -d /opt/godot \
    && chmod +x /opt/godot/Godot_v${GODOT_VERSION}_linux.x86_64 \
    && ln -sf /opt/godot/Godot_v${GODOT_VERSION}_linux.x86_64 /opt/godot/godot \
    && rm -f /tmp/${GODOT_ASSET} /tmp/SHA512-SUMS.txt

# Sanity: the binary runs headless and reports the expected version. xvfb-run
# wraps it so the display driver probe succeeds in the headless build env.
RUN xvfb-run -a /opt/godot/godot --headless --quit 2>&1 | grep -q . \
    && /opt/godot/godot --version | grep -q "^4.7" \
    || (echo "::error::Godot binary did not report 4.7.x" && exit 1)

# The addon's supported floor (issue #701): a second pinned editor used by the
# `godot-floor` job in ci.yml to parse/smoke the addon on 4.4. Same checksum
# discipline as the primary binary; never run an unverified download.
ARG GODOT_FLOOR_VERSION=4.4-stable
ARG GODOT_FLOOR_ASSET=Godot_v4.4-stable_linux.x86_64.zip

RUN mkdir -p /opt/godot/4.4 \
    && curl -fsSL -o /tmp/${GODOT_FLOOR_ASSET} \
        "https://github.com/godotengine/godot/releases/download/${GODOT_FLOOR_VERSION}/${GODOT_FLOOR_ASSET}" \
    && curl -fsSL -o /tmp/SHA512-SUMS-floor.txt \
        "https://github.com/godotengine/godot/releases/download/${GODOT_FLOOR_VERSION}/SHA512-SUMS.txt" \
    && (cd /tmp && awk -v f="${GODOT_FLOOR_ASSET}" '$2==f' SHA512-SUMS-floor.txt | sha512sum -c -) \
    && unzip -o /tmp/${GODOT_FLOOR_ASSET} -d /opt/godot/4.4 \
    && chmod +x /opt/godot/4.4/Godot_v${GODOT_FLOOR_VERSION}_linux.x86_64 \
    && ln -sf /opt/godot/4.4/Godot_v${GODOT_FLOOR_VERSION}_linux.x86_64 /opt/godot/4.4/godot \
    && rm -f /tmp/${GODOT_FLOOR_ASSET} /tmp/SHA512-SUMS-floor.txt

# Sanity: the floor binary reports 4.4.
RUN /opt/godot/4.4/godot --version | grep -q "^4.4" \
    || (echo "::error::Godot floor binary did not report 4.4.x" && exit 1)

# Godot 4.8 beta verification lane (#739). Betas are served from
# downloads.godotengine.org (no GitHub release / SHA512-SUMS file), so the zip's
# SHA512 is pinned here (verified against the official download for the pinned
# beta commit cafc17a1). Update the version, asset, URL and hash together.
ARG GODOT48_VERSION=4.8-beta2
ARG GODOT48_ASSET=Godot_v4.8-beta2_linux.x86_64.zip
ARG GODOT48_SHA512=77470f53a9039cd22837935380230220167e098324e82ec448ee4b1f943f00afc424885f7d6631f385123d7a630a9399b3cc1b0e1dad1a4ac45c6356b3a0aa45

RUN mkdir -p /opt/godot48 \
    && curl -fsSL -o /tmp/${GODOT48_ASSET} \
        "https://downloads.godotengine.org/?version=4.8&flavor=beta2&slug=linux.x86_64.zip" \
    && echo "${GODOT48_SHA512}  /tmp/${GODOT48_ASSET}" | sha512sum -c - \
    && unzip -o /tmp/${GODOT48_ASSET} -d /opt/godot48 \
    && chmod +x /opt/godot48/Godot_v${GODOT48_VERSION}_linux.x86_64 \
    && ln -sf /opt/godot48/Godot_v${GODOT48_VERSION}_linux.x86_64 /opt/godot48/godot \
    && rm -f /tmp/${GODOT48_ASSET}

# Sanity: the beta binary reports the pinned beta line.
RUN /opt/godot48/godot --version | grep -Eq "^4[.-]8[.-]beta2([.-]|$)" \
    || (echo "::error::Godot 4.8 beta binary did not report 4.8.beta2" && exit 1)

ENV GODOT_BIN=/opt/godot/godot

USER runner
