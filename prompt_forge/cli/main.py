"""PromptForge CLI — forge command."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from prompt_forge.cli.client import ForgeClient


pass_client = click.make_pass_decorator(ForgeClient)


def _format_table(rows: list[dict], columns: list[str]) -> str:
    """Simple table formatter."""
    if not rows:
        return "No results."
    # Compute column widths
    widths = {c: len(c) for c in columns}
    for row in rows:
        for c in columns:
            val = str(row.get(c, ""))
            widths[c] = max(widths[c], len(val))

    header = "  ".join(c.upper().ljust(widths[c]) for c in columns)
    separator = "  ".join("-" * widths[c] for c in columns)
    lines = [header, separator]
    for row in rows:
        line = "  ".join(str(row.get(c, "")).ljust(widths[c]) for c in columns)
        lines.append(line)
    return "\n".join(lines)


@click.group()
@click.option("--api", default="http://localhost:8100", envvar="FORGE_API", help="API base URL")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
@click.option("--token", default=None, envvar="FORGE_TOKEN", help="Auth token")
@click.pass_context
def cli(ctx: click.Context, api: str, output_format: str, token: str | None) -> None:
    """PromptForge CLI — manage prompts, versions, and compositions."""
    ctx.ensure_object(dict)
    ctx.obj = ForgeClient(base_url=api, auth_token=token)
    ctx.meta["output_format"] = output_format


def _output(ctx: click.Context, data: Any, columns: list[str] | None = None) -> None:
    fmt = ctx.meta.get("output_format", "table")
    if fmt == "json":
        click.echo(json.dumps(data, indent=2, default=str))
    elif isinstance(data, list) and columns:
        click.echo(_format_table(data, columns))
    else:
        click.echo(json.dumps(data, indent=2, default=str))


# --- Prompt commands ---


@cli.group()
def prompt() -> None:
    """Manage prompts."""


@prompt.command("list")
@click.option("--type", "prompt_type", default=None)
@click.option("--tag", default=None)
@click.pass_context
def prompt_list(ctx: click.Context, prompt_type: str | None, tag: str | None) -> None:
    """List all prompts."""
    client: ForgeClient = ctx.obj
    params: dict[str, Any] = {}
    if prompt_type:
        params["type"] = prompt_type
    if tag:
        params["tag"] = tag
    data = client.list_prompts(**params)
    _output(ctx, data, ["slug", "name", "type", "tags", "parent_slug"])


@prompt.command("create")
@click.option("--slug", required=True)
@click.option("--name", required=True)
@click.option("--type", "prompt_type", required=True)
@click.option("--parent", default=None)
@click.option("--tags", default="")
@click.pass_context
def prompt_create(
    ctx: click.Context, slug: str, name: str, prompt_type: str, parent: str | None, tags: str
) -> None:
    """Create a prompt."""
    client: ForgeClient = ctx.obj
    data: dict[str, Any] = {
        "slug": slug,
        "name": name,
        "type": prompt_type,
        "tags": [t.strip() for t in tags.split(",") if t.strip()] if tags else [],
    }
    if parent:
        data["parent_slug"] = parent
    result = client.create_prompt(data)
    _output(ctx, result)


@prompt.command("show")
@click.argument("slug")
@click.pass_context
def prompt_show(ctx: click.Context, slug: str) -> None:
    """Show prompt details."""
    client: ForgeClient = ctx.obj
    data = client.get_prompt(slug)
    _output(ctx, data)


@prompt.command("archive")
@click.argument("slug")
@click.pass_context
def prompt_archive(ctx: click.Context, slug: str) -> None:
    """Archive a prompt."""
    client: ForgeClient = ctx.obj
    client.archive_prompt(slug)
    click.echo(f"Archived prompt '{slug}'")


# --- Version commands ---


@cli.group()
def version() -> None:
    """Manage versions."""


@version.command("commit")
@click.argument("slug")
@click.option("--message", "-m", required=True)
@click.option("--file", "-f", "file_path", default=None)
@click.option("--author", default="cli")
@click.option("--branch", default="main")
@click.pass_context
def version_commit(
    ctx: click.Context, slug: str, message: str, file_path: str | None, author: str, branch: str
) -> None:
    """Commit a new version. Reads content from --file or stdin (JSON)."""
    client: ForgeClient = ctx.obj
    if file_path:
        with open(file_path) as f:
            content = json.load(f)
    else:
        content = json.load(sys.stdin)
    result = client.commit_version(
        slug, {"content": content, "message": message, "author": author, "branch": branch}
    )
    _output(ctx, result)


@version.command("history")
@click.argument("slug")
@click.option("--branch", default="main")
@click.pass_context
def version_history(ctx: click.Context, slug: str, branch: str) -> None:
    """Show version history."""
    client: ForgeClient = ctx.obj
    data = client.list_versions(slug, branch)
    _output(ctx, data, ["version", "message", "author", "branch", "created_at"])


@version.command("diff")
@click.argument("slug")
@click.argument("v1", type=int)
@click.argument("v2", type=int)
@click.option("--branch", default="main")
@click.pass_context
def version_diff(ctx: click.Context, slug: str, v1: int, v2: int, branch: str) -> None:
    """Structural diff between versions."""
    client: ForgeClient = ctx.obj
    data = client.diff_versions(slug, v1, v2, branch)
    _output(ctx, data)


@version.command("rollback")
@click.argument("slug")
@click.argument("version_num", type=int)
@click.option("--author", default="cli")
@click.pass_context
def version_rollback(ctx: click.Context, slug: str, version_num: int, author: str) -> None:
    """Rollback to a specific version."""
    client: ForgeClient = ctx.obj
    result = client.rollback(slug, version_num, author)
    _output(ctx, result)


# --- Compose ---


@cli.command()
@click.option("--persona", required=True)
@click.option("--skills", default="")
@click.option("--constraints", default="")
@click.option("--variables", multiple=True, help="key=value pairs")
@click.option("--branch", default="main")
@click.pass_context
def compose(
    ctx: click.Context, persona: str, skills: str, constraints: str, variables: tuple, branch: str
) -> None:
    """Compose a prompt from components."""
    client: ForgeClient = ctx.obj
    vars_dict = {}
    for v in variables:
        if "=" in v:
            k, val = v.split("=", 1)
            vars_dict[k] = val
    data = {
        "persona": persona,
        "skills": [s.strip() for s in skills.split(",") if s.strip()] if skills else [],
        "constraints": [c.strip() for c in constraints.split(",") if c.strip()]
        if constraints
        else [],
        "variables": vars_dict,
        "branch": branch,
    }
    result = client.compose(data)
    click.echo(result.get("prompt", ""))
    if result.get("warnings"):
        click.echo("\nWarnings:", err=True)
        for w in result["warnings"]:
            click.echo(f"  - {w}", err=True)


# --- Resolve ---


@cli.command()
@click.argument("slug")
@click.option("--branch", default="main")
@click.option("--version", "version_num", type=int, default=None)
@click.option("--strategy", default="latest")
@click.pass_context
def resolve(
    ctx: click.Context, slug: str, branch: str, version_num: int | None, strategy: str
) -> None:
    """Resolve a prompt to a specific version."""
    client: ForgeClient = ctx.obj
    data: dict[str, Any] = {"slug": slug, "branch": branch, "strategy": strategy}
    if version_num is not None:
        data["version"] = version_num
    result = client.resolve(data)
    _output(ctx, result)


# --- Deploy ---


@cli.command()
@click.argument("slug")
@click.option("--branch", default="main")
@click.pass_context
def deploy(ctx: click.Context, slug: str, branch: str) -> None:
    """Deploy — resolve and pretty-print the final prompt."""
    client: ForgeClient = ctx.obj
    result = client.resolve({"slug": slug, "branch": branch, "strategy": "latest"})
    content = result.get("content", {})
    click.echo("=" * 60)
    click.echo("DEPLOYED PROMPT")
    click.echo("=" * 60)
    for section in content.get("sections", []):
        click.echo(f"\n## {section.get('label', section.get('id', 'Unknown'))}")
        click.echo(section.get("content", ""))
    click.echo("\n" + "=" * 60)
    click.echo("Manifest:")
    click.echo(f"  Version: {result.get('version')}")
    click.echo(f"  Branch: {result.get('branch')}")
    click.echo(f"  Author: {result.get('author')}")


# --- Search ---


@cli.command()
@click.argument("query")
@click.pass_context
def search(ctx: click.Context, query: str) -> None:
    """Search prompts by name or tags."""
    client: ForgeClient = ctx.obj
    data = client.search(query)
    _output(ctx, data, ["slug", "name", "type", "tags"])


if __name__ == "__main__":
    cli()
