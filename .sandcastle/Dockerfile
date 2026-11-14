FROM node:22-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
  git \
  curl \
  jq \
  poppler-utils \
  && rm -rf /var/lib/apt/lists/*

# PostgreSQL 17 (same major version as supabase/config.toml) from the
# official PGDG repo: a private database per sandbox. See db/sandbox-db.
RUN install -d /usr/share/postgresql-common/pgdg \
  && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
     https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
     > /etc/apt/sources.list.d/pgdg.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends postgresql-17 \
  && rm -rf /var/lib/apt/lists/*
ENV PATH="/usr/lib/postgresql/17/bin:$PATH"

COPY db/sandbox-db /usr/local/bin/sandbox-db
COPY db/supabase-shim.sql /opt/sandbox-db/supabase-shim.sql
RUN sed -i 's/\r$//' /usr/local/bin/sandbox-db /opt/sandbox-db/supabase-shim.sql \
  && chmod 755 /usr/local/bin/sandbox-db && chmod 644 /opt/sandbox-db/supabase-shim.sql

# Backend settings for tests against the sandbox database. The repo's .env is
# gitignored, so it isn't in the worktree. SUPABASE_URL points nowhere: the
# Auth and Storage APIs don't run here. OWNER_DATABASE_URL is the owner
# connection; once the app_backend role exists (ticket 01), point
# DATABASE_URL at it.
ENV DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/postgres" \
    OWNER_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/postgres" \
    SUPABASE_URL="http://127.0.0.1:54321" \
    SUPABASE_SERVICE_ROLE_KEY="sandbox-service-role-key" \
    SUPABASE_JWT_SECRET="sandbox-jwt-secret-at-least-32-characters-long" \
    MAIL_FROM="alerts@maritime.local" \
    ENABLE_DAILY_SCAN="0"

# No issue tracker CLI: issues are local markdown, listed and closed on the host.

# Build-args for UID/GID alignment: sandcastle docker build-image
# defaults these to the host user's UID/GID so image-built files
# and bind-mounted files share an owner without runtime chown.
ARG AGENT_UID=1000
ARG AGENT_GID=1000

# Rename the base image's "node" user to "agent" and align UID/GID.
RUN groupmod -o -g $AGENT_GID node && usermod -o -u $AGENT_UID -g $AGENT_GID -d /home/agent -m -l agent node
USER ${AGENT_UID}:${AGENT_GID}

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash

# Add Claude (and uv, below) to PATH
ENV PATH="/home/agent/.local/bin:$PATH"

# Python backend: uv plus the Python version pyproject.toml requires
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
  && uv python install 3.13

WORKDIR /home/agent

# In worktree sandbox mode, Sandcastle bind-mounts the git worktree at /home/agent/workspace
# and overrides the working directory to /home/agent/workspace at container start.
# Structure your Dockerfile so that /home/agent/workspace can serve as the project root.
ENTRYPOINT ["sleep", "infinity"]
