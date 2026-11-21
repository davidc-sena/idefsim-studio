"""Condições sobre atributos das entidades, usadas na regra OU por atributo.

Sintaxe (português ou símbolos)::

    tipo == 2
    peso > 10 e tipo != 3
    prioridade >= 2 ou urgente == 1
    não (defeito == 1)
    senão                      ← saída padrão, quando nenhuma condição é verdadeira

Operadores: ``== != < <= > >= + - * /``, ``e``/``and``, ``ou``/``or``, ``não``/``not`` e
parênteses. Os nomes são atributos da entidade. A avaliação é feita sobre a árvore
sintática (não usa ``eval``), e a mesma condição é traduzida para o JaamSim
(``this.obj.peso > 10 && this.obj.tipo != 3``).
"""
from __future__ import annotations

import ast
import operator
import re
import unicodedata

DEFAULT_WORDS = {"senao", "senão", "else", "default", "padrao", "padrão", "outro", "outros"}

_CMP = {ast.Eq: (operator.eq, "=="), ast.NotEq: (operator.ne, "!="), ast.Lt: (operator.lt, "<"),
        ast.LtE: (operator.le, "<="), ast.Gt: (operator.gt, ">"), ast.GtE: (operator.ge, ">=")}
_BIN = {ast.Add: (operator.add, "+"), ast.Sub: (operator.sub, "-"),
        ast.Mult: (operator.mul, "*"), ast.Div: (operator.truediv, "/")}
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ExpressionError(ValueError):
    pass


def is_default(text: str) -> bool:
    return text.strip().lower() in DEFAULT_WORDS


def valid_attribute_name(name: str) -> bool:
    """Atributo: letras sem acento, números e _ (vale também no JaamSim)."""
    return bool(NAME_RE.match(name)) and name.lower() not in {"e", "ou", "nao", "and", "or", "not",
                                                               "this", "obj", "null"}


def _normalize(text: str) -> str:
    t = " " + text.strip() + " "
    t = re.sub(r"(?i)(?<![\w])não(?![\w])", " not ", t)
    t = re.sub(r"(?i)(?<![\w])nao(?![\w])", " not ", t)
    t = re.sub(r"(?i)(?<![\w])e(?![\w])", " and ", t)
    t = re.sub(r"(?i)(?<![\w])ou(?![\w])", " or ", t)
    t = t.replace("&&", " and ").replace("||", " or ")
    t = re.sub(r"!(?!=)", " not ", t)
    t = re.sub(r"(?<![<>=!])=(?!=)", "==", t)  # aceita '=' como comparação
    return t.strip()


def parse(text: str) -> ast.Expression:
    if not text or not text.strip():
        raise ExpressionError("Condição vazia.")
    if is_default(text):
        raise ExpressionError("'senão' não é uma condição (é a saída padrão).")
    norm = _normalize(text)
    if not norm.isascii():
        norm2 = unicodedata.normalize("NFKD", norm).encode("ascii", "ignore").decode()
        if norm2 != norm:
            raise ExpressionError("Use nomes de atributos sem acentos.")
    try:
        tree = ast.parse(norm, mode="eval")
    except SyntaxError:
        raise ExpressionError(f"Condição inválida: {text}") from None
    _check(tree.body)
    return tree


def _check(n: ast.AST) -> None:
    if isinstance(n, ast.BoolOp):
        for v in n.values:
            _check(v)
    elif isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.Not, ast.USub, ast.UAdd)):
        _check(n.operand)
    elif isinstance(n, ast.Compare):
        if any(type(op) not in _CMP for op in n.ops):
            raise ExpressionError("Comparação não suportada (use ==, !=, <, <=, >, >=).")
        _check(n.left)
        for c in n.comparators:
            _check(c)
    elif isinstance(n, ast.BinOp) and type(n.op) in _BIN:
        _check(n.left)
        _check(n.right)
    elif isinstance(n, ast.Name):
        if not valid_attribute_name(n.id):
            raise ExpressionError(f"Nome de atributo inválido: {n.id}")
    elif isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
            and not isinstance(n.value, bool):
        pass
    else:
        raise ExpressionError("Use apenas atributos, números, comparações e e/ou/não.")


def names(text: str) -> set[str]:
    return {n.id for n in ast.walk(parse(text)) if isinstance(n, ast.Name)}


def evaluate(text: str, attrs: dict[str, float]) -> bool:
    def ev(n):
        if isinstance(n, ast.BoolOp):
            vals = (ev(v) for v in n.values)
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return (not v) if isinstance(n.op, ast.Not) else (-v if isinstance(n.op, ast.USub) else v)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, c in zip(n.ops, n.comparators):
                right = ev(c)
                if not _CMP[type(op)][0](left, right):
                    return False
                left = right
            return True
        if isinstance(n, ast.BinOp):
            return _BIN[type(n.op)][0](ev(n.left), ev(n.right))
        if isinstance(n, ast.Name):
            return attrs.get(n.id, 0.0)
        return n.value
    return bool(ev(parse(text).body))


def to_jaamsim(text: str) -> str:
    """Traduz a condição para uma expressão do JaamSim sobre ``this.obj``."""
    def tr(n) -> str:
        if isinstance(n, ast.BoolOp):
            op = " && " if isinstance(n.op, ast.And) else " || "
            return "(" + op.join(tr(v) for v in n.values) + ")"
        if isinstance(n, ast.UnaryOp):
            sym = "!" if isinstance(n.op, ast.Not) else ("-" if isinstance(n.op, ast.USub) else "")
            return f"{sym}({tr(n.operand)})"
        if isinstance(n, ast.Compare):
            parts, left = [], tr(n.left)
            for op, c in zip(n.ops, n.comparators):
                right = tr(c)
                parts.append(f"{left} {_CMP[type(op)][1]} {right}")
                left = right
            return parts[0] if len(parts) == 1 else "(" + " && ".join(parts) + ")"
        if isinstance(n, ast.BinOp):
            return f"({tr(n.left)} {_BIN[type(n.op)][1]} {tr(n.right)})"
        if isinstance(n, ast.Name):
            return f"this.obj.{n.id}"
        return f"{n.value:g}" if isinstance(n.value, float) else str(n.value)
    out = tr(parse(text).body)
    return out[1:-1] if out.startswith("(") and out.endswith(")") and out.count("(") == 1 else out
