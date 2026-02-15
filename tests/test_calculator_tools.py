import math

import pytest

from app.skills.tools.calculator_tools import safe_eval


def test_basic_addition():
    assert safe_eval("2 + 3") == 5.0


def test_basic_multiplication():
    assert safe_eval("4 * 5") == 20.0


def test_order_of_operations():
    assert safe_eval("2 + 3 * 4") == 14.0


def test_parentheses():
    assert safe_eval("(2 + 3) * 4") == 20.0


def test_power():
    assert safe_eval("2 ** 10") == 1024.0


def test_modulo():
    assert safe_eval("10 % 3") == 1.0


def test_division():
    assert safe_eval("10 / 3") == pytest.approx(3.333333, abs=1e-4)


def test_floor_division():
    assert safe_eval("10 // 3") == 3.0


def test_negative_number():
    assert safe_eval("-5 + 3") == -2.0


def test_sqrt():
    assert safe_eval("sqrt(16)") == 4.0


def test_sin():
    assert safe_eval("sin(0)") == 0.0


def test_cos():
    assert safe_eval("cos(0)") == 1.0


def test_pi_constant():
    assert safe_eval("pi") == pytest.approx(math.pi)


def test_e_constant():
    assert safe_eval("e") == pytest.approx(math.e)


def test_complex_expression():
    assert safe_eval("sqrt(2**2 + 3**2)") == pytest.approx(math.sqrt(13))


def test_log():
    assert safe_eval("log(e)") == pytest.approx(1.0)


def test_abs_function():
    assert safe_eval("abs(-42)") == 42.0


def test_round_function():
    assert safe_eval("round(3.7)") == 4.0


# Security tests

def test_reject_import():
    with pytest.raises(ValueError):
        safe_eval("__import__('os')")


def test_reject_attribute_access():
    with pytest.raises(ValueError):
        safe_eval("().__class__")


def test_reject_unknown_function():
    with pytest.raises(ValueError):
        safe_eval("exec('print(1)')")


def test_reject_unknown_variable():
    with pytest.raises(ValueError):
        safe_eval("x + 1")


def test_reject_string_literal():
    with pytest.raises(ValueError):
        safe_eval("'hello'")


def test_division_by_zero():
    with pytest.raises(ZeroDivisionError):
        safe_eval("1 / 0")


# Integration test via registry

async def test_calculate_tool_via_registry():
    from app.skills.models import ToolCall
    from app.skills.registry import SkillRegistry
    from app.skills.tools.calculator_tools import register

    reg = SkillRegistry(skills_dir="/nonexistent")
    register(reg)

    result = await reg.execute_tool(ToolCall(name="calculate", arguments={"expression": "2 + 3"}))
    assert result.success
    assert result.content == "5"


async def test_calculate_tool_error():
    from app.skills.models import ToolCall
    from app.skills.registry import SkillRegistry
    from app.skills.tools.calculator_tools import register

    reg = SkillRegistry(skills_dir="/nonexistent")
    register(reg)

    result = await reg.execute_tool(ToolCall(name="calculate", arguments={"expression": "__import__('os')"}))
    assert result.success  # Handler catches ValueError
    assert "Error" in result.content
