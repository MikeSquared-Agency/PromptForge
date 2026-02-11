# Warren Integration Guide

## How Warren Uses PromptForge

### Agent Boot Sequence

When the King spawns a new worker:

1. King determines required agent type (e.g., "code-reviewer with Python + security skills")
2. King calls `POST /api/v1/compose`:
   ```json
   {
     "persona": "code-reviewer",
     "skills": ["python-expert", "security-audit"],
     "constraints": ["concise-output"],
     "variables": {"project_name": "PromptForge"}
   }
   ```
3. PromptForge resolves each component, composes the final prompt, returns it with a manifest
4. King spawns the worker with the composed system prompt
5. Worker stores the composition manifest for later logging

### Usage Telemetry

When a worker completes a task:

```json
POST /api/v1/usage
{
  "prompt_id": "...",
  "version_id": "...",
  "agent_id": "worker-code-review-42",
  "composition_manifest": { ... },
  "outcome": "success",
  "latency_ms": 3400
}
```

### PromptArchitect Integration

The PromptArchitect agent has direct tool access to PromptForge core functions. It runs as an OpenClaw agent and can:

- Design new prompts when the King identifies a gap
- Refine prompts when usage metrics show degradation
- Compose and validate new agent configurations

### Environment Variables

Warren agents need:
```
PROMPTFORGE_URL=http://prompt-forge:8400
```

### Docker Swarm Network

Both Warren and PromptForge should be on the same overlay network:
```yaml
networks:
  warren-net:
    driver: overlay
```
