"""Load static AI context files and skills."""

import re
from pathlib import Path

AI_DIR = Path(__file__).parent


def load_overview() -> str:
    """Load the static workspace overview."""
    return (AI_DIR / "overview.md").read_text()


def load_skills() -> list[dict]:
    """Load all skill files from the skills directory.

    Returns a list of dicts with 'name', 'description', 'content' (full file),
    and 'body' (content without frontmatter).
    """
    skills_dir = AI_DIR / "skills"
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
