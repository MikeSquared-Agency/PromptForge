# API Reference

Base URL: `http://localhost:8400/api/v1`

Interactive docs: `http://localhost:8400/docs`

## Prompts

### Create Prompt
`POST /prompts`
```json
{"slug": "code-reviewer", "name": "Code Reviewer", "type": "persona", "content": {...}}
```

### List Prompts
`GET /prompts?type=persona&tag=python&search=review`

### Get Prompt
`GET /prompts/{slug}`

### Update Prompt
`PUT /prompts/{slug}`
```json
{"name": "Senior Code Reviewer", "tags": ["python", "review"]}
```

### Archive Prompt
`DELETE /prompts/{slug}`

## Versions

### Commit Version
`POST /prompts/{slug}/versions`
```json
{"content": {...}, "message": "Improve constraints", "author": "architect", "branch": "main"}
```

### List History
`GET /prompts/{slug}/versions?branch=main&limit=50`

### Get Version
`GET /prompts/{slug}/versions/{version}?branch=main`

### Diff Versions
`GET /prompts/{slug}/diff?from=1&to=2&branch=main`

### Rollback
`POST /prompts/{slug}/rollback`
```json
{"version": 3, "author": "architect"}
```

## Composition

### Compose Agent Prompt
`POST /compose`
```json
{"persona": "code-reviewer", "skills": ["python-expert"], "constraints": ["concise-output"], "variables": {"project_name": "MyApp"}}
```

### Resolve Component
`POST /resolve`
```json
{"slug": "code-reviewer", "branch": "main", "strategy": "latest"}
```

## Usage

### Log Usage
`POST /usage`
```json
{"prompt_id": "uuid", "version_id": "uuid", "agent_id": "worker-1", "outcome": "success", "latency_ms": 1200}
```

### Usage Stats
`GET /usage/stats/{slug}`
