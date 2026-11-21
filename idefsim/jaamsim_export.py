"""Gera um modelo básico do JaamSim (.cfg) a partir de um modelo IDEF-SIM.

Correspondência entre os elementos (sintaxe conferida no código-fonte e nos exemplos
oficiais do JaamSim):

=================================  ==================================================
IDEF-SIM                           JaamSim
=================================  ==================================================
Entidade com chegada externa       SimEntity + EntityGenerator
Entidade de transformação          Queue + Assemble (cria a nova entidade)
Função com recursos                Queue + Seize → EntityDelay → Release
Função sem recursos                EntityDelay (capacidade infinita)
Movimentação                       EntityConveyor (com Seize/Release se tiver recurso)
Recurso                            Resource (Capacity)
Regra OU (X)                       Branch + DiscreteDistribution
Regra E (&) – divisão              Duplicate
Regra E (&) – junção               Queue por ramo + Combine
Regra E (&) – junção → Entidade    Queue por ramo + Assemble (montagem)
Regra E/OU (O)                     Duplicate + Branch por ramo (segue ou descarta)
Ponto final                        EntitySink
Conexão                            ligação direta ao conector de mesmo nome
Controle / Informação explicativa  Text (documentação no modelo)
=================================  ==================================================
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

from . import APP_NAME, AUTHOR, EMAIL, INSTITUTION, __version__
from . import distributions as dist
from .model import ConnectionKind as CK, ElementKind as EK, Model, PROCESS_KINDS

UNIT_MAP = {"s": "s", "seg": "s", "segundo": "s", "segundos": "s",
            "min": "min", "minuto": "min", "minutos": "min",
            "h": "h", "hora": "h", "horas": "h",
            "d": "d", "dia": "d", "dias": "d"}
SCALE = 1 / 60.0  # pixels do diagrama → metros no JaamSim
_INVALID = re.compile(r"[^A-Za-z0-9_\-]+")


def jaamsim_name(text: str) -> str:
    """Nome válido no JaamSim (sem espaços, pontos, colchetes, chaves, aspas ou #)."""
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    name = _INVALID.sub("_", ascii_).strip("_") or "Objeto"
    if name[0].isdigit():
        name = "N" + name
    return name


def ascii_text(text: str) -> str:
    """O JaamSim lê o .cfg com a codificação padrão do sistema: o arquivo sai em ASCII puro."""
    text = text.replace("—", "-").replace("–", "-").replace("’", "'").replace("…", "...")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _q(text: str) -> str:
    """Texto entre aspas simples (o JaamSim não aceita aspas dentro do texto)."""
    return "'" + text.replace("'", "`").replace("\n", " ") + "'"


def _num(v: float) -> str:
    return f"{v:.6g}"


@dataclass
class ExportResult:
    text: str
    warnings: list[str] = field(default_factory=list)
    object_count: int = 0


class _Exporter:
    def __init__(self, model: Model):
        self.m = model
        self.warnings: list[str] = []
        tu = model.settings.time_unit.strip().lower()
        self.unit = UNIT_MAP.get(tu)
        if self.unit is None:
            self.unit = "min"
            self.warnings.append(f"Unidade de tempo '{model.settings.time_unit}' não reconhecida; "
                                 "foi usada 'min'.")
        self.defs: dict[str, list[str]] = {}       # tipo → nomes (ordem de definição)
        self.early: list[str] = []                  # UnitType: logo após os Define
        self.lines: dict[str, list[str]] = {}      # tipo → linhas de palavras-chave
        self.graphics: list[str] = []
        self.used: set[str] = set()
        self.seed = 0
        self.positions: list[tuple[float, float]] = []
        # nomes JaamSim por elemento
        rule_names = {EK.RULE_AND: "Regra_E", EK.RULE_OR: "Regra_OU", EK.RULE_ANDOR: "Regra_EOU"}
        self.names = {e.id: self.unique(rule_names.get(e.kind) or jaamsim_name(e.name))
                      for e in model.elements.values()}

    # ----------------------------------------------------------- utilidades
    def unique(self, base: str) -> str:
        name, i = base, 2
        while name in self.used:
            name = f"{base}_{i}"
            i += 1
        self.used.add(name)
        return name

    def define(self, kind: str, name: str) -> str:
        self.defs.setdefault(kind, []).append(name)
        return name

    def kw(self, kind: str, obj: str, keyword: str, value: str) -> None:
        if keyword == "UnitType":
            self.early.append(f"{obj} UnitType {{ {value} }}")
            return
        self.lines.setdefault(kind, []).append(f"{obj} {keyword} {{ {value} }}")

    def pos(self, obj: str, x: float, y: float) -> None:
        X, Y = x * SCALE, -y * SCALE
        self.positions.append((X, Y))
        self.graphics.append(f"{obj} Position {{ {_num(X)}  {_num(Y)}  0.0  m }}")

    def points(self, obj: str, x1: float, y1: float, x2: float, y2: float) -> None:
        a, b = (x1 * SCALE, -y1 * SCALE), (x2 * SCALE, -y2 * SCALE)
        self.positions += [a, b]
        self.graphics.append(f"{obj} Points {{ {{ {_num(a[0])}  {_num(a[1])}  0.0  m }} "
                             f"{{ {_num(b[0])}  {_num(b[1])}  0.0  m }} }}")

    def next_seed(self) -> int:
        self.seed += 1
        return self.seed

    def time_value(self, text: str, owner: str, x: float, y: float) -> str:
        """Converte uma expressão de distribuição em valor ou objeto de distribuição do JaamSim."""
        try:
            d = dist.parse(text)
        except dist.DistributionError as ex:
            self.warnings.append(f"{owner}: distribuição inválida ({ex}); usado 0.")
            return f"0  {self.unit}"
        u, a = self.unit, d.args
        if d.name == "CONST":
            return f"{_num(a[0])}  {u}"
        t = lambda v: f"{_num(v)}  {u}"  # noqa: E731  valor com unidade de tempo
        if d.name == "EXPO":
            cls, kws = "ExponentialDistribution", [("Mean", t(a[0]))]
        elif d.name == "NORM":  # truncada em zero, como no IDEF-SIM Studio
            cls, kws = "NormalDistribution", [("Mean", t(a[0])), ("StandardDeviation", t(a[1])),
                                              ("MinValue", t(0))]
        elif d.name == "TRIA":
            cls, kws = "TriangularDistribution", [("MinValue", t(a[0])), ("Mode", t(a[1])),
                                                  ("MaxValue", t(a[2]))]
        elif d.name == "UNIF":
            cls, kws = "UniformDistribution", [("MinValue", t(a[0])), ("MaxValue", t(a[1]))]
        elif d.name == "ERLA":
            cls, kws = "ErlangDistribution", [("Mean", t(a[0])), ("Shape", str(int(a[1])))]
        elif d.name == "WEIB":
            cls, kws = "WeibullDistribution", [("Scale", t(a[0])), ("Shape", _num(a[1]))]
        else:  # LOGN
            # JaamSim usa os parâmetros da normal subjacente: amostra = Scale·exp(N(μ, σ))
            mean, sd = a
            s2 = math.log(1 + (sd * sd) / (mean * mean))
            cls, kws = "LogNormalDistribution", [("Scale", f"1  {u}"),
                                                 ("NormalMean", _num(math.log(mean) - s2 / 2)),
                                                 ("NormalStandardDeviation", _num(math.sqrt(s2)))]
        name = self.define(cls, self.unique(f"{owner}_Tempo"))
        self.kw(cls, name, "UnitType", "TimeUnit")
        self.kw(cls, name, "RandomSeed", str(self.next_seed()))
        for k, v in kws:
            self.kw(cls, name, k, v)
        self.pos(name, x, y + 70)
        return name

    def discrete(self, owner: str, probs: list[float], x: float, y: float) -> str:
        total = sum(max(0.0, p) for p in probs) or 1.0
        ps = [round(max(0.0, p) / total, 6) for p in probs]
        ps[-1] = round(1 - sum(ps[:-1]), 6)
        name = self.define("DiscreteDistribution", self.unique(f"{owner}_Prob"))
        self.kw("DiscreteDistribution", name, "UnitType", "DimensionlessUnit")
        self.kw("DiscreteDistribution", name, "RandomSeed", str(self.next_seed()))
        self.kw("DiscreteDistribution", name, "ValueList", "  ".join(str(i + 1) for i in range(len(ps))))
        self.kw("DiscreteDistribution", name, "ProbabilityList", "  ".join(_num(p) for p in ps))
        self.pos(name, x, y + 60)
        return name

    # -------------------------------------------------------------- roteamento
    def _assemble_target(self, rule_id: str) -> str | None:
        """Junção E seguida de uma Entidade → montagem (Assemble) dessa entidade."""
        outs = self.m.outgoing(rule_id)
        if len(outs) == 1 and self.m.elements[outs[0].target].kind == EK.ENTITY:
            return outs[0].target
        return None

    def entry(self, node: str, via: str | None, _seen=None) -> str:
        """Componente JaamSim por onde entram as entidades que chegam a ``node`` pelo fluxo ``via``."""
        _seen = set() if _seen is None else _seen
        if (node, via) in _seen:
            return self.sink_for(node)
        _seen.add((node, via))
        e = self.m.elements[node]
        k, n = e.kind, self.names[node]
        ins, outs = self.m.incoming(node), self.m.outgoing(node)
        if k in PROCESS_KINDS:
            return f"{n}_Seize" if self.m.resources_of(node) else n
        if k == EK.EXIT:
            return n
        if k == EK.ENTITY:
            return f"{n}_Fila"
        if k == EK.RULE_OR:
            return f"{n}_Branch" if len(outs) > 1 else self.after(node, _seen)
        if k == EK.RULE_AND:
            if len(ins) > 1:
                return f"{n}_Fila_{ins.index(next(c for c in ins if c.id == via)) + 1}" if via else \
                    f"{n}_Fila_1"
            return f"{n}_Duplicate" if len(outs) > 1 else self.after(node, _seen)
        if k == EK.RULE_ANDOR:
            return f"{n}_Duplicate" if len(outs) > 1 else self.after(node, _seen)
        if k == EK.CONNECTOR:
            if outs:
                return self.after(node, _seen)
            key = e.name.strip().upper()
            for other in self.m.by_kind(EK.CONNECTOR):
                if other.name.strip().upper() == key and self.m.outgoing(other.id):
                    return self.entry(other.id, None, _seen)
            return self.sink_for(node)
        return self.sink_for(node)

    def after(self, node: str, _seen=None) -> str:
        """Componente seguinte ao processamento de ``node``."""
        outs = self.m.outgoing(node)
        if not outs:
            return self.sink_for(node)
        if len(outs) == 1:
            return self.entry(outs[0].target, outs[0].id, _seen)
        return f"{self.names[node]}_Decisao"

    def sink_for(self, node: str) -> str:
        name = f"{self.names[node]}_Saida"
        if name not in self.defs.get("EntitySink", []):
            self.used.add(name)
            self.define("EntitySink", name)
            e = self.m.elements[node]
            self.pos(name, e.x + 80, e.y)
            self.warnings.append(f"'{e.name}' não tem fluxo de saída nem Ponto final; "
                                 f"foi criado o EntitySink {name}.")
        return name

    def decision(self, node: str) -> None:
        """Cria o Branch para nós com várias saídas sem regra explícita."""
        outs = self.m.outgoing(node)
        if len(outs) <= 1:
            return
        e = self.m.elements[node]
        name = f"{self.names[node]}_Decisao"
        self.used.add(name)
        self.define("Branch", name)
        self.kw("Branch", name, "NextComponentList",
                "  ".join(self.entry(c.target, c.id) for c in outs))
        self.kw("Branch", name, "Choice",
                self.discrete(self.names[node], [c.probability for c in outs], e.x + 40, e.y))
        self.pos(name, e.x + 50, e.y)

    # ---------------------------------------------------------------- objetos
    def build(self) -> None:
        m = self.m
        for e in m.elements.values():
            n, k = self.names[e.id], e.kind
            ins, outs = m.incoming(e.id), m.outgoing(e.id)

            if k == EK.ENTITY:
                self.define("SimEntity", n)
                self.pos(n, e.x - 60, e.y)
                if not ins:
                    g = self.define("EntityGenerator", self.unique(f"{n}_Chegada"))
                    p = e.params
                    self.kw("EntityGenerator", g, "NextComponent", self.after(e.id))
                    first = str(p.get("first_arrival", "0")).strip()
                    if first not in ("0", "0.0", "CONST(0)"):
                        self.kw("EntityGenerator", g, "FirstArrivalTime",
                                self.time_value(first, f"{n}_Primeira", e.x, e.y))
                    self.kw("EntityGenerator", g, "InterArrivalTime",
                            self.time_value(p.get("interarrival", "EXPO(10)"), f"{n}_Chegada", e.x, e.y))
                    if int(p.get("batch_size", 1)) > 1:
                        self.kw("EntityGenerator", g, "EntitiesPerArrival", str(int(p["batch_size"])))
                    if int(p.get("max_arrivals", 0) or 0) > 0:
                        self.kw("EntityGenerator", g, "MaxNumber", str(int(p["max_arrivals"])))
                    self.kw("EntityGenerator", g, "PrototypeEntity", n)
                    self.pos(g, e.x, e.y)
                    self.decision(e.id)
                else:
                    # transformação: cada entidade que chega vira uma entidade deste tipo
                    feeders = [c for c in ins if not (m.elements[c.source].kind == EK.RULE_AND
                                                      and self._assemble_target(c.source) == e.id
                                                      and len(m.incoming(c.source)) > 1)]
                    if feeders:
                        q = self.define("Queue", f"{n}_Fila")
                        self.used.add(q)
                        a = self.define("Assemble", self.unique(f"{n}_Transformar"))
                        self.kw("Assemble", a, "NextComponent", self.after(e.id))
                        self.kw("Assemble", a, "WaitQueueList", q)
                        self.kw("Assemble", a, "PrototypeEntity", n)
                        self.pos(q, e.x - 30, e.y + 40)
                        self.pos(a, e.x, e.y)
                        self.decision(e.id)
                    elif len(outs) > 1:
                        self.decision(e.id)

            elif k in PROCESS_KINDS:
                res = m.resources_of(e.id)
                dur = e.params.get("duration", "0")
                nxt = self.after(e.id)
                if res:
                    q = self.define("Queue", self.unique(f"{n}_Fila"))
                    s = self.define("Seize", f"{n}_Seize")
                    r = self.define("Release", f"{n}_Release")
                    self.used |= {s, r}
                    rl = "  ".join(self.names[x.id] for x in res)
                    self.kw("Seize", s, "NextComponent", n)
                    self.kw("Seize", s, "WaitQueue", q)
                    self.kw("Seize", s, "ResourceList", rl)
                    self.kw("Release", r, "NextComponent", nxt)
                    self.kw("Release", r, "ResourceList", rl)
                    self.pos(q, e.x - 50, e.y - 40)
                    self.pos(s, e.x - 50, e.y)
                    self.pos(r, e.x + 50, e.y)
                    nxt_of_proc = r
                else:
                    nxt_of_proc = nxt
                if k == EK.FUNCTION:
                    self.define("EntityDelay", n)
                    self.kw("EntityDelay", n, "NextComponent", nxt_of_proc)
                    self.kw("EntityDelay", n, "Duration", self.time_value(dur, n, e.x, e.y))
                    self.points(n, e.x - 30, e.y, e.x + 30, e.y)
                else:
                    self.define("EntityConveyor", n)
                    self.kw("EntityConveyor", n, "NextComponent", nxt_of_proc)
                    self.kw("EntityConveyor", n, "TravelTime", self.time_value(dur, n, e.x, e.y))
                    self.points(n, e.x - 30, e.y, e.x + 30, e.y)
                self.decision(e.id)

            elif k == EK.RESOURCE:
                self.define("Resource", n)
                self.kw("Resource", n, "Capacity", str(int(e.params.get("capacity", 1))))
                self.pos(n, e.x, e.y)

            elif k == EK.RULE_OR and len(outs) > 1:
                b = self.define("Branch", f"{n}_Branch")
                self.used.add(b)
                self.kw("Branch", b, "NextComponentList",
                        "  ".join(self.entry(c.target, c.id) for c in outs))
                self.kw("Branch", b, "Choice", self.discrete(n, [c.probability for c in outs], e.x, e.y))
                self.pos(b, e.x, e.y)

            elif k == EK.RULE_AND:
                if len(ins) > 1:
                    qs = []
                    for i, _c in enumerate(ins):
                        q = self.define("Queue", f"{n}_Fila_{i + 1}")
                        self.used.add(q)
                        self.pos(q, e.x - 40, e.y - 30 + 30 * i)
                        qs.append(q)
                    target = self._assemble_target(e.id)
                    if target:  # montagem: as partes formam a nova entidade
                        a = self.define("Assemble", self.unique(f"{n}_Montagem"))
                        self.kw("Assemble", a, "NextComponent", self.after(target))
                        self.kw("Assemble", a, "WaitQueueList", "  ".join(qs))
                        self.kw("Assemble", a, "PrototypeEntity", self.names[target])
                        self.pos(a, e.x, e.y)
                        continue
                    c = self.define("Combine", self.unique(f"{n}_Combine"))
                    nxt = f"{n}_Duplicate" if len(outs) > 1 else self.after(e.id)
                    self.kw("Combine", c, "NextComponent", nxt)
                    self.kw("Combine", c, "WaitQueueList", "  ".join(qs))
                    self.pos(c, e.x, e.y)
                if len(outs) > 1:
                    d = self.define("Duplicate", f"{n}_Duplicate")
                    self.used.add(d)
                    tg = [self.entry(c.target, c.id) for c in outs]
                    self.kw("Duplicate", d, "NextComponent", tg[0])
                    self.kw("Duplicate", d, "TargetComponentList", "  ".join(tg[1:]))
                    self.pos(d, e.x + 20, e.y)

            elif k == EK.RULE_ANDOR and len(outs) > 1:
                d = self.define("Duplicate", f"{n}_Duplicate")
                self.used.add(d)
                descarte = self.define("EntitySink", self.unique(f"{n}_Descarte"))
                self.pos(descarte, e.x, e.y + 90)
                branches = []
                for i, c in enumerate(outs):
                    b = self.define("Branch", self.unique(f"{n}_Ramo_{i + 1}"))
                    p = min(max(c.probability, 0.0), 1.0)
                    self.kw("Branch", b, "NextComponentList", f"{self.entry(c.target, c.id)}  {descarte}")
                    self.kw("Branch", b, "Choice", self.discrete(b, [p, 1 - p], e.x + 30, e.y + 40 * i))
                    self.pos(b, e.x + 30, e.y - 20 + 40 * i)
                    branches.append(b)
                self.kw("Duplicate", d, "NextComponent", branches[0])
                self.kw("Duplicate", d, "TargetComponentList", "  ".join(branches[1:]))
                self.pos(d, e.x, e.y)
                self.warnings.append(f"Regra E/OU '{e.name}': cada ramo é seguido com a sua "
                                     "probabilidade, de forma independente (no JaamSim pode não "
                                     "seguir nenhum ramo; entidades descartadas vão para "
                                     f"{descarte}).")

            elif k == EK.EXIT:
                self.define("EntitySink", n)
                self.pos(n, e.x, e.y)

            elif k == EK.CONNECTOR and outs:
                self.decision(e.id)

            elif k in (EK.NOTE, EK.CONTROL):
                t = self.define("Text", self.unique(f"{n}_Texto"))
                label = e.name if k == EK.NOTE else f"Controle: {e.name}"
                targets = [m.elements[c.target].name for c in m.outgoing(e.id, CK.CONTROL)]
                if targets:
                    label += f" ({', '.join(targets)})"
                self.kw("Text", t, "Format", _q(label))
                self.kw("Text", t, "TextHeight", "0.15  m")
                self.pos(t, e.x, e.y)

    # ------------------------------------------------------------------ saída
    def render(self) -> ExportResult:
        self.build()
        m, s, u = self.m, self.m.settings, self.unit
        order = ["SimEntity", "EntityGenerator", "Queue", "Seize", "EntityDelay", "EntityConveyor",
                 "Release", "Resource", "Branch", "Duplicate", "Combine", "Assemble", "EntitySink",
                 "ExponentialDistribution", "NormalDistribution", "TriangularDistribution",
                 "UniformDistribution", "LogNormalDistribution", "ErlangDistribution",
                 "WeibullDistribution", "DiscreteDistribution", "Text"]
        kinds = [k for k in order if k in self.defs] + [k for k in self.defs if k not in order]
        out = [
            "# " + "=" * 76,
            f"# Modelo JaamSim gerado pelo {APP_NAME} {__version__} a partir do modelo IDEF-SIM",
            f"#   '{m.name}'" + (f" — autor: {m.author}" if m.author else ""),
            f"# {APP_NAME}: {AUTHOR} — {INSTITUTION} — {EMAIL}",
            "#",
            "# Modelo BÁSICO: revise no JaamSim os tempos, as regras e a animação.",
            "# Abra este arquivo no JaamSim (File > Open).",
            "# " + "=" * 76,
        ]
        if self.warnings:
            out.append("#\n# Avisos da conversão:")
            out += [f"#  - {w}" for w in self.warnings]
        out += ["", "RecordEdits", ""]
        for k in kinds:
            out.append(f"Define {k} {{ {'  '.join(self.defs[k])} }}")
        out += ["Define View { View1 }", "Define OverlayText { Titulo }", ""]
        out += self.early + [""]
        out += ["Simulation Description { " + _q(f"{m.name} (gerado a partir do IDEF-SIM)") + " }",
                f"Simulation RunDuration {{ {_num(s.duration)}  {u} }}"]
        if s.warmup > 0:
            out.append(f"Simulation InitializationDuration {{ {_num(s.warmup)}  {u} }}")
        out += [f"Simulation NumberOfReplications {{ {int(s.replications)} }}",
                f"Simulation GlobalSubstreamSeed {{ {int(s.seed) % 100000} }}",
                "Simulation PrintReport { TRUE }", ""]
        for k in kinds:
            if self.lines.get(k):
                out.append(f"# *** {k} ***")
                out += self.lines[k]
                out.append("")
        xs = [p[0] for p in self.positions] or [0.0]
        ys = [p[1] for p in self.positions] or [0.0]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        dist_view = max(max(xs) - min(xs), (max(ys) - min(ys)) * 1.6, 5.0) * 1.1
        out += ["# *** GRAPHICS INPUTS ***", "",
                f"Simulation DisplayedUnits {{ {u} }}",
                "Simulation RealTime { FALSE }",
                "Simulation ShowLabels { TRUE }",
                "Simulation ShowModelBuilder { TRUE }",
                "Simulation ShowObjectSelector { TRUE }",
                "Simulation ShowInputEditor { TRUE }",
                "Simulation ShowOutputViewer { TRUE }", ""]
        out += self.graphics
        out += ["",
                "Titulo ScreenPosition { 15  15 }",
                "Titulo TextHeight { 18 }",
                "Titulo Format { " + _q(m.name) + " }", "",
                "View1 Description { 'Default view window' }",
                f"View1 ViewCenter {{ {_num(cx)}  {_num(cy)}  0.0  m }}",
                f"View1 ViewPosition {{ {_num(cx)}  {_num(cy)}  {_num(dist_view)}  m }}",
                "View1 ShowWindow { TRUE }",
                "View1 Lock2D { TRUE }", ""]
        count = sum(len(v) for v in self.defs.values())
        return ExportResult(ascii_text("\n".join(out)) + "\n", self.warnings, count)


def export_jaamsim(model: Model) -> ExportResult:
    """Converte o modelo IDEF-SIM em texto de configuração (.cfg) do JaamSim."""
    return _Exporter(model).render()
