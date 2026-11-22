"""Identidade visual: símbolo do logo, janela de abertura (splash) e créditos."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QDialog, QLabel, QSplashScreen, QVBoxLayout

from .. import APP_NAME, AUTHOR, EMAIL, INSTITUTION, YEAR, __version__

RES = Path(__file__).resolve().parents[1] / "resources"
BLUE = QColor("#1b4f9c")
BLUE_DARK = QColor("#0e2c5a")
AMBER = QColor("#ffcf5c")
INK = QColor("#1d2433")
MUTED = QColor("#5b6475")
FAMILY = "Inter"
_fonts_loaded = False


def load_fonts() -> str:
    """Registra a fonte Inter embutida; devolve a família a usar."""
    global _fonts_loaded, FAMILY
    if not _fonts_loaded:
        ok = False
        for f in sorted((RES / "fonts").glob("*.otf")):
            ok = QFontDatabase.addApplicationFont(str(f)) >= 0 or ok
        FAMILY = "Inter" if ok else QFont().family()
        _fonts_loaded = True
    return FAMILY


def font(size: float, weight=QFont.Normal, spacing: float = 0.0) -> QFont:
    f = QFont(load_fonts())
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


# --------------------------------------------------------------------- símbolo
def paint_mark(p: QPainter, rect: QRectF, background: bool = True) -> None:
    """Desenha o símbolo: entrada externa → entidade → função, com recurso por baixo."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.topLeft())
    s = min(rect.width(), rect.height()) / 100.0
    p.scale(s, s)
    if background:
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(2, 2, 96, 96), 22, 22)
        g = QLinearGradient(0, 0, 100, 100)
        g.setColorAt(0, QColor("#2a6fd1"))
        g.setColorAt(1, BLUE_DARK)
        p.fillPath(bg, QBrush(g))
    _symbols(p, QColor("white") if background else BLUE)
    p.restore()


def mark_pixmap(size: int, dpr: float = 1.0) -> QPixmap:
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_mark(p, QRectF(0, 0, size, size))
    p.end()
    return pm


# ------------------------------------------------------------- janela de abertura
SPLASH_W, SPLASH_H = 640, 380


def paint_splash(p: QPainter, status: str | None = "Carregando…") -> None:
    W, H = SPLASH_W, SPLASH_H
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    card = QPainterPath()
    card.addRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 14, 14)
    p.fillPath(card, QColor("white"))
    p.save()
    p.setClipPath(card)
    # faixa lateral com o símbolo
    side = QRectF(0, 0, 232, H)
    g = QLinearGradient(0, 0, 232, H)
    g.setColorAt(0, QColor("#2a6fd1"))
    g.setColorAt(1, BLUE_DARK)
    p.fillRect(side, g)
    # grade sutil (alusão à área de modelagem)
    p.setPen(QPen(QColor(255, 255, 255, 18), 1))
    for x in range(0, 232, 16):
        p.drawLine(x, 0, x, H)
    for y in range(0, H, 16):
        p.drawLine(0, y, 232, y)
    # símbolo em branco sobre a faixa
    p.save()
    k = 1.9                                    # símbolo ocupa x 5..90, y 27..76
    p.translate(116 - 47.5 * k, H / 2 - 51.5 * k)
    p.scale(k, k)
    _symbols(p, QColor("white"))
    p.restore()
    # rodapé
    p.fillRect(QRectF(232, H - 44, W - 232, 44), QColor("#f4f6fa"))
    p.restore()

    x0 = 268
    p.setPen(INK)
    p.setFont(font(26, QFont.Bold, -0.4))
    p.drawText(QRectF(x0, 46, W - x0 - 24, 40), Qt.AlignLeft | Qt.AlignVCenter, APP_NAME)
    p.setPen(MUTED)
    p.setFont(font(10.5))
    p.drawText(QRectF(x0, 88, W - x0 - 24, 40), Qt.AlignLeft | Qt.TextWordWrap,
               "Modelagem conceitual IDEF-SIM, validação e\nsimulação a eventos discretos")
    # versão
    p.setFont(font(8.5, QFont.DemiBold, 0.6))
    vtxt = f"VERSÃO {__version__}"
    vw = p.fontMetrics().horizontalAdvance(vtxt) + 18
    pill = QPainterPath()
    pill.addRoundedRect(QRectF(x0, 136, vw, 22), 11, 11)
    p.fillPath(pill, QColor("#e8f0fc"))
    p.setPen(BLUE)
    p.drawText(QRectF(x0, 136, vw, 22), Qt.AlignCenter, vtxt)
    # créditos
    p.setPen(QPen(QColor("#e3e7ee"), 1))
    p.drawLine(QPointF(x0, 180), QPointF(W - 28, 180))
    p.setPen(BLUE)
    p.setFont(font(8.5, QFont.DemiBold, 1.4))
    p.drawText(QRectF(x0, 194, 300, 18), Qt.AlignLeft, "DESENVOLVIDO POR")
    p.setPen(INK)
    p.setFont(font(14, QFont.DemiBold))
    p.drawText(QRectF(x0, 214, W - x0 - 24, 26), Qt.AlignLeft | Qt.AlignVCenter, AUTHOR)
    p.setPen(MUTED)
    p.setFont(font(11, QFont.Medium))
    p.drawText(QRectF(x0, 242, W - x0 - 24, 22), Qt.AlignLeft | Qt.AlignVCenter, INSTITUTION)
    p.setPen(BLUE)
    p.setFont(font(11))
    p.drawText(QRectF(x0, 264, W - x0 - 24, 22), Qt.AlignLeft | Qt.AlignVCenter, EMAIL)
    # rodapé
    p.setPen(MUTED)
    p.setFont(font(8.5))
    left = status if status else f"© {YEAR} · {INSTITUTION}"   # curto: não encosta no texto à direita
    p.drawText(QRectF(x0, H - 44, W - x0 - 24, 44), Qt.AlignLeft | Qt.AlignVCenter, left)
    p.drawText(QRectF(x0, H - 44, W - x0 - 24, 44), Qt.AlignRight | Qt.AlignVCenter,
               "Notação: Leal, Almeida e Montevechi (2008)")
    p.setPen(QPen(QColor("#d5dbe5"), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(card)


def _symbols(p: QPainter, white: QColor) -> None:
    """Entrada externa (dois traços) → entidade → função, com recurso por baixo (caixa 100×100)."""
    pen = QPen(white, 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    def head(tip, dx, dy, size=6.5):
        nx, ny = -dy, dx
        p.setPen(Qt.NoPen)
        p.setBrush(white)
        p.drawPolygon(QPolygonF([
            tip,
            QPointF(tip.x() - dx * size + nx * size * 0.62, tip.y() - dy * size + ny * size * 0.62),
            QPointF(tip.x() - dx * size - nx * size * 0.62, tip.y() - dy * size - ny * size * 0.62)]))

    cy = 40
    p.setPen(pen)
    p.drawLine(QPointF(5, cy), QPointF(17, cy))
    p.drawLine(QPointF(8, cy - 5.5), QPointF(8, cy + 5.5))
    p.drawLine(QPointF(13, cy - 5.5), QPointF(13, cy + 5.5))
    head(QPointF(23, cy), 1, 0)
    p.setPen(QPen(white, 3))
    p.setBrush(AMBER)
    p.drawEllipse(QPointF(33.5, cy), 10, 10)
    p.setPen(pen)
    p.drawLine(QPointF(44.5, cy), QPointF(50, cy))
    head(QPointF(56, cy), 1, 0)
    p.setPen(QPen(white, 3))
    p.setBrush(QColor(255, 255, 255, 235) if white == QColor("white") else QColor("#e3eefc"))
    p.drawRoundedRect(QRectF(56, 27, 34, 26), 2.5, 2.5)
    p.setPen(pen)
    p.drawLine(QPointF(63, 76), QPointF(83, 76))
    p.drawLine(QPointF(73, 76), QPointF(73, 60))
    head(QPointF(73, 53.5), 0, -1)


def splash_pixmap(dpr: float = 1.0, status: str | None = "Carregando…") -> QPixmap:
    pm = QPixmap(int(SPLASH_W * dpr), int(SPLASH_H * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_splash(p, status)
    p.end()
    return pm


class SplashScreen(QSplashScreen):
    """Janela de abertura; um clique fecha antes do tempo."""
    clicked = Signal()

    def __init__(self, dpr: float = 1.0):
        super().__init__(splash_pixmap(dpr), Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def mousePressEvent(self, ev):
        self.clicked.emit()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Sobre o {APP_NAME}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        img = QLabel()
        img.setPixmap(splash_pixmap(self.devicePixelRatioF(), status=None))
        lay.addWidget(img)
        ref = QLabel("Referência da notação: LEAL, F.; ALMEIDA, D. A.; MONTEVECHI, J. A. B. "
                     "<i>Uma proposta de técnica de modelagem conceitual para a simulação através "
                     "de elementos do IDEF</i>. SBPO, 2008.<br>"
                     "Fonte Inter © The Inter Project Authors (SIL Open Font License 1.1).")
        ref.setWordWrap(True)
        ref.setStyleSheet("color:#5b6475;font-size:9pt")
        lay.addWidget(ref)
        self.setFixedWidth(SPLASH_W + 24)
