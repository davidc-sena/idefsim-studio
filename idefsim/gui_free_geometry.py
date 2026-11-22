"""Tamanho dos símbolos sem depender do Qt (usado pelo layout da importação)."""
from __future__ import annotations

from .model import ElementKind as EK

SIZES = {EK.ENTITY: (64, 64), EK.FUNCTION: (130, 64), EK.RESOURCE: (120, 30), EK.CONTROL: (120, 30),
         EK.MOVEMENT: (130, 56), EK.RULE_AND: (38, 38), EK.RULE_OR: (38, 38), EK.RULE_ANDOR: (38, 38),
         EK.EXIT: (40, 40), EK.CONNECTOR: (42, 38), EK.NOTE: (150, 56)}
MARGIN = 8


def element_rect(e, x: float | None = None, y: float | None = None) -> tuple[float, float, float, float]:
    w, h = SIZES[e.kind]
    x = e.x if x is None else x
    y = e.y if y is None else y
    if e.kind == EK.EXIT:
        h += 34  # nome abaixo
    return (x - w / 2 - MARGIN, y - h / 2 - MARGIN, x + w / 2 + MARGIN, y + h / 2 + MARGIN)


def overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
