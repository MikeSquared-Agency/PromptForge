CREATE TABLE experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_slug     TEXT NOT NULL,
    control_version UUID NOT NULL,
    variant_version UUID NOT NULL,
    split_pct       INT NOT NULL DEFAULT 50 CHECK (split_pct BETWEEN 1 AND 99),
    status          TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','paused','concluded')),
    min_sessions    INT NOT NULL DEFAULT 50,
    max_duration_d  INT NOT NULL DEFAULT 14,
    conclusion      TEXT CHECK (conclusion IN ('promoted','rejected','expired')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    concluded_at    TIMESTAMPTZ
);

CREATE TABLE experiment_assignments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id   UUID NOT NULL REFERENCES experiments(id),
    agent_id        TEXT NOT NULL,
    session_id      TEXT,
    arm             TEXT NOT NULL CHECK (arm IN ('control','variant')),
    assigned_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_exp_assign_experiment ON experiment_assignments(experiment_id);
CREATE UNIQUE INDEX idx_one_active_experiment ON experiments(prompt_slug) WHERE status = 'running';
