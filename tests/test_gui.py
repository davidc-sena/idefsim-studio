"""Testes da interface (executados em modo offscreen)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from idefsim.examples import montagem  # noqa: E402
from idefsim.gui.main_window import MainWindow  # noqa: E402
from idefsim.model import ConnectionKind as CK, ElementKind as EK  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _click(win, scene_pos):
    vp = win.view.viewport()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, win.view.mapFromScene(scene_pos))


def test_draw_with_mouse(app):
    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    win.view.resetTransform()
    win.view.centerOn(300, 0)
    sc = win.scene
    for kind, x in ((EK.ENTITY, 100), (EK.FUNCTION, 300), (EK.EXIT, 500)):
        sc.set_tool("add", kind)
        _click(win, QPoint(x, 0))
    m = sc.model
    assert len(m.elements) == 3
    ids = {e.kind: e.id for e in m.elements.values()}
    sc.set_tool("link", CK.FLOW)
    for a, b in ((100, 300), (300, 500)):
        _click(win, QPoint(a, 0))
        _click(win, QPoint(b, 0))
    assert len(m.connections) == 2
    assert m.outgoing(ids[EK.ENTITY])[0].target == ids[EK.FUNCTION]
    n_hist = len(win.history)
    win.undo()
    assert len(win.scene.model.connections) == 1
    win.redo()
    assert len(win.scene.model.connections) == 2
    assert len(win.history) == n_hist
    win.dirty = False
    win.close()


def test_load_example_and_export(app, tmp_path):
    win = MainWindow()
    win._set_model(montagem(), None)
    assert win.svg_bytes().startswith(b"<?xml")
    assert not win.image().isNull()
    win.close()


def test_arrowhead_visible_when_rule_touches_function(app):
    from idefsim.model import Model
    m = Model()
    f = m.add_element(EK.FUNCTION, 0, 0)
    r = m.add_element(EK.RULE_OR, 80, 0)   # regra sobreposta à função
    m.add_connection(CK.FLOW, f.id, r.id)
    win = MainWindow()
    win._set_model(m, None)
    ed = next(iter(win.scene.edges.values()))
    a, b = ed.points
    assert b.x() - a.x() >= 14 and ed.zValue() > win.scene.nodes[f.id].zValue()
    win.dirty = False
    win.close()


def test_entry_tool_sets_side(app):
    from PySide6.QtCore import QPointF
    from idefsim.model import Model
    m = Model()
    e = m.add_element(EK.ENTITY, 0, 0)
    e.params["external_arrival"] = False
    win = MainWindow()
    win._set_model(m, None)
    assert win.scene.set_entry_arrow(e.id, QPointF(0, -20))   # clique acima
    p = win.scene.model.elements[e.id].params
    assert p["external_arrival"] and p["arrival_side"] == "top"
    win.undo()
    assert not win.scene.model.elements[e.id].params["external_arrival"]
    win.dirty = False
    win.close()


def test_splash_and_about(app):
    from idefsim import AUTHOR, EMAIL, INSTITUTION
    from idefsim.gui import branding
    assert branding.load_fonts()
    pm = branding.splash_pixmap(1)
    assert pm.width() == branding.SPLASH_W and not pm.isNull()
    assert (AUTHOR, INSTITUTION, EMAIL) == ("Prof. David Custódio de Sena", "UFERSA",
                                            "sena@ufersa.edu.br")
    dlg = branding.AboutDialog()
    assert dlg.width() > branding.SPLASH_W
    dlg.close()


def test_export_jaamsim_from_gui(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from idefsim.examples import usinagem_inspecao
    win = MainWindow()
    win._set_model(usinagem_inspecao(), None)
    out = tmp_path / "modelo"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win.export_jaamsim()
    text = (tmp_path / "modelo.cfg").read_text(encoding="ascii")
    assert "Define EntityGenerator { Peca_Chegada }" in text
    win.dirty = False
    win.close()


def test_arrow_heads_from_properties(app):
    from PySide6.QtWidgets import QComboBox
    from idefsim.examples import usinagem_inspecao
    win = MainWindow()
    win._set_model(usinagem_inspecao(), None)
    cid = next(c.id for c in win.scene.model.connections.values() if c.kind == CK.CONTROL)
    win.scene.clearSelection()
    win.scene.edges[cid].setSelected(True)
    boxes = win.props.widget().findChildren(QComboBox)
    assert len(boxes) == 2 and [b.currentText() for b in boxes] == ["Sem ponta", "Com ponta"]
    boxes[1].setCurrentIndex(0)                       # fim: sem ponta
    assert win.scene.model.connections[cid].heads == (False, False)
    win.undo()
    assert win.scene.model.connections[cid].heads == (False, True)
    win.dirty = False
    win.close()


def test_clean_export_and_print(app, tmp_path):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter
    from PySide6.QtPrintSupport import QPrinter
    from idefsim.examples import usinagem_inspecao
    from idefsim.gui import printing, shapes
    win = MainWindow()
    win._set_model(usinagem_inspecao(), None)
    win.scene.select_element(next(iter(win.scene.model.elements)))
    opts = printing.CleanOptions()
    for ext in ("pdf", "png", "svg"):
        out = tmp_path / f"limpo.{ext}"
        printing.export_clean(win.scene, win.scene.model, str(out), opts)
        assert out.stat().st_size > 1000
    assert (tmp_path / "limpo.pdf").read_bytes().startswith(b"%PDF")
    # impressão: renderiza numa impressora em modo PDF (sem diálogo)
    pr = QPrinter(QPrinter.HighResolution)
    pr.setOutputFormat(QPrinter.PdfFormat)
    pr.setOutputFileName(str(tmp_path / "impresso.pdf"))
    p = QPainter(pr)
    page = pr.pageLayout().paintRectPixels(pr.resolution())
    printing.render(win.scene, win.scene.model, p, QRectF(0, 0, page.width(), page.height()), opts)
    p.end()
    assert (tmp_path / "impresso.pdf").stat().st_size > 1000
    # o editor volta ao estado normal: cores, grade e seleção
    assert shapes.STYLE == {"mono": False, "edge_labels": True}
    assert win.scene.show_grid and len(win.scene.selectedItems()) == 1
    win.dirty = False
    win.close()


def test_distribution_editor(app):
    from idefsim.gui.dist_editor import DistributionEditor
    got = []
    ed = DistributionEditor("TRIA(3; 4,5; 6)", for_time=True, unit="min")
    ed.changed.connect(got.append)
    assert ed.code() == "TRIA" and [f.text() for f in ed.fields] == ["3", "4,5", "6"]
    ed.combo.setCurrentIndex(ed.combo.findData("CONST"))     # CONSTANTE: só o valor médio
    assert len(ed.fields) == 1 and got[-1] == "CONST(4,5)"
    ed.combo.setCurrentIndex(ed.combo.findData("GAMM"))
    assert got[-1] == "GAMM(4,5; 2)"
    assert ed.combo.findData("POIS") == -1                    # contagem fora dos tempos
    assert DistributionEditor("0", for_time=False).combo.findData("POIS") >= 0
