-- Phase 2 Migration — Analytics views and indexes

-- Materialized view for prompt usage stats (can be refreshed periodically)
CREATE MATERIALIZED VIEW IF NOT EXISTS prompt_usage_stats AS
SELECT
    p.id AS prompt_id,
    p.slug,
    p.name,
    COUNT(u.id) AS total_uses,
    COUNT(CASE WHEN u.outcome = 'success' THEN 1 END) AS successes,
    COUNT(CASE WHEN u.outcome = 'failure' THEN 1 END) AS failures,
    ROUND(
        COUNT(CASE WHEN u.outcome = 'success' THEN 1 END)::NUMERIC /
        NULLIF(COUNT(u.id), 0), 3
    ) AS success_rate,
    ROUND(AVG(u.latency_ms)::NUMERIC, 1) AS avg_latency_ms,
    MAX(u.resolved_at) AS last_used_at
FROM prompts p
LEFT JOIN prompt_usage_log u ON p.id = u.prompt_id
WHERE p.archived = FALSE
GROUP BY p.id, p.slug, p.name;

CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_stats_prompt_id ON prompt_usage_stats (prompt_id);

-- View for version-level performance
CREATE MATERIALIZED VIEW IF NOT EXISTS version_performance AS
SELECT
    pv.prompt_id,
    pv.id AS version_id,
    pv.version,
    pv.branch,
    COUNT(u.id) AS total_uses,
    COUNT(CASE WHEN u.outcome = 'success' THEN 1 END) AS successes,
    ROUND(
        COUNT(CASE WHEN u.outcome = 'success' THEN 1 END)::NUMERIC /
        NULLIF(COUNT(u.id), 0), 3
    ) AS success_rate,
    ROUND(AVG(u.latency_ms)::NUMERIC, 1) AS avg_latency_ms
FROM prompt_versions pv
LEFT JOIN prompt_usage_log u ON pv.id = u.version_id
GROUP BY pv.prompt_id, pv.id, pv.version, pv.branch;

CREATE UNIQUE INDEX IF NOT EXISTS idx_version_perf_id ON version_performance (version_id);

-- Additional indexes for analytics queries
CREATE INDEX IF NOT EXISTS idx_usage_prompt_version ON prompt_usage_log (prompt_id, version_id);
CREATE INDEX IF NOT EXISTS idx_usage_outcome_resolved ON prompt_usage_log (outcome, resolved_at DESC);
