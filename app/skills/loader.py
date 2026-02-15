from __future__ import annotations

import logging
import re
from pathlib import Path

from app.skills.models import SkillMetadata

logger = logging.getLogger(__name__)


def parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """Parse YAML-like frontmatter from a SKILL.md file using regex.

    Returns (frontmatter_dict, body_text).
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    fm_text = match.group(1)
    body = match.group(2).strip()

    result: dict[str, str | list[str]] = {}
    current_key: str | None = None

    for line in fm_text.split("\n"):
        # List item under current key
        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_key is not None:
            val = result.get(current_key)
            if not isinstance(val, list):
                result[current_key] = []
            result[current_key].append(list_match.group(1).strip())
            continue

        # Key-value pair
        kv_match = re.match(r"^(\w+)\s*:\s*(.*)$", line)
        if kv_match:
            current_key = kv_match.group(1)
            value = kv_match.group(2).strip()
            if value:
                result[current_key] = value
            else:
                result[current_key] = []
            continue

    return result, body


def load_skill_metadata(skill_dir: Path) -> SkillMetadata | None:
    """Load a SkillMetadata from a SKILL.md file in the given directory."""
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    text = skill_file.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    name = fm.get("name")
    if not name or not isinstance(name, str):
        logger.warning("SKILL.md in %s missing 'name' field", skill_dir)
        return None

    description = fm.get("description", "")
    if not isinstance(description, str):
        description = ""

    version_raw = fm.get("version", "1")
    try:
        version = int(version_raw) if isinstance(version_raw, str) else 1
    except ValueError:
        version = 1

    tools_raw = fm.get("tools", [])
    tools = tools_raw if isinstance(tools_raw, list) else []

    return SkillMetadata(
        name=name,
        description=description,
        version=version,
        tools=tools,
        instructions=body,
    )


def scan_skills_directory(skills_dir: str) -> list[SkillMetadata]:
    """Scan a directory for skill subdirectories containing SKILL.md files."""
    path = Path(skills_dir)
    if not path.exists():
        logger.info("Skills directory %s does not exist, skipping", skills_dir)
        return []

    skills = []
    for child in sorted(path.iterdir()):
        if child.is_dir():
            metadata = load_skill_metadata(child)
            if metadata:
                skills.append(metadata)
                logger.info("Loaded skill: %s (%d tools)", metadata.name, len(metadata.tools))

    return skills
