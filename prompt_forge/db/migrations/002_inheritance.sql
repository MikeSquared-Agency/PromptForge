-- Prompt Inheritance Migration
-- Adds parent_slug to prompts and override_sections to prompt_versions

ALTER TABLE prompts ADD COLUMN parent_slug TEXT REFERENCES prompts(slug);
CREATE INDEX idx_prompts_parent_slug ON prompts(parent_slug);

ALTER TABLE prompt_versions ADD COLUMN override_sections JSONB DEFAULT '{}';
