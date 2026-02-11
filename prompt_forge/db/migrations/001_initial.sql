-- PromptForge Initial Migration
-- Creates all tables for Phase 1

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- PROMPTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS prompts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('persona', 'skill', 'constraint', 'template', 'meta')),
    description     TEXT DEFAULT '',
    tags            TEXT[] DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    archived        BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_prompts_slug ON prompts (slug);
CREATE INDEX idx_prompts_type ON prompts (type);
CREATE INDEX idx_prompts_tags ON prompts USING GIN (tags);
CREATE INDEX idx_prompts_archived ON prompts (archived);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prompts_updated_at
    BEFORE UPDATE ON prompts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- PROMPT VERSIONS
-- =============================================================================
CREATE TABLE IF NOT EXISTS prompt_versions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_id           UUID NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version             INTEGER NOT NULL,
    content             JSONB NOT NULL,
    message             TEXT DEFAULT 'Update',
    author              TEXT DEFAULT 'system',
    parent_version_id   UUID REFERENCES prompt_versions(id),
    branch              TEXT DEFAULT 'main',
    created_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (prompt_id, version, branch)
);

CREATE INDEX idx_versions_prompt_id ON prompt_versions (prompt_id);
CREATE INDEX idx_versions_branch ON prompt_versions (branch);
CREATE INDEX idx_versions_prompt_branch ON prompt_versions (prompt_id, branch, version DESC);

-- =============================================================================
-- PROMPT BRANCHES
-- =============================================================================
CREATE TABLE IF NOT EXISTS prompt_branches (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_id           UUID NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    head_version_id     UUID REFERENCES prompt_versions(id),
    base_version_id     UUID REFERENCES prompt_versions(id),
    status              TEXT DEFAULT 'active' CHECK (status IN ('active', 'merged', 'abandoned')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (prompt_id, name)
);

CREATE INDEX idx_branches_prompt_id ON prompt_branches (prompt_id);

CREATE TRIGGER branches_updated_at
    BEFORE UPDATE ON prompt_branches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- PROMPT USAGE LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS prompt_usage_log (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_id               UUID NOT NULL REFERENCES prompts(id),
    version_id              UUID NOT NULL REFERENCES prompt_versions(id),
    agent_id                TEXT NOT NULL,
    composition_manifest    JSONB,
    resolved_at             TIMESTAMPTZ DEFAULT NOW(),
    outcome                 TEXT DEFAULT 'unknown' CHECK (outcome IN ('success', 'failure', 'partial', 'unknown')),
    latency_ms              INTEGER,
    feedback                JSONB
);

CREATE INDEX idx_usage_prompt_id ON prompt_usage_log (prompt_id);
CREATE INDEX idx_usage_version_id ON prompt_usage_log (version_id);
CREATE INDEX idx_usage_agent_id ON prompt_usage_log (agent_id);
CREATE INDEX idx_usage_outcome ON prompt_usage_log (outcome);
CREATE INDEX idx_usage_resolved_at ON prompt_usage_log (resolved_at DESC);

-- =============================================================================
-- ROW LEVEL SECURITY
-- =============================================================================
ALTER TABLE prompts ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_branches ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_usage_log ENABLE ROW LEVEL SECURITY;

-- Service role has full access (used by PromptForge API)
CREATE POLICY "Service role full access on prompts"
    ON prompts FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on versions"
    ON prompt_versions FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on branches"
    ON prompt_branches FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on usage_log"
    ON prompt_usage_log FOR ALL
    USING (auth.role() = 'service_role');

-- Anon/authenticated can read non-archived prompts (Phase 2: tighten)
CREATE POLICY "Public read on prompts"
    ON prompts FOR SELECT
    USING (archived = FALSE);

CREATE POLICY "Public read on versions"
    ON prompt_versions FOR SELECT
    USING (TRUE);
