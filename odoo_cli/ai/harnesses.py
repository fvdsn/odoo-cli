"""Harness-specific file generators for AI context setup."""

from pathlib import Path

from odoo_cli.ai.templates import load_overview, load_skills

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

    path = directory / "CLAUDE.md"
    path.write_text(load_overview())
    files.append("CLAUDE.md")

    commands_dir = directory / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    for skill in load_skills():
        # Claude commands use description in frontmatter, body as content
        skill_path = commands_dir / f"{skill['name']}.md"
        skill_path.write_text(
            f"---\ndescription: {skill['description']}\n---\n\n{skill['body']}"
        )
        files.append(f".claude/commands/{skill['name']}.md")

    return files


def setup_copilot(directory: Path, config: dict) -> list[str]:
    """Generate GitHub Copilot context files."""
    files = []

    github_dir = directory / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)

    path = github_dir / "copilot-instructions.md"
    path.write_text(load_overview())
    files.append(".github/copilot-instructions.md")

    instructions_dir = github_dir / "instructions"
    instructions_dir.mkdir(parents=True, exist_ok=True)

    for skill in load_skills():
        skill_path = instructions_dir / f"{skill['name']}.instructions.md"
        skill_path.write_text(
            f"---\ndescription: {skill['description']}\nglobs: \"**\"\n---\n\n{skill['body']}"
        )
        files.append(f".github/instructions/{skill['name']}.instructions.md")

    return files


def setup_codex(directory: Path, config: dict) -> list[str]:
    """Generate OpenAI Codex context files."""
    files = []

    content = load_overview()
    for skill in load_skills():
        content += f"\n---\n\n## Skill: {skill['name']}\n\n{skill['body']}"

    path = directory / "AGENTS.md"
    path.write_text(content)
    files.append("AGENTS.md")

    return files


def setup_opencode(directory: Path, config: dict) -> list[str]:
    """Generate OpenCode context files."""
    files = []

    agents_path = directory / "AGENTS.md"
    if not agents_path.exists():
        content = load_overview()
        for skill in load_skills():
            content += f"\n---\n\n## Skill: {skill['name']}\n\n{skill['body']}"
        agents_path.write_text(content)
        files.append("AGENTS.md")

    skills_dir = directory / ".agents" / "skills"
    for skill in load_skills():
        skill_dir = skills_dir / skill["name"]
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill["content"])
        files.append(f".agents/skills/{skill['name']}/SKILL.md")

    return files


def setup_pi(directory: Path, config: dict) -> list[str]:
    """Generate Pi context files."""
    files = []

    agents_path = directory / "AGENTS.md"
    if not agents_path.exists():
        content = load_overview()
        for skill in load_skills():
            content += f"\n---\n\n## Skill: {skill['name']}\n\n{skill['body']}"
        agents_path.write_text(content)
        files.append("AGENTS.md")

    # .agents/skills/ shared with OpenCode
    skills_dir = directory / ".agents" / "skills"
    for skill in load_skills():
        skill_dir = skills_dir / skill["name"]
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            skill_path.write_text(skill["content"])
            files.append(f".agents/skills/{skill['name']}/SKILL.md")

    return files


SETUP_FUNCTIONS = {
    "claude": setup_claude,
    "copilot": setup_copilot,
    "codex": setup_codex,
    "opencode": setup_opencode,
    "pi": setup_pi,
}
