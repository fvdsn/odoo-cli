"""Harness-specific file generators for AI context setup."""

from pathlib import Path

from odoo_cli.ai.templates import SKILL_ODOO_CLI, workspace_overview

HARNESSES = {
    "claude": "Claude Code",
    "copilot": "GitHub Copilot",
    "codex": "OpenAI Codex",
    "opencode": "OpenCode",
    "pi": "Pi",
}


def setup_claude(directory: Path, config: dict) -> list[str]:
    """Generate Claude Code context files."""
    files = []

    # CLAUDE.md at workspace root
    path = directory / "CLAUDE.md"
    path.write_text(workspace_overview(config))
    files.append("CLAUDE.md")

    # Skills as custom commands
    commands_dir = directory / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    skill_path = commands_dir / "odoo-cli.md"
    skill_path.write_text(f"""\
---
description: Manage Odoo development environment (server, modules, database, tests)
---

{SKILL_ODOO_CLI}
""")
    files.append(".claude/commands/odoo-cli.md")

    return files


def setup_copilot(directory: Path, config: dict) -> list[str]:
    """Generate GitHub Copilot context files."""
    files = []

    # Main instructions
    github_dir = directory / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)

    path = github_dir / "copilot-instructions.md"
    path.write_text(workspace_overview(config))
    files.append(".github/copilot-instructions.md")

    # Skill as instruction file
    instructions_dir = github_dir / "instructions"
    instructions_dir.mkdir(parents=True, exist_ok=True)

    skill_path = instructions_dir / "odoo-cli.instructions.md"
    skill_path.write_text(f"""\
---
description: Manage Odoo development environment (server, modules, database, tests)
globs: "**"
---

{SKILL_ODOO_CLI}
""")
    files.append(".github/instructions/odoo-cli.instructions.md")

    return files


def setup_codex(directory: Path, config: dict) -> list[str]:
    """Generate OpenAI Codex context files."""
    files = []

    path = directory / "AGENTS.md"
    content = workspace_overview(config)
    content += "\n---\n\n## Skill: odoo-cli\n\n" + SKILL_ODOO_CLI
    path.write_text(content)
    files.append("AGENTS.md")

    return files


def setup_opencode(directory: Path, config: dict) -> list[str]:
    """Generate OpenCode context files."""
    files = []

    # AGENTS.md (shared with codex if present, otherwise create)
    agents_path = directory / "AGENTS.md"
    if not agents_path.exists():
        content = workspace_overview(config)
        content += "\n---\n\n## Skill: odoo-cli\n\n" + SKILL_ODOO_CLI
        agents_path.write_text(content)
        files.append("AGENTS.md")

    # Skills in .agents/ (shared with Pi)
    skills_dir = directory / ".agents" / "skills" / "odoo-cli"
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skills_dir / "SKILL.md"
    skill_path.write_text(f"""\
---
name: odoo-cli
description: Manage Odoo development environment (server, modules, database, tests)
---

{SKILL_ODOO_CLI}
""")
    files.append(".agents/skills/odoo-cli/SKILL.md")

    return files


def setup_pi(directory: Path, config: dict) -> list[str]:
    """Generate Pi context files."""
    files = []

    # AGENTS.md (shared with codex/opencode if present, otherwise create)
    agents_path = directory / "AGENTS.md"
    if not agents_path.exists():
        content = workspace_overview(config)
        content += "\n---\n\n## Skill: odoo-cli\n\n" + SKILL_ODOO_CLI
        agents_path.write_text(content)
        files.append("AGENTS.md")

    # Skills in .agents/ (shared with OpenCode)
    skills_dir = directory / ".agents" / "skills" / "odoo-cli"
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skills_dir / "SKILL.md"
    if not skill_path.exists():
        skill_path.write_text(f"""\
---
name: odoo-cli
description: Manage Odoo development environment (server, modules, database, tests)
---

{SKILL_ODOO_CLI}
""")
        files.append(".agents/skills/odoo-cli/SKILL.md")

    return files


SETUP_FUNCTIONS = {
    "claude": setup_claude,
    "copilot": setup_copilot,
    "codex": setup_codex,
    "opencode": setup_opencode,
    "pi": setup_pi,
}
