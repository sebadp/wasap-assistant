from __future__ import annotations

import ast
import logging
import math
import operator

from app.skills.registry import SkillRegistry

# Whitelist of allowed operations
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "abs": abs,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
}

_ALLOWED_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval_node(node: ast.AST) -> float:
    """Recursively evaluate an AST node with strict whitelist."""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]
        raise ValueError(f"Unknown variable: {node.id}")

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        operand = _safe_eval_node(node.operand)
        return _ALLOWED_OPERATORS[op_type](operand)  # type: ignore[operator]

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)  # type: ignore[assignment]
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        return _ALLOWED_OPERATORS[op_type](left, right)  # type: ignore[operator]

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct function calls are allowed")
        func_name = node.func.id
        if func_name not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"Unknown function: {func_name}")
        args = [_safe_eval_node(arg) for arg in node.args]
        return _ALLOWED_FUNCTIONS[func_name](*args)  # type: ignore[operator]

    raise ValueError(f"Unsupported expression: {type(node).__name__}")


def safe_eval(expression: str) -> float:
    """Safely evaluate a math expression using AST parsing."""
    tree = ast.parse(expression, mode="eval")
    return _safe_eval_node(tree)


logger = logging.getLogger(__name__)


def register(registry: SkillRegistry) -> None:

    async def calculate(expression: str) -> str:
        logger.info(f"Calculating expression: {expression}")
        try:
            result = safe_eval(expression)
            # Format nicely: remove trailing .0 for integers
            if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
                formatted_result = str(int(result))
            else:
                formatted_result = str(result)
            logger.info(f"Calculation result: {formatted_result}")
            return formatted_result
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as e:
            logger.warning(f"Calculation error for '{expression}': {e}")
            return f"Error: {e}"

    registry.register_tool(
        name="calculate",
        description="Evaluate a mathematical expression safely",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression to evaluate (e.g. '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)')",
                },
            },
            "required": ["expression"],
        },
        handler=calculate,
        skill_name="calculator",
    )
