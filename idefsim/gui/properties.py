"""Painel de propriedades do modelo, elemento ou ligação selecionada."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import expressions as expr
from . import shapes
from ..model import (CONNECTION_LABELS, DECISION_LABELS, KIND_LABELS, Connection,
                     ConnectionKind as CK, Element, ElementKind as EK, Model, PROCESS_KINDS)
from .dist_editor import DistributionEditor

COND_HELP = ("Condição sobre atributos da entidade, ex.: tipo == 1 · peso > 10 e tipo != 3 · "
             "prioridade >= 2 ou urgente == 1. Escreva 'senão' na saída padrão.")


class _TextEdit(QPlainTextEdit):
    editingFinished = Signal()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.editingFinished.emit()


class PropertiesPanel(QScrollArea):
    edited = Signal(str, str)        # descrição, chave de agrupamento
    elementRenamed = Signal(str)     # id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(280)
        self.model: Model | None = None
        self._clear()

    def _clear(self) -> QFormLayout:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:bold;font-size:11pt;padding:4px 0")
        lay.addWidget(self.title)
        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        lay.addLayout(self.form)
        lay.addStretch(1)
        self.setWidget(w)
        return self.form

    # --------------------------------------------------------------- helpers
    def _line(self, label, value, apply, tip="", validator=None):
        ed = QLineEdit(str(value))
        ed.setToolTip(tip)

        def check():
            ok = validator is None or validator(ed.text())
            ed.setStyleSheet("" if ok else "background:#ffd9d9")
            return ok

        def done():
            if check() and ed.text() != str(value_holder[0]):
                value_holder[0] = ed.text()
                apply(ed.text())
        value_holder = [value]
        ed.textChanged.connect(lambda _: check())
        ed.editingFinished.connect(done)
        check()
        self.form.addRow(label, ed)
        return ed

    def _spin(self, label, value, apply, lo=0, hi=10**9, tip=""):
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(int(value))
        sp.setToolTip(tip)
        sp.valueChanged.connect(apply)
        self.form.addRow(label, sp)
        return sp

    def _dspin(self, label, value, apply, lo=0.0, hi=1e9, step=1.0, dec=2):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(dec)
        sp.setSingleStep(step)
        sp.setValue(float(value))
        sp.valueChanged.connect(apply)
        self.form.addRow(label, sp)
        return sp

    def _dist(self, label, value, apply, for_time=True):
        """Menu de distribuições + campos dos parâmetros."""
        unit = self.model.settings.time_unit if (for_time and self.model) else ""
        ed = DistributionEditor(value, for_time=for_time, unit=unit)
        ed.changed.connect(apply)
        self.form.addRow(label, ed)
        return ed

    def _rebuild_later(self, model, e):
        QTimer.singleShot(0, lambda: self.show_element(model, e))

    def _text(self, label, value, apply):
        ed = _TextEdit(value)
        ed.setFixedHeight(80)
        ed.editingFinished.connect(lambda: ed.toPlainText() != value and apply(ed.toPlainText()))
        self.form.addRow(label, ed)
        return ed

    # ------------------------------------------------------------------ modelo
    def show_model(self, model: Model) -> None:
        self.model = model
        self._clear()
        self.title.setText("Modelo")
        s = model.settings

        def setter(obj, attr, desc, conv=lambda v: v):
            def f(v):
                setattr(obj, attr, conv(v))
                self.edited.emit(desc, f"model.{attr}")
            return f

        self._line("Nome", model.name, setter(model, "name", "Nome do modelo"))
        self._line("Autor", model.author, setter(model, "author", "Autor"))
        self._line("Versão", model.version, setter(model, "version", "Versão"))
        self._text("Descrição", model.description, setter(model, "description", "Descrição"))
        sep = QLabel("<b>Simulação</b>")
        self.form.addRow(sep)
        unit = QComboBox()
        unit.setEditable(True)
        unit.addItems(["s", "min", "h", "dia"])
        unit.setCurrentText(s.time_unit)
        unit.currentTextChanged.connect(setter(s, "time_unit", "Unidade de tempo"))
        self.form.addRow("Unidade de tempo", unit)
        self._dspin("Duração", s.duration, setter(s, "duration", "Duração"), 0.01, 1e9, 60)
        self._dspin("Aquecimento", s.warmup, setter(s, "warmup", "Aquecimento"), 0, 1e9, 10)
        self._spin("Replicações", s.replications, setter(s, "replications", "Replicações"), 1, 1000)
        self._spin("Semente", s.seed, setter(s, "seed", "Semente"), 0, 2**31 - 1)
        n_el = len(model.elements)
        self.form.addRow(QLabel(f"<i>{n_el} elementos, {len(model.connections)} ligações.<br>"
                                "Selecione um elemento para editar suas propriedades.</i>"))

    # ---------------------------------------------------------------- elemento
    def show_element(self, model: Model, e: Element) -> None:
        self.model = model
        self._clear()
        self.title.setText(KIND_LABELS[e.kind])

        def set_name(v):
            e.name = v.strip() or e.name
            self.elementRenamed.emit(e.id)
            self.edited.emit("Renomear", f"{e.id}.name")

        def set_param(key, desc, conv=lambda v: v):
            def f(v):
                e.params[key] = conv(v)
                self.elementRenamed.emit(e.id)
                self.edited.emit(desc, f"{e.id}.{key}")
            return f

        def set_desc(v):
            e.description = v
            self.elementRenamed.emit(e.id)
            self.edited.emit("Descrição", f"{e.id}.description")

        if e.kind not in (EK.RULE_AND, EK.RULE_OR, EK.RULE_ANDOR):
            self._line("Nome", e.name, set_name,
                       "Conectores com o mesmo nome se conectam entre si." if e.kind == EK.CONNECTOR else "")
        else:
            help_ = QLabel(self._rule_help(e.kind))
            help_.setWordWrap(True)
            self.form.addRow(help_)

        if e.kind == EK.ENTITY:
            ext = QCheckBox("Fluxo de entrada no sistema")
            ext.setToolTip("Seta com dois traços antes da entidade: ela chega de fora do sistema.")
            ext.setChecked(bool(e.params.get("external_arrival")))
            ext.toggled.connect(set_param("external_arrival", "Fluxo de entrada", bool))
            self.form.addRow("Chegada externa", ext)
            side = QComboBox()
            sides = list(shapes.SIDE_LABELS)
            side.addItems([shapes.SIDE_LABELS[k] for k in sides])
            side.setCurrentIndex(sides.index(e.params.get("arrival_side", "left")))
            side.setEnabled(ext.isChecked())
            ext.toggled.connect(side.setEnabled)
            side.currentIndexChanged.connect(
                lambda i: set_param("arrival_side", "Lado da chegada")(sides[i]))
            self.form.addRow("Seta vem da", side)
            if model.incoming(e.id):
                self.form.addRow(QLabel("<i>Entidade de transformação: as entidades que chegam "
                                        "passam a ser deste tipo.</i>"))
            else:
                self._dist("Intervalo entre chegadas", e.params.get("interarrival", ""),
                           set_param("interarrival", "Intervalo entre chegadas"))
                self._dist("Primeira chegada", e.params.get("first_arrival", "0"),
                           set_param("first_arrival", "Primeira chegada"))
                self._spin("Entidades por chegada", e.params.get("batch_size", 1),
                           set_param("batch_size", "Lote"), 1, 10**6)
                self._spin("Máx. de chegadas", e.params.get("max_arrivals", 0),
                           set_param("max_arrivals", "Máx. chegadas"), 0, 10**9, "0 = ilimitado")
            self._attributes(model, e)
        elif e.kind in PROCESS_KINDS:
            self._dist("Tempo" + (" de processamento" if e.kind == EK.FUNCTION else " de deslocamento"),
                       e.params.get("duration", ""), set_param("duration", "Tempo"))
            res = model.resources_of(e.id)
            self.form.addRow("Recursos", QLabel(", ".join(r.name for r in res) or
                                                "<i>nenhum (capacidade infinita)</i>"))
            ctrls = [model.elements[c.source].name for c in model.incoming(e.id, CK.CONTROL)]
            if ctrls:
                self.form.addRow("Controles", QLabel(", ".join(ctrls)))
        elif e.kind == EK.RESOURCE:
            self._spin("Capacidade", e.params.get("capacity", 1),
                       set_param("capacity", "Capacidade", int), 1, 10**6)
            used = [model.elements[c.target].name for c in model.outgoing(e.id, CK.RESOURCE)]
            self.form.addRow("Usado em", QLabel(", ".join(used) or "<i>—</i>"))

        if e.kind == EK.RULE_OR:
            box = QComboBox()
            keys = list(DECISION_LABELS)
            box.addItems([DECISION_LABELS[k] for k in keys])
            box.setCurrentIndex(keys.index(model.decision_of(e.id)))

            def set_decision(i):
                e.params["decision"] = keys[i]
                self.elementRenamed.emit(e.id)
                self.edited.emit("Tipo de decisão", f"{e.id}.decision")
                self._rebuild_later(model, e)
            box.currentIndexChanged.connect(set_decision)
            self.form.addRow("Decisão", box)
            if model.decision_of(e.id) == "visual":
                crit = self._line("Critério", e.params.get("criterion", ""),
                                  set_param("criterion", "Critério"),
                                  "Texto mostrado no diagrama, ex.: menor fila, turno, prioridade.")
                crit.setPlaceholderText("ex.: menor fila")
                self.form.addRow(QLabel("<i>Apenas documenta a decisão: na simulação as saídas "
                                        "são sorteadas com chances iguais.</i>"))

        self._text("Descrição", e.description, set_desc)
        outs = model.outgoing(e.id)
        decision = model.decision_of(e.id)
        if len(outs) > 1 and decision != "visual":
            self.form.addRow(QLabel("<b>Saídas</b>"))
            for c in outs:
                name = model.elements[c.target].name
                if decision == "condition":
                    self._cond_row(model, c, f"→ {name}")
                else:
                    self._prob_row(model, c, name)

    # ------------------------------------------------------------ atributos
    def _attributes(self, model, e) -> None:
        attrs = e.params.setdefault("attributes", [])
        self.form.addRow(QLabel("<b>Atributos</b>"))
        if not attrs:
            self.form.addRow(QLabel("<i>Nenhum. Atributos são sorteados quando a entidade chega "
                                    "(ou se transforma) e podem ser usados na regra OU.</i>"))
        for i, a in enumerate(attrs):
            top = QWidget()
            row = QHBoxLayout(top)
            row.setContentsMargins(0, 0, 0, 0)
            name = QLineEdit(a.get("name", ""))
            name.setPlaceholderText("nome, ex.: tipo")
            name.setToolTip("Letras sem acento, números e _ , começando por letra.")
            rm = QPushButton("Remover")
            row.addWidget(name, 1)
            row.addWidget(rm)
            ed = DistributionEditor(a.get("value", "0"), for_time=False)

            def check(text, w=name):
                w.setStyleSheet("" if expr.valid_attribute_name(text.strip()) else "background:#ffe3e0")

            def set_name(a=a, w=name):
                v = w.text().strip()
                if v != a.get("name"):
                    a["name"] = v
                    self.edited.emit("Nome do atributo", f"{e.id}.attr.{id(a)}")

            def set_value(t, a=a):
                a["value"] = t
                self.edited.emit("Valor do atributo", f"{e.id}.attrv.{id(a)}")

            def remove(_=False, i=i):
                del attrs[i]
                self.edited.emit("Remover atributo", "")
                self._rebuild_later(model, e)
            name.textChanged.connect(check)
            check(name.text())
            name.editingFinished.connect(set_name)
            ed.changed.connect(set_value)
            rm.clicked.connect(remove)
            self.form.addRow(f"Atributo {i + 1}", top)
            self.form.addRow("Valor", ed)
        add = QPushButton("+ Adicionar atributo")

        def add_attr():
            used = {x.get("name") for x in attrs}
            n = 1
            while f"atributo{n}" in used:
                n += 1
            attrs.append({"name": f"atributo{n}", "value": "0"})
            self.edited.emit("Adicionar atributo", "")
            self._rebuild_later(model, e)
        add.clicked.connect(add_attr)
        self.form.addRow(add)

    def _cond_row(self, model, c: Connection, label: str):
        known = model.attribute_names()

        def check(text):
            t = text.strip()
            ok = not t or expr.is_default(t)
            if not ok:
                try:
                    expr.parse(t)
                    ok = True
                except expr.ExpressionError:
                    ok = False
            return ok

        def apply(v, c=c):
            c.condition = v.strip()
            self.elementRenamed.emit(c.source)
            self.edited.emit("Condição", f"{c.id}.cond")
        tip = COND_HELP + ("\nAtributos definidos: " + ", ".join(known) if known else
                           "\nAinda não há atributos nas entidades.")
        ed = self._line(label, c.condition, apply, tip, check)
        ed.setPlaceholderText("ex.: tipo == 1   (ou 'senão')")
        return ed

    @staticmethod
    def _rule_help(kind: EK) -> str:
        return {
            EK.RULE_AND: "<b>&amp; (E)</b>: com várias entradas aguarda uma entidade de cada "
                         "ramo (junção/montagem); com várias saídas segue todos os ramos.",
            EK.RULE_OR: "<b>X (OU)</b>: a entidade segue apenas uma das saídas, escolhida por "
                        "probabilidade, por condição sobre seus atributos ou, no modo "
                        "apenas visual, sem regra simulada.",
            EK.RULE_ANDOR: "<b>O (E/OU)</b>: cada saída é seguida de forma independente "
                           "com sua probabilidade.",
        }[kind]

    def _prob_row(self, model, c: Connection, name: str):
        def f(v, c=c):
            c.probability = v / 100
            self.elementRenamed.emit(c.source)
            self.edited.emit("Probabilidade", f"{c.id}.p")
        self._dspin(f"→ {name} (%)", c.probability * 100, f, 0, 100, 5, 2)

    # ----------------------------------------------------------------- ligação
    def show_connection(self, model: Model, c: Connection) -> None:
        self.model = model
        self._clear()
        self.title.setText(CONNECTION_LABELS[c.kind])
        s, t = model.elements[c.source], model.elements[c.target]
        self.form.addRow("De", QLabel(s.name))
        self.form.addRow("Para", QLabel(t.name))

        def set_label(v):
            c.label = v
            self.elementRenamed.emit(c.source)
            self.edited.emit("Rótulo", f"{c.id}.label")
        self._line("Rótulo", c.label, set_label)

        # pontas da seta: escolhidas para cada ligação
        start, end = c.heads
        for label, attr, value in (("Início", "head_start", start), ("Fim", "head_end", end)):
            box = QComboBox()
            box.addItems(["Sem ponta", "Com ponta"])
            box.setCurrentIndex(1 if value else 0)

            def apply(i, attr=attr):
                setattr(c, attr, bool(i))
                self.elementRenamed.emit(c.source)
                self.edited.emit("Pontas da seta", f"{c.id}.{attr}")
            box.currentIndexChanged.connect(apply)
            self.form.addRow(f"{label} da seta", box)
        decision = model.decision_of(s.id)
        if c.kind == CK.FLOW and s.kind == EK.RULE_OR and decision == "condition":
            self._cond_row(model, c, "Condição")
        elif c.kind == CK.FLOW and s.kind == EK.RULE_OR and decision == "visual":
            pass
        elif c.kind == CK.FLOW and len(model.outgoing(c.source)) > 1 or s.kind == EK.RULE_ANDOR:
            self._prob_row(model, c, "probabilidade")
