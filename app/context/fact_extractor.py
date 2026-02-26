"""Deterministic extraction of user facts from memory strings.

No LLM calls — fast regex-based extraction of known fact types.
Used by ConversationContext.build() to create user_facts for tool loop injection.
"""

from __future__ import annotations

import re

# Each entry: (fact_key, compiled_pattern)
# The pattern must have exactly one capture group for the fact value.
_FACT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # GitHub username — broad pattern to handle many Spanish and English variations:
    # "usuario de GitHub es sebadp", "GitHub username: sebadp",
    # "usuario en GitHub del usuario es sebadp", "mi cuenta de GitHub es sebadp"
    # "GitHub: sebadp", "github user sebadp"
    (
        "github_username",
        re.compile(
            r"github[^\n,;.]{0,30}?(?:es|is|:)\s+([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})"
            r"(?!\S)",  # not followed by non-space (i.e. end of word)
            re.IGNORECASE,
        ),
    ),
    # GitHub token / PAT — extract presence, not the value
    (
        "github_token_configured",
        re.compile(
            r"(?:github\s+(?:token|pat|personal\s+access))\s+(?:configurad[oa]|is set|registrad[oa]|activ[oa])",
            re.IGNORECASE,
        ),
    ),
    # Name — "se llama Sebastián", "mi nombre es Juan", "me llamo Pedro", "my name is John"
    (
        "name",
        re.compile(
            r"(?:se\s+llama|(?:mi\s+)?nombre\s+es|me\s+llamo|my\s+name\s+is)\s+"
            r"([A-ZÀ-Üa-zà-ü][a-zà-ü]+(?:\s+[A-ZÀ-Üa-zà-ü][a-zà-ü]+)?)",
            re.IGNORECASE,
        ),
    ),
    # Preferred language
    (
        "language",
        re.compile(
            r"(?:prefiere\s+(?:el\s+)?|habla\s+|idioma\s+(?:preferido\s+)?es\s+)"
            r"(español|inglés|ingles|english|spanish|português|portuguese)",
            re.IGNORECASE,
        ),
    ),
]

# If any of these marker strings appear, the fact value is a boolean True sentinel
_BOOLEAN_FACTS: set[str] = {"github_token_configured"}


def extract_facts(memories: list[str]) -> dict[str, str]:
    """Extract key-value facts from a list of memory strings.

    Returns a dict of fact_key -> fact_value. Only captures the first
    occurrence of each fact type found across all memories.

    Example:
        memories = [
            "El usuario de GitHub del usuario es sebadp",
            "Se llama Sebastián",
        ]
        extract_facts(memories)
        # -> {"github_username": "sebadp", "name": "Sebastián"}
    """
    facts: dict[str, str] = {}

    for mem in memories:
        for fact_key, pattern in _FACT_PATTERNS:
            if fact_key in facts:
                continue  # Already captured, skip

            match = pattern.search(mem)
            if match:
                if fact_key in _BOOLEAN_FACTS:
                    facts[fact_key] = "true"
                else:
                    facts[fact_key] = match.group(1).strip()

    return facts


def format_facts_for_prompt(facts: dict[str, str]) -> str | None:
    """Format extracted facts as a compact system message for the tool loop.

    Returns None if facts is empty.
    """
    if not facts:
        return None

    labels = {
        "github_username": "GitHub username",
        "github_token_configured": "GitHub token",
        "name": "Name",
        "language": "Preferred language",
    }

    lines = ["Known user facts (use these directly, do not ask the user again):"]
    for key, value in facts.items():
        label = labels.get(key, key)
        if key == "github_token_configured":
            lines.append(f"- {label}: configured")
        else:
            lines.append(f"- {label}: {value}")

    return "\n".join(lines)
