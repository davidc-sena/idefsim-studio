"""Regra de desenho do fluxo da entidade: entra pela esquerda e sai pela direita.

Um fluxo cujo destino está atrás da origem (ex.: retrabalho voltando ao teste) não é
desenhado como seta de volta: é trocado por um par de Conexões (triângulos com a mesma
letra) — uma à direita da origem e outra à esquerda do destino.
"""
from __future__ import annotations

from .gui_free_geometry import SIZES, element_rect, overlaps
from .model import Connection, ConnectionKind as CK, Element, ElementKind as EK, Model

FLOW_GAP = 16    # mesma folga usada no desenho das setas
OFFSET = 45      # distância da conexão até o símbolo
GRID = 10


def _half_width(kind: EK) -> float:
    return SIZES[kind][0] / 2


def out_x(model: Model, element_id: str) -> float:
    e = model.elements[element_id]
    return e.x + _half_width(e.kind)


def in_x(model: Model, element_id: str) -> float:
    e = model.elements[element_id]
    return e.x - _half_width(e.kind)


def is_backward(model: Model, c: Connection) -> bool:
    """Fluxo que não consegue sair pela direita e entrar pela esquerda indo para a frente."""
    if c.kind != CK.FLOW:
        return False
    s, t = model.elements[c.source], model.elements[c.target]
    if EK.CONNECTOR in (s.kind, t.kind):
        return False  # conexões já são o "salto" do diagrama
    return in_x(model, t.id) - out_x(model, s.id) < FLOW_GAP


def _fresh_letter(model: Model) -> str:
    used = {e.name.strip().upper() for e in model.by_kind(EK.CONNECTOR)}
    abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for name in list(abc) + [a + b for a in abc for b in abc]:
        if name not in used:
            return name
    return "Z"  # pragma: no cover


def _free_spot(model: Model, x: float, y: float, step_y: float) -> tuple[float, float]:
    """Primeira posição livre (sem sobrepor símbolos) a partir de (x, y), andando na vertical."""
    probe = Element("?", EK.CONNECTOR, "?")
    others = [element_rect(e) for e in model.elements.values()]
    for k in range(12):
        cy = y + k * step_y
        if not any(overlaps(element_rect(probe, x, cy), r) for r in others):
            return x, cy
    return x, y


def _snap(v: float) -> float:
    return round(v / GRID) * GRID


def replace_with_connectors(model: Model, c: Connection) -> str:
    """Troca o fluxo de volta ``c`` por origem → Conexão X ... Conexão X → destino.
    Devolve a letra usada. Probabilidade, condição, rótulo e pontas ficam na 1ª ligação."""
    s, t = model.elements[c.source], model.elements[c.target]
    letter = _fresh_letter(model)
    # na mesma altura só se não houver outras setas naquele lado (para não ficar sobre elas)
    other_out = any(o.id != c.id for o in model.outgoing(s.id))
    other_in = any(i.id != c.id for i in model.incoming(t.id))
    x1, y1 = _free_spot(model, _snap(out_x(model, s.id) + OFFSET),
                        _snap(s.y + (70 if other_out else 0)), 50)
    x2, y2 = _free_spot(model, _snap(in_x(model, t.id) - OFFSET),
                        _snap(t.y + (70 if other_in else 0)), 50)
    c1 = model.add_element(EK.CONNECTOR, x1, y1, letter)
    c2 = model.add_element(EK.CONNECTOR, x2, y2, letter)
    del model.connections[c.id]
    first = model.add_connection(CK.FLOW, s.id, c1.id, probability=c.probability, label=c.label)
    first.condition, first.head_start, first.head_end = c.condition, c.head_start, c.head_end
    model.add_connection(CK.FLOW, c2.id, t.id)
    return letter


def fix_backward_flows(model: Model) -> list[str]:
    """Troca todos os fluxos de volta do modelo por pares de conexões; devolve as letras."""
    letters = []
    for c in list(model.connections.values()):
        if c.id in model.connections and is_backward(model, c):
            letters.append(replace_with_connectors(model, c))
    return letters
