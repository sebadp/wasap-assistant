import logging
from pathlib import Path

from app.skills.models import ToolDefinition

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


async def create_feature_docs(
    feature_id: str, feature_title: str, walkthrough_content: str, testing_content: str
) -> str:
    """Implement rule #1 and #2 of the 5-step documentation protocol: Walkthrough and Testing generation."""
    feature_path = _PROJECT_ROOT / "docs" / "features" / f"{feature_id}.md"
    testing_path = _PROJECT_ROOT / "docs" / "testing" / f"{feature_id}_testing.md"

    try:
        feature_path.write_text(walkthrough_content, encoding="utf-8")
        testing_path.write_text(testing_content, encoding="utf-8")
    except Exception as e:
        return f"Error writing doc files: {e}"

    # Update indices (Rule #3)
    feature_idx = _PROJECT_ROOT / "docs" / "features" / "README.md"
    testing_idx = _PROJECT_ROOT / "docs" / "testing" / "README.md"

    def _append_to_table(filepath: Path, new_row: str) -> bool:
        if not filepath.exists():
            return False
        content = filepath.read_text(encoding="utf-8")
        # Find the end of the markdown table
        lines = content.splitlines()
        insert_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("|") and (
                i + 1 == len(lines) or not lines[i + 1].strip().startswith("|")
            ):
                insert_idx = i + 1

        if insert_idx != -1:
            lines.insert(insert_idx, new_row)
            filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
        return False

    success_feat = _append_to_table(
        feature_idx, f"| {feature_title} | [`{feature_id}.md`]({feature_id}.md) | Agent-auto |"
    )
    success_test = _append_to_table(
        testing_idx, f"| {feature_title} | [`{feature_id}_testing.md`]({feature_id}_testing.md) |"
    )

    return (
        f"Documentation generated successfully.\n"
        f"Feature Walkthrough: {feature_path.relative_to(_PROJECT_ROOT)}\n"
        f"Testing Guide: {testing_path.relative_to(_PROJECT_ROOT)}\n"
        f"Features Index Updated: {success_feat}\n"
        f"Testing Index Updated: {success_test}"
    )


async def update_architecture_rules(rule_description: str) -> str:
    """Implement rule #4 of the 5-step documentation protocol: update CLAUDE.md."""
    claude_path = _PROJECT_ROOT / "CLAUDE.md"
    if not claude_path.exists():
        return "Error: CLAUDE.md not found at project root."

    try:
        content = claude_path.read_text(encoding="utf-8")

        # Append to Patrones
        if "## Patrones" in content:
            # We append right at the end of the document, which is within Patrones
            content = content.rstrip() + f"\n- {rule_description}\n"
            claude_path.write_text(content, encoding="utf-8")
            return "Rule appended successfully to the 'Patrones' section of CLAUDE.md."
        else:
            return "Error: '## Patrones' section not found in CLAUDE.md."
    except Exception as e:
        return f"Error updating CLAUDE.md: {e}"


async def update_agent_docs(agent_capability_description: str) -> str:
    """Implement rule #5 of the 5-step documentation protocol: update AGENTS.md."""
    agents_path = _PROJECT_ROOT / "AGENTS.md"
    if not agents_path.exists():
        return "Error: AGENTS.md not found at project root."

    try:
        content = agents_path.read_text(encoding="utf-8")
        # We append to the bottom of the document
        content = content.rstrip() + f"\n- {agent_capability_description}\n"
        agents_path.write_text(content, encoding="utf-8")
        return "Capability appended successfully to AGENTS.md."
    except Exception as e:
        return f"Error updating AGENTS.md: {e}"


def register(registry) -> None:
    """Register documentation management tools with the skill registry."""
    registry.register_tool(
        name="create_feature_docs",
        description=(
            "Creates the mandatory feature walkthrough and manual testing guide "
            "using standard templates, and appends them to their respective indices."
        ),
        parameters={
            "type": "object",
            "properties": {
                "feature_id": {
                    "type": "string",
                    "description": "Chronological ID and name (e.g. '24-observability').",
                },
                "feature_title": {
                    "type": "string",
                    "description": "Human-readable title (e.g. 'Observability & Tracing').",
                },
                "walkthrough_content": {
                    "type": "string",
                    "description": "The markdown content detailing What, How, Decisions, and Gotchas.",
                },
                "testing_content": {
                    "type": "string",
                    "description": "The markdown content detailing the manual test cases and verification steps.",
                },
            },
            "required": [
                "feature_id",
                "feature_title",
                "walkthrough_content",
                "testing_content",
            ],
        },
        handler=create_feature_docs,
        skill_name="docs",
    )

    registry.register_tool(
        name="update_architecture_rules",
        description=(
            "Appends a new architectural rule, pattern, or constraint to CLAUDE.md "
            "so future agents respect the design decision."
        ),
        parameters={
            "type": "object",
            "properties": {
                "rule_description": {
                    "type": "string",
                    "description": "A concise (1-3 sentences) markdown bullet point explaining the pattern and the files involved.",
                }
            },
            "required": ["rule_description"],
        },
        handler=update_architecture_rules,
        skill_name="docs",
    )

    registry.register_tool(
        name="update_agent_docs",
        description=(
            "Appends information about a newly added Skill, Command, or MCP Server "
            "into AGENTS.md so future agents know of its existence."
        ),
        parameters={
            "type": "object",
            "properties": {
                "agent_capability_description": {
                    "type": "string",
                    "description": "A bullet point detailing the new capability (Name, Description, Path).",
                }
            },
            "required": ["agent_capability_description"],
        },
        handler=update_agent_docs,
        skill_name="docs",
    )
