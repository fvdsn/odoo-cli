"""Static content templates for AI context files."""

import re
from importlib.resources import files as pkg_files
from pathlib import Path


def workspace_overview(config: dict) -> str:
    """Generate the main workspace overview content."""
    version = config.get("version", "master")
    repos = []
    repos.append("- `odoo/` — Odoo Community (main codebase)")
    if config["repositories"]["enterprise"]:
        repos.append("- `enterprise/` — Odoo Enterprise")
    if config["repositories"]["documentation"]:
        repos.append("- `documentation/` — Odoo Documentation")
    if config["repositories"]["themes"]:
        repos.append("- `themes/` — Odoo Themes (design-themes)")
    for url in config["repositories"].get("extra_addons", []):
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        repos.append(f"- `addons/{name}/` — Extra addon")
    repos_str = "\n".join(repos)

    pg = config["postgres"]
    db_name = pg["db_name"]

    odoo_config = config.get("odoo", {})
    http_port = odoo_config.get("http_port", 8069)
    modules = ", ".join(odoo_config.get("install_modules", []))

    return f"""\
# Odoo Development Workspace

Version: {version}

## Repositories

{repos_str}

## Database

- Database: `{db_name}`
- Server: http://localhost:{http_port}
- Credentials: admin / admin

## CLI Tool

This workspace is managed by `odoo-cli`. All commands should be run from the workspace root.

### Quick Reference

| Command | Description |
|---|---|
| `odoo-cli start` | Start the Odoo server |
| `odoo-cli update [modules]` | Update modules (default: all) |
| `odoo-cli db-reset` | Drop and recreate the database |
| `odoo-cli test [modules]` | Run tests on a dedicated test database |
| `odoo-cli sql "SELECT ..."` | Execute a SQL query |
| `odoo-cli psql` | Open an interactive PostgreSQL shell |
| `odoo-cli shell` | Python REPL with Odoo environment |
| `odoo-cli run "code"` | Execute Python in Odoo environment |
| `odoo-cli checkout [version]` | Switch all repos to a version |
| `odoo-cli pull` | Pull latest changes across all repos |
| `odoo-cli venv` | Recreate the Python virtual environment |

### Installed Modules

{modules}

## Python Environment

The virtual environment is at `odoo/.venv/`. When running Python directly:
```bash
odoo/.venv/bin/python odoo/odoo-bin [options]
```

## Git Workflow

Feature branches should be pushed to the dev remote (`odoo-dev`), not `origin`.
"""


def load_skills() -> list[dict]:
    """Load all skill files from the skills directory.

    Returns a list of dicts with 'name', 'description', 'content' (full file),
    and 'body' (content without frontmatter).
    """
    skills_dir = Path(__file__).parent / "skills"
    skills = []
    for path in sorted(skills_dir.glob("*.md")):
        content = path.read_text()
        name = path.stem
        description = ""
        body = content

        # Parse YAML frontmatter
        m = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
        if m:
            frontmatter, body = m.group(1), m.group(2).lstrip("\n")
            for line in frontmatter.splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()

        skills.append({
            "name": name,
            "description": description,
            "content": content,
            "body": body,
        })
    return skills
