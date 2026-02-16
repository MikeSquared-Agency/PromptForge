CREATE TABLE prompt_effectiveness (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_id            UUID REFERENCES prompts(id),
    version_id           UUID REFERENCES prompt_versions(id),
    session_uuid         TEXT NOT NULL,
    mission_id           TEXT,
    task_id              TEXT,
    agent_id             TEXT NOT NULL,
    model_id             TEXT NOT NULL,
    model_tier           TEXT,
    briefing_hash        TEXT,
    input_tokens         BIGINT,
    output_tokens        BIGINT,
    total_tokens         BIGINT,
    cost_usd             NUMERIC(10,6),
    correction_count     INT DEFAULT 0,
    human_interventions  INT DEFAULT 0,
    outcome              TEXT DEFAULT 'unknown',
    outcome_score        FLOAT,
    effectiveness        FLOAT GENERATED ALWAYS AS (
        CASE WHEN cost_usd > 0 AND outcome_score IS NOT NULL
             THEN outcome_score / cost_usd ELSE NULL END
    ) STORED,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    completed_at         TIMESTAMPTZ
);

CREATE INDEX idx_effectiveness_session ON prompt_effectiveness(session_uuid);
CREATE INDEX idx_effectiveness_prompt ON prompt_effectiveness(prompt_id);
CREATE INDEX idx_effectiveness_version ON prompt_effectiveness(version_id);
CREATE INDEX idx_effectiveness_model ON prompt_effectiveness(model_id);
CREATE INDEX idx_effectiveness_model_tier ON prompt_effectiveness(model_tier);
CREATE INDEX idx_effectiveness_mission ON prompt_effectiveness(mission_id);
CREATE INDEX idx_effectiveness_created ON prompt_effectiveness(created_at DESC);
