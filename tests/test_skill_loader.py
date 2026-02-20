
from app.skills.loader import load_skill_metadata, parse_frontmatter, scan_skills_directory


def test_parse_frontmatter_basic():
    text = """---
name: weather
description: Check the weather
version: 1
tools:
  - get_weather
---
Use the get_weather tool."""
    fm, body = parse_frontmatter(text)
    assert fm["name"] == "weather"
    assert fm["description"] == "Check the weather"
    assert fm["version"] == "1"
    assert fm["tools"] == ["get_weather"]
    assert body == "Use the get_weather tool."


def test_parse_frontmatter_multiple_tools():
    text = """---
name: datetime
description: Date and time tools
tools:
  - get_current_datetime
  - convert_timezone
---
Instructions here."""
    fm, body = parse_frontmatter(text)
    assert fm["tools"] == ["get_current_datetime", "convert_timezone"]
    assert body == "Instructions here."


def test_parse_frontmatter_no_frontmatter():
    text = "Just some text without frontmatter."
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == text


def test_parse_frontmatter_empty_body():
    text = """---
name: test
description: A test skill
tools:
  - do_thing
---
"""
    fm, body = parse_frontmatter(text)
    assert fm["name"] == "test"
    assert body == ""


def test_load_skill_metadata(tmp_path):
    skill_dir = tmp_path / "weather"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: weather
description: Check the weather
version: 1
tools:
  - get_weather
---
Use get_weather with the city name.""")

    meta = load_skill_metadata(skill_dir)
    assert meta is not None
    assert meta.name == "weather"
    assert meta.description == "Check the weather"
    assert meta.version == 1
    assert meta.tools == ["get_weather"]
    assert "get_weather" in meta.instructions


def test_load_skill_metadata_missing_file(tmp_path):
    skill_dir = tmp_path / "empty"
    skill_dir.mkdir()
    assert load_skill_metadata(skill_dir) is None


def test_load_skill_metadata_missing_name(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
description: No name field
---
Body.""")
    assert load_skill_metadata(skill_dir) is None


def test_scan_skills_directory(tmp_path):
    for name in ["alpha", "beta"]:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"""---
name: {name}
description: Skill {name}
tools:
  - tool_{name}
---
Instructions for {name}.""")

    skills = scan_skills_directory(str(tmp_path))
    assert len(skills) == 2
    assert skills[0].name == "alpha"
    assert skills[1].name == "beta"


def test_scan_nonexistent_directory():
    skills = scan_skills_directory("/nonexistent/path")
    assert skills == []
