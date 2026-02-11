# Architecture

## Overview

PromptForge is a stateless FastAPI service backed by Supabase (PostgreSQL). It provides prompt lifecycle management through four core subsystems:

1. **Registry** — CRUD storage for prompt components
2. **Version Control** — Git-like versioning with structural diffs
3. **Composition Engine** — Assembles agent identities from components
4. **Smart Resolver** — Selects the right version based on strategy

## Request Flow

```
Client → FastAPI Router → API Endpoint → Core Module → Supabase Client → PostgreSQL
```

## Layered Architecture

```
┌─────────────────────────────┐
│         API Layer           │  FastAPI endpoints, Pydantic models
├─────────────────────────────┤
│        Core Layer           │  Registry, VCS, Composer, Resolver, Differ
├─────────────────────────────┤
│         DB Layer            │  Supabase client, helper methods
├─────────────────────────────┤
│       PostgreSQL            │  Supabase-managed, RLS-enabled
└─────────────────────────────┘
```

## Key Design Decisions

- **Structured content (JSONB)**: Prompts are stored as structured JSON with sections, enabling section-level diffing and intelligent composition
- **Slug-based addressing**: Human-readable slugs are the primary interface; UUIDs are internal
- **Composition over inheritance**: Agent identities are composed from independent components rather than inheriting from base templates
- **Provenance manifests**: Every composed prompt includes a manifest recording exact component versions used
- **Stateless API**: No server-side sessions; all state lives in Supabase

## Deployment

Single Docker container using supervisord to run:
- **uvicorn** serving FastAPI on port 8400
- **OpenClaw gateway** (optional) for PromptArchitect agent

Secrets via Docker Swarm `/run/secrets/` pattern, with env var fallback for development.
