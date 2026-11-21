"""Editor de distribuição: escolha no menu e preencha os parâmetros."""
from __future__ import annotations

import math

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QFormLayout, QLabel, QLayout, QLineEdit, QVBoxLayout,
                               QWidget)

from .. import distributions as dist

# parâmetros sem unidade (forma, probabilidades, contagens)
_UNITLESS = ("forma", "k (", "alfa", "beta", "probabilidade", "nº")


def _fmt_num(v: float) -> str:
    return f"{v:.6g}".replace(".", ",")


def _parse_num(text: str) -> float:
    return float(text.strip().replace(",", "."))


def _parse_list(text: str) -> list[float]:
    """Lista de números separados por espaço ou ';' (aceita vírgula decimal)."""
    parts = text.replace(";", " ").split()
    return [_parse_num(p) for p in parts]


def defaults(code: str, mean: float) -> list[float]:
    """Parâmetros iniciais coerentes com a média atual ao trocar de distribuição."""
    m = mean if mean and math.isfinite(mean) and mean > 0 else 1.0
    r = lambda v: float(f"{v:.4g}")  # noqa: E731
    return {
        "CONST": [r(m)], "EXPO": [r(m)], "NORM": [r(m), r(m * 0.1)],
        "TRIA": [r(m * 0.8), r(m), r(m * 1.2)], "UNIF": [r(m * 0.8), r(m * 1.2)],
        "LOGN": [r(m), r(m * 0.25)], "ERLA": [r(m), 2], "GAMM": [r(m), 2],
        "WEIB": [r(m / math.gamma(1.5)), 2], "LOGL": [r(m * math.sin(math.pi / 3) / (math.pi / 3)), 3],
        "BETA": [2, 2, r(m * 0.8), r(m * 1.2)], "DISC": [r(m), 1], "CONT": [r(m * 0.8), 0, r(m * 1.2), 1],
        "POIS": [r(m)], "BINO": [10, 0.5], "GEOM": [0.5], "NBIN": [2, 0.5], "DUNI": [1, 6],
    }[code]


class DistributionEditor(QWidget):
    """Menu de distribuições + campos de parâmetros. Emite ``changed(texto)`` quando válido."""
    changed = Signal(str)

    def __init__(self, text: str, for_time: bool = True, unit: str = "", parent=None):
        super().__init__(parent)
        self.for_time, self.unit = for_time, unit
        self.allow_negative = not for_time
        self.specs = dist.TIME_CATALOG if for_time else dist.CATALOG
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSizeConstraint(QLayout.SetMinimumSize)
        self.combo = QComboBox()
        for s in self.specs:
            self.combo.addItem(s.label, s.code)
        lay.addWidget(self.combo)
        self.form = QFormLayout()
        self.form.setContentsMargins(8, 0, 0, 0)
        lay.addLayout(self.form)
        self.error = QLabel()
        self.error.setStyleSheet("color:#b3261e")
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)
        self.fields: list[QLineEdit] = []
        self._last = ""
        try:
            d = dist.parse(text, self.allow_negative, for_time)
        except dist.DistributionError:
            d = dist.Distribution("CONST", (0.0,))
        self._set(d.name, list(d.args))
        self._last = self.text() or ""
        self.combo.currentIndexChanged.connect(self._kind_changed)

    # -------------------------------------------------------------- campos
    def code(self) -> str:
        return self.combo.currentData()

    def _label(self, name: str) -> str:
        if self.for_time and self.unit and not name.lower().startswith(_UNITLESS) \
                and "acumulad" not in name.lower():
            return f"{name} ({self.unit})"
        return name

    def _set(self, code: str, args: list[float]) -> None:
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(max(0, self.combo.findData(code)))
        self.combo.blockSignals(False)
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = []
        spec = dist.SPECS[code]
        if code in dist.PAIRED:
            values = [_fmt_num(v) for v in args[0::2]]
            probs = [_fmt_num(v) for v in args[1::2]]
            texts = ["  ".join(values), "  ".join(probs)]
        else:
            texts = [_fmt_num(v) for v in args]
        for name, t in zip(spec.params, texts):
            ed = QLineEdit(t)
            if code in dist.PAIRED:
                ed.setPlaceholderText("separe por espaço, ex.: 1  2  3")
                ed.setToolTip("Números separados por espaço ou ';' (vírgula decimal permitida).")
            ed.editingFinished.connect(self._emit)
            ed.textChanged.connect(lambda _=None: self._validate(show=False))
            self.form.addRow(self._label(name), ed)
            self.fields.append(ed)

    def _kind_changed(self, _i: int) -> None:
        try:
            mean = dist.parse(self._last, self.allow_negative).mean() if self._last else 1.0
        except dist.DistributionError:
            mean = 1.0
        self._set(self.code(), defaults(self.code(), mean))
        self._emit()

    # ------------------------------------------------------------ resultado
    def text(self) -> str | None:
        """Texto da distribuição (ex.: 'TRIA(3; 4,5; 6)') ou None se inválido."""
        code = self.code()
        try:
            if code in dist.PAIRED:
                vs, ps = (_parse_list(f.text()) for f in self.fields)
                if len(vs) != len(ps):
                    raise dist.DistributionError("Informe a mesma quantidade de valores e de "
                                                 "probabilidades.")
                args = [x for pair in zip(vs, ps) for x in pair]
            else:
                args = [_parse_num(f.text()) for f in self.fields]
        except ValueError:
            raise dist.DistributionError("Preencha todos os parâmetros com números.") from None
        t = dist.fmt(code, args)
        dist.parse(t, self.allow_negative, self.for_time)  # valida
        return t

    def _validate(self, show: bool = True) -> str | None:
        try:
            t = self.text()
        except dist.DistributionError as ex:
            for f in self.fields:
                f.setStyleSheet("background:#ffe3e0")
            if show:
                self.error.setText(str(ex))
                self.error.show()
            return None
        for f in self.fields:
            f.setStyleSheet("")
        self.error.hide()
        return t

    def _emit(self) -> None:
        t = self._validate()
        if t and t != self._last:
            self._last = t
            self.changed.emit(t)
