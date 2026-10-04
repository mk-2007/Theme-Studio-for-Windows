"""Safe calculator for Spotlight (no eval)."""
from __future__ import annotations

import ast
import math
import operator as op
import re

_BIN = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.FloorDiv: op.floordiv, ast.Mod: op.mod, ast.Pow: op.pow}
_UN = {ast.USub: op.neg, ast.UAdd: op.pos}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "log": math.log10, "ln": math.log, "abs": abs, "round": round,
          "floor": math.floor, "ceil": math.ceil}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e6):
            raise ValueError("too large")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("unsupported")


def evaluate(text: str) -> str | None:
    """Return the formatted result, or None if `text` is not a math expression."""
    if len(text) > 200 or text.count("(") > 40:            # bound the work an expression can cause
        return None
    expr = text.strip().lower().replace("^", "**").replace("\u00d7", "*").replace("\u00f7", "/")
    expr = re.sub(r"(?<=\d),(?=\d{3}\b)", "", expr)
    if not expr or not re.search(r"\d", expr):
        return None
    if not re.search(r"[-+*/%()]|\b(sqrt|sin|cos|tan|log|ln|abs|round|floor|ceil)\b", expr):
        return None
    try:
        value = _eval(ast.parse(expr, mode="eval"))
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            value = round(value, 10)
            if value == int(value) and abs(value) < 1e15:
                value = int(value)
        if isinstance(value, int):
            if abs(value) >= 10 ** 60:                       # keep results short (and under Python's int->str limit)
                return f"{float(value):.6e}"
            return f"{value:,}"
        return str(value)
    except (Exception, RecursionError, MemoryError):
        return None
