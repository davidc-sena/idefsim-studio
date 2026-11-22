"""Gera o manual de uso (docs/manual/): capturas de tela do próprio programa, resultados reais
da simulação do exemplo completo, manual.html e Manual_IDEF-SIM_Studio.pdf.

Uso:  python packaging/build_manual.py          (requer Node + Playwright para o PDF)
"""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "manual"
IMG = OUT / "img"

from PySide6.QtCore import QLibraryInfo, QLocale, QPoint, QTranslator  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QMenu, QToolBar  # noqa: E402

QLocale.setDefault(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
app = QApplication([])
app.setStyle("Fusion")
_tr = QTranslator(app)
_tr.load("qtbase_pt_BR", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
app.installTranslator(_tr)

from idefsim import APP_NAME, AUTHOR, EMAIL, INSTITUTION, __version__  # noqa: E402
from idefsim.examples import oficina_bombas  # noqa: E402
from idefsim.gui import branding, printing  # noqa: E402
from idefsim.gui.dialogs import LegendDialog, ResultsDialog  # noqa: E402
from idefsim.gui.main_window import MainWindow  # noqa: E402
from idefsim.jaamsim_export import export_jaamsim  # noqa: E402
from idefsim.model import ConnectionKind as CK  # noqa: E402
from idefsim.simulation import run_simulation  # noqa: E402

branding.load_fonts()


def settle(n: int = 3) -> None:
    for _ in range(n):
        app.processEvents()


def shots() -> dict:
    """Capturas de tela; devolve dados usados no texto (resultados, trecho do .cfg...)."""
    IMG.mkdir(parents=True, exist_ok=True)
    branding.splash_pixmap(2, status=None).save(str(IMG / "abertura.png"))
    w = MainWindow()
    w.resize(1500, 900)
    w.show()
    model = oficina_bombas()
    w._set_model(model, None)
    w.fit()
    settle()
    w.grab().save(str(IMG / "janela.png"))
    w.image(1.6).save(str(IMG / "exemplo_diagrama.png"))
    pal = next(t for t in w.findChildren(QToolBar) if t.objectName() == "palette")
    pal.grab().save(str(IMG / "paleta.png"))
    by = {e.name: e for e in model.elements.values()}

    def props(element_name: str, file: str, height: int = 640) -> None:
        w.scene.select_element(by[element_name].id)
        settle()
        g = w.props.grab()
        g.copy(0, 0, g.width(), min(g.height(), height)).save(str(IMG / file))

    props("Bomba com defeito", "prop_entidade.png", 820)
    props("Inspecionar", "prop_funcao.png", 300)
    props("Aguardar inspeção", "prop_fila.png", 220)
    props("Aguardar kit", "prop_fila_juncao.png", 230)
    props("Técnico", "prop_recurso.png", 200)
    ou = next(e for e in model.elements.values()
              if e.kind.value == "rule_or" and e.params.get("decision") == "condition")
    w.scene.select_element(ou.id)
    settle()
    w.props.grab().copy(0, 0, w.props.width(), 330).save(str(IMG / "prop_ou_condicao.png"))
    vis = next(e for e in model.elements.values() if e.params.get("decision") == "visual")
    w.scene.select_element(vis.id)
    settle()
    w.props.grab().copy(0, 0, w.props.width(), 300).save(str(IMG / "prop_ou_visual.png"))
    # seta: ligação da nota (com ponta escolhida)
    cnx = next(c for c in model.connections.values() if c.kind == CK.NOTE)
    w.scene.clearSelection()
    w.scene.edges[cnx.id].setSelected(True)
    settle()
    w.props.grab().copy(0, 0, w.props.width(), 230).save(str(IMG / "prop_seta.png"))
    # editor de distribuição com o menu aberto
    w.scene.select_element(by["Inspecionar"].id)
    settle()
    combo = next(c for c in w.props.widget().findChildren(QComboBox) if c.count() > 10)
    combo.showPopup()
    settle()
    view = combo.view().window()
    view.grab().save(str(IMG / "menu_distribuicoes.png"))
    combo.hidePopup()
    # validação
    w.scene.clearSelection()
    w.validate()
    settle()
    w.issue_dock.grab().copy(0, 0, 900, 70).save(str(IMG / "validacao.png"))
    # resultados (simulação completa do exemplo)
    result = run_simulation(model)
    dlg = ResultsDialog(result, w)
    dlg.resize(980, 600)
    dlg.show()
    settle()
    dlg.grab().save(str(IMG / "resultados.png"))
    dlg.close()
    # saída limpa e opções
    od = printing.CleanOptionsDialog("Exportar diagrama limpo", printing.CleanOptions(), w)
    od.show()
    settle()
    od.grab().save(str(IMG / "opcoes_limpo.png"))
    od.close()
    printing.export_png(w.scene, model, str(IMG / "exemplo_limpo.png"), printing.CleanOptions(), 1.6)
    # legenda e menus
    lg = LegendDialog(w)
    lg.resize(760, 760)
    lg.show()
    settle()
    lg.grab().save(str(IMG / "legenda.png"))
    lg.close()
    menu = next(m for m in w.findChildren(QMenu) if m.title() == "&Arquivo")
    menu.popup(w.mapToGlobal(QPoint(10, 25)))
    settle()
    menu.grab().save(str(IMG / "menu_arquivo.png"))
    menu.close()
    w.dirty = False
    w.close()
    return {"result": result, "cfg": export_jaamsim(model).text, "model": model}


# --------------------------------------------------------------------------- HTML
def results_table(result) -> str:
    keep = {("Sistema", "Entidades que saíram"), ("Sistema", "Tempo médio no sistema"),
            ("Sistema", "WIP médio"), ("Fila", "Tempo médio em fila"), ("Fila", "Fila máxima"),
            ("Recurso", "Utilização (%)"), ("Entidade", "Saídas")}
    rows = []
    for r in result.rows():
        if (r.category, r.metric) in keep and not (r.metric == "Saídas" and r.mean == 0):
            rows.append(f"<tr><td>{html.escape(r.category)}</td><td>{html.escape(r.obj)}</td>"
                        f"<td>{html.escape(r.metric)}</td><td class=n>{r.mean:,.2f}</td>"
                        f"<td class=n>± {r.half_width:,.2f}</td></tr>".replace(",", "X")
                        .replace(".", ",").replace("X", "."))
    return ("<table><thead><tr><th>Categoria</th><th>Objeto</th><th>Indicador</th>"
            "<th>Média</th><th>IC 95%</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def cfg_excerpt(cfg: str) -> str:
    want = ("Aguardar_insp", "Inspecionar ", "Regra_OU_Branch", "Regra_E_Montagem",
            "Bomba_com_defeito_Atributos", "Bomba_com_defeito AttributeDefinitionList")
    lines = [ln for ln in cfg.splitlines() if ln.startswith(want) and "Position" not in ln]
    return html.escape("\n".join(lines[:16]))


def build_html(data: dict) -> str:
    tpl = (ROOT / "packaging" / "manual_template.html").read_text(encoding="utf-8")
    m = data["model"]
    s = m.settings
    subs = {
        "{{APP}}": APP_NAME, "{{VERSAO}}": __version__, "{{AUTOR}}": AUTHOR,
        "{{INSTITUICAO}}": INSTITUTION, "{{EMAIL}}": EMAIL,
        "{{RESULTADOS}}": results_table(data["result"]),
        "{{CFG}}": cfg_excerpt(data["cfg"]),
        "{{SIM}}": (f"{s.duration:g} {s.time_unit} de simulação, aquecimento de {s.warmup:g} "
                    f"{s.time_unit} e {s.replications} replicações"),
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)
    return tpl


def build_pdf(html_path: Path, pdf_path: Path) -> None:
    js = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://{html_path.as_posix()}', {{ waitUntil: 'networkidle' }});
  await p.pdf({{ path: '{pdf_path.as_posix()}', format: 'A4', printBackground: true,
    margin: {{ top: '18mm', bottom: '18mm', left: '16mm', right: '16mm' }},
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#777">' +
      '{APP_NAME} {__version__} — Manual de uso — <span class=pageNumber></span>/' +
      '<span class=totalPages></span></div>' }});
  await b.close();
}})();
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
    try:
        subprocess.run(["node", f.name], check=True)
    finally:
        os.unlink(f.name)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    data = shots()
    (OUT / "manual.html").write_text(build_html(data), encoding="utf-8")
    # as fontes vêm de idefsim/resources/fonts (mesmo caminho relativo no executável)
    if "--sem-pdf" not in sys.argv:
        build_pdf(OUT / "manual.html", OUT / "Manual_IDEF-SIM_Studio.pdf")
    print("manual gerado em", OUT)


if __name__ == "__main__":
    main()
