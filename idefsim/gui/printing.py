"""Impressão e exportação "limpa" do diagrama (sem grade, seleção ou cores de edição)."""
from __future__ import annotations

import datetime as _dt
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout)

from .. import APP_NAME, __version__
from . import branding, shapes

MARGIN = 24  # margem (unidades de cena) em volta do diagrama


@dataclass
class CleanOptions:
    mono: bool = True            # preto e branco
    header: bool = True          # título, autor e data
    edge_labels: bool = True     # probabilidades e rótulos nas setas


class CleanOptionsDialog(QDialog):
    def __init__(self, title: str, opts: CleanOptions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("O diagrama sai sem grade, seleção nem marcas de edição."))
        self.mono = QCheckBox("Preto e branco (sem cores de preenchimento)")
        self.header = QCheckBox("Título do modelo, autor e data")
        self.labels = QCheckBox("Probabilidades e rótulos nas setas")
        for cb, v in ((self.mono, opts.mono), (self.header, opts.header),
                      (self.labels, opts.edge_labels)):
            cb.setChecked(v)
            lay.addWidget(cb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def options(self) -> CleanOptions:
        return CleanOptions(self.mono.isChecked(), self.header.isChecked(), self.labels.isChecked())


@contextmanager
def clean_scene(scene, opts: CleanOptions):
    """Prepara a cena para a saída limpa e restaura tudo no fim."""
    sel = scene.selectedItems()
    old = dict(shapes.STYLE)
    scene.clearSelection()
    scene.show_grid = False
    shapes.STYLE.update(mono=opts.mono, edge_labels=opts.edge_labels)
    for it in scene.items():
        it.update()
    try:
        yield
    finally:
        shapes.STYLE.update(old)
        scene.show_grid = True
        for it in sel:
            it.setSelected(True)
        for it in scene.items():
            it.update()


def diagram_rect(scene) -> QRectF:
    return scene.itemsBoundingRect().adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)


def render(scene, model, painter: QPainter, page: QRectF, opts: CleanOptions) -> None:
    """Desenha o diagrama limpo (e, se pedido, cabeçalho/rodapé) dentro de ``page``."""
    dpi = painter.device().logicalDpiY() or 96
    unit = dpi / 72.0  # 1 ponto tipográfico em unidades do dispositivo
    area = QRectF(page)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.fillRect(page, Qt.white)
    if opts.header:
        head_h, foot_h = 30 * unit, 16 * unit
        ink = QColor("#111111")
        painter.setPen(ink)
        painter.setFont(branding.font(14, QFont.DemiBold))
        painter.drawText(QRectF(area.left(), area.top(), area.width(), 20 * unit),
                         Qt.AlignLeft | Qt.AlignVCenter, model.name)
        painter.setFont(branding.font(8))
        painter.setPen(QColor("#444444"))
        sub = "Modelo conceitual IDEF-SIM" + (f" — versão {model.version}" if model.version else "")
        painter.drawText(QRectF(area.left(), area.top(), area.width(), 20 * unit),
                         Qt.AlignRight | Qt.AlignVCenter, sub)
        painter.setPen(QPen(ink, max(1.0, 0.6 * unit)))
        y = area.top() + 22 * unit
        painter.drawLine(area.left(), y, area.right(), y)
        foot = QRectF(area.left(), area.bottom() - 12 * unit, area.width(), 12 * unit)
        painter.setPen(QPen(QColor("#999999"), max(1.0, 0.4 * unit)))
        painter.drawLine(foot.left(), foot.top() - 2 * unit, foot.right(), foot.top() - 2 * unit)
        painter.setPen(QColor("#444444"))
        left = f"Autor: {model.author}" if model.author else ""
        painter.drawText(foot, Qt.AlignLeft | Qt.AlignVCenter, left)
        painter.drawText(foot, Qt.AlignRight | Qt.AlignVCenter,
                         f"{APP_NAME} {__version__} — {_dt.date.today():%d/%m/%Y}")
        area = area.adjusted(0, head_h, 0, -foot_h)
    with clean_scene(scene, opts):
        src = diagram_rect(scene)
        scene.render(painter, area, src, Qt.KeepAspectRatio)
    painter.restore()


def _landscape(scene) -> bool:
    r = diagram_rect(scene)
    return r.width() >= r.height()


def export_pdf(scene, model, path: str, opts: CleanOptions) -> None:
    w = QPdfWriter(path)
    w.setTitle(model.name)
    w.setCreator(f"{APP_NAME} {__version__}")
    w.setResolution(300)
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4),
                                QPageLayout.Landscape if _landscape(scene) else QPageLayout.Portrait,
                                QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter))
    p = QPainter(w)
    render(scene, model, p, QRectF(0, 0, w.width(), w.height()), opts)
    p.end()


def _content_size(scene, opts: CleanOptions, scale: float) -> tuple[QSizeF, float]:
    r = diagram_rect(scene)
    extra = (46 if opts.header else 0) * scale  # espaço do cabeçalho/rodapé (pontos × escala)
    return QSizeF(r.width() * scale, r.height() * scale + extra), extra


def export_png(scene, model, path: str, opts: CleanOptions, scale: float = 3.0) -> None:
    size, _ = _content_size(scene, opts, scale)
    img = QImage(int(size.width()), int(size.height()), QImage.Format_ARGB32)
    dpm = int(72 * scale / 0.0254)  # pontos tipográficos proporcionais à escala
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    img.fill(Qt.white)
    p = QPainter(img)
    render(scene, model, p, QRectF(0, 0, size.width(), size.height()), opts)
    p.end()
    img.save(path)


def export_svg(scene, model, path: str, opts: CleanOptions) -> None:
    size, _ = _content_size(scene, opts, 1.0)
    gen = QSvgGenerator()
    gen.setFileName(path)
    gen.setResolution(72)
    gen.setSize(size.toSize())
    gen.setViewBox(QRectF(0, 0, size.width(), size.height()))
    gen.setTitle(model.name)
    p = QPainter(gen)
    render(scene, model, p, QRectF(0, 0, size.width(), size.height()), opts)
    p.end()


EXPORTERS = {".pdf": export_pdf, ".png": export_png, ".svg": export_svg}


def export_clean(scene, model, path: str, opts: CleanOptions) -> None:
    ext = Path(path).suffix.lower()
    if ext not in EXPORTERS:
        raise ValueError(f"Formato não suportado: {ext}")
    EXPORTERS[ext](scene, model, path, opts)


def print_clean(scene, model, opts: CleanOptions, parent=None) -> None:
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName(model.name)
    printer.setPageOrientation(QPageLayout.Landscape if _landscape(scene) else QPageLayout.Portrait)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle(f"Imprimir — {model.name}")
    dlg.resize(1000, 760)

    def paint(pr: QPrinter):
        p = QPainter(pr)
        page = pr.pageLayout().paintRectPixels(pr.resolution())
        render(scene, model, p, QRectF(0, 0, page.width(), page.height()), opts)
        p.end()
    dlg.paintRequested.connect(paint)
    dlg.exec()
