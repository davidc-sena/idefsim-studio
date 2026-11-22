"""Itens gráficos do diagrama."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..model import (Connection, ConnectionKind as CK, Element, ElementKind as EK,
                     PROCESS_KINDS, RULE_KINDS)
from .. import expressions as expr
from . import shapes

GRID = 10
FLOW_GAP = 16      # trecho mínimo antes de dobrar (fluxo entra à esquerda e sai à direita)


class NodeItem(QGraphicsItem):
    def __init__(self, element: Element):
        super().__init__()
        self.element = element
        self.edges: list[EdgeItem] = []
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setPos(element.x, element.y)
        self.setZValue(1 if element.kind != EK.NOTE else 0.5)
        self._rect = shapes.node_rect(element.kind)
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        e = self.element
        from ..model import KIND_LABELS
        lines = [f"<b>{KIND_LABELS[e.kind]}</b>: {e.name}"]
        lines += [f"{k}: {v}" for k, v in e.params.items()]
        if e.description:
            lines.append(f"<i>{e.description}</i>")
        return "<br>".join(lines)

    def refresh(self) -> None:
        self.prepareGeometryChange()
        self.setToolTip(self._tooltip())
        self.update()
        for ed in self.edges:
            ed.adjust()

    def _criterion(self) -> str:
        e = self.element
        if e.kind == EK.RULE_OR and e.params.get("decision") == "visual":
            return e.params.get("criterion", "").strip()
        return ""

    def has_entry_arrow(self) -> bool:
        return self.element.kind == EK.ENTITY and bool(self.element.params.get("external_arrival"))

    def boundingRect(self) -> QRectF:
        r = self._rect.adjusted(-3, -3, 3, 3)
        if self.element.kind == EK.EXIT or self._criterion():
            r = r.adjusted(-40, 0, 40, 34)
        if self.has_entry_arrow():
            L = shapes.ENTRY_LENGTH + 4
            r = r.adjusted(-L, -L, L, L)
        return r

    def shape(self) -> QPainterPath:
        return shapes.node_path(self.element.kind, self._rect)

    def paint(self, painter, option, widget=None):
        shapes.paint_node(painter, self.element.kind, self._rect, self.element.name,
                          self.isSelected())
        if self.element.kind == EK.FUNCTION and self.element.params.get("is_queue"):
            # marca de fila: caixa aberta com três entidades em espera, no canto superior direito
            r = self._rect
            w, h = 22.0, 9.0
            x0, y0 = r.right() - w - 5, r.top() + 5
            pen = QPen(shapes.SELECT if self.isSelected() else shapes.INK, 1.1)
            painter.setPen(pen)
            painter.drawLine(QPointF(x0, y0), QPointF(x0 + w, y0))
            painter.drawLine(QPointF(x0, y0 + h), QPointF(x0 + w, y0 + h))
            painter.drawLine(QPointF(x0 + w, y0), QPointF(x0 + w, y0 + h))
            painter.setBrush(pen.color())
            for i in range(3):
                painter.drawEllipse(QPointF(x0 + w - 4.5 - i * 6.5, y0 + h / 2), 2.2, 2.2)
            painter.setBrush(Qt.NoBrush)
        crit = self._criterion()
        if crit:  # regra OU apenas visual: critério escrito abaixo do símbolo
            box = QRectF(self._rect.left() - 40, self._rect.bottom() + 2, self._rect.width() + 80, 30)
            f = QFont(painter.font())
            shapes.set_font_size(f, 8)
            f.setItalic(True)
            painter.setFont(f)
            painter.setPen(shapes.SELECT if self.isSelected() else shapes.INK)
            painter.drawText(box, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, crit)
        if self.has_entry_arrow():
            side = self.element.params.get("arrival_side", "left")
            vx, vy = shapes.SIDE_VECTORS.get(side, (-1, 0))
            rad = self._rect.width() / 2
            color = shapes.SELECT if self.isSelected() else shapes.INK
            shapes.draw_entry_arrow(painter, QPointF(vx * rad, vy * rad), side, color)

    def body_rect(self) -> QRectF:
        """Retângulo útil do símbolo em coordenadas de cena (corpo da seta na movimentação)."""
        r = self._rect
        if self.element.kind == EK.MOVEMENT:
            head = min(28.0, r.width() * 0.25)
            r = r.adjusted(0, r.height() * 0.22, -head, -r.height() * 0.22)
        return r.translated(self.scenePos())

    def boundary_point(self, toward: QPointF) -> QPointF:
        c = self.scenePos()
        dx, dy = toward.x() - c.x(), toward.y() - c.y()
        if dx == 0 and dy == 0:
            return c
        if self.element.kind in shapes.CIRCULAR:
            rad = self._rect.width() / 2
            d = math.hypot(dx, dy)
            return QPointF(c.x() + dx / d * rad, c.y() + dy / d * rad)
        if self.element.kind == EK.CONNECTOR:  # interseção do raio com o triângulo
            poly = shapes.triangle_polygon(self._rect)
            best = None
            for i in range(3):
                a, b = poly[i], poly[(i + 1) % 3]
                ex, ey = b.x() - a.x(), b.y() - a.y()
                den = dx * ey - dy * ex
                if abs(den) < 1e-9:
                    continue
                t = (a.x() * ey - a.y() * ex) / den        # ao longo do raio (origem no centro)
                u = (a.x() * dy - a.y() * dx) / den        # ao longo da aresta
                if t > 0 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best):
                    best = t
            if best is not None:
                return QPointF(c.x() + dx * best, c.y() + dy * best)
        hw, hh = self._rect.width() / 2, self._rect.height() / 2
        if self.element.kind == EK.MOVEMENT:  # corpo da seta é mais estreito
            hh -= self._rect.height() * 0.22
        t = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
        return QPointF(c.x() + dx * t, c.y() + dy * t)

    def flow_port(self, edge, side: str) -> QPointF:
        """Ponto de encaixe do fluxo: entra pelo lado esquerdo ("in") e sai pelo direito ("out").
        Várias setas no mesmo lado são distribuídas na altura, na ordem da outra ponta."""
        if side == "in":
            sibs = [e for e in self.edges if e.conn.kind == CK.FLOW and e.dst is self]
            other = lambda e: e.src  # noqa: E731
        else:
            sibs = [e for e in self.edges if e.conn.kind == CK.FLOW and e.src is self]
            other = lambda e: e.dst  # noqa: E731
        sibs.sort(key=lambda e: (other(e).scenePos().y(), other(e).scenePos().x(), e.conn.id))
        n = len(sibs)
        i = sibs.index(edge) if edge in sibs else 0
        r, k = self._rect, self.element.kind
        if k in RULE_KINDS or k in shapes.CIRCULAR or k == EK.CONNECTOR:
            n = 1  # símbolos pequenos: um ponto só; as setas se ramificam a partir dele
        usable = r.height() * (0.34 if k == EK.MOVEMENT else 0.6)
        dy = ((i + 1) / (n + 1) - 0.5) * usable if n > 1 else 0.0
        if k in shapes.CIRCULAR:
            rad = r.width() / 2
            x = math.sqrt(max(rad * rad - dy * dy, 0.0))
            x = -x if side == "in" else x
        elif k == EK.CONNECTOR:  # na aresta inclinada do triângulo, à altura dy
            frac = (r.bottom() - dy) / r.height()
            half = frac * r.width() / 2
            x = -half if side == "in" else half
        elif k == EK.MOVEMENT and side == "out" and n <= 1:
            x = r.right()                                   # ponta da seta larga
        elif k == EK.MOVEMENT and side == "out":
            x = r.right() - min(28.0, r.width() * 0.25)
        else:
            x = r.left() if side == "in" else r.right()
        return self.scenePos() + QPointF(x, dy)

    def scene_body(self) -> QRectF:
        return self._rect.translated(self.scenePos())

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            v = QPointF(value)
            return QPointF(round(v.x() / GRID) * GRID, round(v.y() / GRID) * GRID)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.element.x, self.element.y = self.pos().x(), self.pos().y()
            todo = set(self.edges)
            for ed in self.edges:  # a ordem dos encaixes nas faces vizinhas pode mudar
                if ed.conn.kind in SIDE_KINDS:
                    todo.update(e for e in ed.dst.edges if e.conn.kind == ed.conn.kind)
                elif ed.conn.kind == CK.FLOW:
                    for n in (ed.src, ed.dst):
                        todo.update(e for e in n.edges if e.conn.kind == CK.FLOW)
            for ed in todo:
                ed.adjust()
        return super().itemChange(change, value)


SIDE_KINDS = (CK.RESOURCE, CK.CONTROL)
_GAP = 18  # afastamento mínimo das rotas ortogonais


def _route_from_below(src: QRectF, body: QRectF, tx: float) -> list[QPointF]:
    """Rota ortogonal de um rótulo até à face inferior de ``body`` (no ponto tx)."""
    t = QPointF(tx, body.bottom())
    sx = src.center().x()
    if src.top() >= body.bottom() + 4:            # caso normal: rótulo abaixo
        s = QPointF(sx, src.top())
        if abs(sx - tx) < 1:
            return [s, t]
        ym = (s.y() + t.y()) / 2
        return [s, QPointF(sx, ym), QPointF(tx, ym), t]
    ylow = max(body.bottom(), src.bottom()) + _GAP
    s = QPointF(sx, src.bottom())
    if src.bottom() + _GAP < body.top():          # rótulo acima: contorna a função
        x_out = body.left() - _GAP if sx < body.center().x() else body.right() + _GAP
        y1 = s.y() + _GAP / 2
        return [s, QPointF(sx, y1), QPointF(x_out, y1), QPointF(x_out, ylow),
                QPointF(tx, ylow), t]
    return [s, QPointF(sx, ylow), QPointF(tx, ylow), t]   # rótulo ao lado


def route_flow(a: QPointF, b: QPointF, src: QRectF, dst: QRectF) -> list[QPointF]:
    """Fluxo da entidade: sai pela direita (a) e entra pela esquerda (b), com trechos retos.
    Se o destino estiver atrás da origem, contorna por baixo dos dois símbolos."""
    if b.x() - a.x() >= FLOW_GAP:
        if abs(a.y() - b.y()) < 0.5:
            return [a, b]
        mx = round((a.x() + b.x()) / 2 / 5) * 5
        return [a, QPointF(mx, a.y()), QPointF(mx, b.y()), b]
    ylow = max(src.bottom(), dst.bottom()) + 24
    return [a, QPointF(a.x() + FLOW_GAP, a.y()), QPointF(a.x() + FLOW_GAP, ylow),
            QPointF(b.x() - FLOW_GAP, ylow), QPointF(b.x() - FLOW_GAP, b.y()), b]


def _flip(r: QRectF) -> QRectF:
    return QRectF(r.left(), -r.bottom(), r.width(), r.height())


class EdgeItem(QGraphicsItem):
    def __init__(self, conn: Connection, src: NodeItem, dst: NodeItem, model):
        super().__init__()
        self.conn, self.src, self.dst, self.model = conn, src, dst, model
        src.edges.append(self)
        dst.edges.append(self)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        # acima dos símbolos, para a ponta nunca ficar escondida atrás de um elemento vizinho
        self.setZValue(2)
        self.points: list[QPointF] = [QPointF(), QPointF()]
        self.adjust()

    def detach(self) -> None:
        for n in (self.src, self.dst):
            if self in n.edges:
                n.edges.remove(self)

    def label_text(self) -> str:
        c = self.conn
        parts = [c.label] if c.label else []
        if c.kind == CK.FLOW:
            src = self.model.elements[c.source]
            n_out = len(self.model.outgoing(src.id))
            decision = self.model.decision_of(src.id)
            if src.kind == EK.RULE_OR and decision == "condition":
                cond = c.condition.strip()
                parts.append("senão" if not cond or expr.is_default(cond) else cond)
                return "  ".join(parts)
            if src.kind == EK.RULE_OR and decision == "visual":
                return "  ".join(parts)
            if (src.kind in (EK.RULE_OR, EK.RULE_ANDOR) or
                    (src.kind in PROCESS_KINDS and n_out > 1)) and n_out > 0:
                parts.append(f"{c.probability * 100:g}%")
        return "  ".join(parts)

    def _slot_x(self, body: QRectF) -> float:
        """Distribui várias ligações do mesmo tipo ao longo da face da função."""
        sibs = sorted((e for e in self.dst.edges if e.conn.kind == self.conn.kind),
                      key=lambda e: (e.src.scenePos().x(), e.conn.id))
        if len(sibs) <= 1:  # uma só ligação: seta reta se o rótulo estiver alinhado
            sx = self.src.body_rect().center().x()
            return min(max(sx, body.left() + 12), body.right() - 12)
        i = sibs.index(self) if self in sibs else 0
        return body.left() + body.width() * (i + 1) / (len(sibs) + 1)

    def adjust(self) -> None:
        self.prepareGeometryChange()
        if self.conn.kind in SIDE_KINDS:
            body, src = self.dst.body_rect(), self.src.body_rect()
            tx = self._slot_x(body)
            if self.conn.kind == CK.RESOURCE:     # recurso: entra por baixo
                pts = _route_from_below(src, body, tx)
            else:                                 # controle: entra por cima (espelhado)
                pts = [QPointF(p.x(), -p.y()) for p in
                       _route_from_below(_flip(src), _flip(body), tx)]
            self.points = pts
        elif self.conn.kind == CK.FLOW:
            a = self.src.flow_port(self, "out")
            b = self.dst.flow_port(self, "in")
            self.points = route_flow(a, b, self.src.scene_body(), self.dst.scene_body())
        else:  # ligação de nota: reta entre as bordas
            self.points = [self.src.boundary_point(self.dst.scenePos()),
                           self.dst.boundary_point(self.src.scenePos())]
        self.update()

    def _path(self) -> QPainterPath:
        p = QPainterPath(self.points[0])
        for pt in self.points[1:]:
            p.lineTo(pt)
        return p

    def boundingRect(self) -> QRectF:
        return self._path().boundingRect().adjusted(-60, -20, 60, 20)

    def shape(self) -> QPainterPath:
        st = QPainterPathStroker()
        st.setWidth(10)
        return st.createStroke(self._path())

    def paint(self, painter, option, widget=None):
        if self._path().length() < 2:
            return
        color = shapes.SELECT if self.isSelected() else shapes.INK
        shapes.draw_link(painter, self.conn.kind, self.points, color, heads=self.conn.heads)
        txt = self.label_text() if shapes.STYLE["edge_labels"] else ""
        if txt:
            # rótulo no último trecho (junto ao destino); se for curto, no trecho mais longo
            segs = list(zip(self.points[:-1], self.points[1:]))
            seg = segs[-1]
            if (seg[1] - seg[0]).manhattanLength() < 60:
                seg = max(segs, key=lambda s: (s[1] - s[0]).manhattanLength())
            mid = (seg[0] + seg[1]) / 2
            f = QFont(painter.font())
            shapes.set_font_size(f, 8)
            painter.setFont(f)
            r = painter.boundingRect(QRectF(mid.x() - 60, mid.y() - 18, 120, 14),
                                     Qt.AlignCenter, txt)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawRect(r.adjusted(-2, 0, 2, 0))
            painter.setPen(QPen(color))
            painter.drawText(r, Qt.AlignCenter, txt)
