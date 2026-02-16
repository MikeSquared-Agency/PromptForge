CREATE TABLE persona_prompts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    persona TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    template TEXT NOT NULL,
    is_latest BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(persona, version)
);

CREATE INDEX idx_persona_prompts_latest ON persona_prompts(persona, is_latest) WHERE is_latest = TRUE;