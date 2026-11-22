"""Gera um modelo básico do JaamSim (.cfg) a partir de um modelo IDEF-SIM.

Correspondência entre os elementos (sintaxe conferida no código-fonte e nos exemplos
oficiais do JaamSim):

=================================  ==================================================
IDEF-SIM                           JaamSim
=================================  ==================================================
Entidade com chegada externa       SimEntity + EntityGenerator
Entidade de transformação          Queue + Assemble (cria a nova entidade)
Função                             Queue + EntityProcessor (ResourceList, Capacity, ServiceTime)
Função que representa uma fila     Queue (WaitQueue do processo seguinte), sem tempo
Movimentação                       EntityConveyor (com Seize/Release se tiver recurso)
Recurso                            Resource (Capacity)
Regra OU (X) – probabilidade       Branch + DiscreteDistribution
Regra OU (X) – por atributo        Branch com Choice 'cond1 ? 1 : (cond2 ? 2 : padrão)'
Regra OU (X) – apenas visual       Branch com chances iguais + Text com o critério (aviso)
Atributos da entidade              AttributeDefinitionList + Assign ([Distribuição].Value)
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
from . import expressions as expr
from .model import ConnectionKind as CK, ElementKind as EK, Model, PROCESS_KINDS

UNIT_MAP = {"s": "s", "seg": "s", "segundo": "s", "segundos": "s",
            "min": "min", "minuto": "min", "minutos": "min",
            "h": "h", "hora": "h", "horas": "h",
            "d": "d", "dia": "d", "dias": "d"}
SCALE = 1 / 20.0  # pixels do diagrama → metros no JaamSim (funções a ~8 m umas das outras)
CELL = 1.4        # espaço mínimo (m) entre objetos auxiliares (filas, distribuições...)
UNLIMITED = 1000000  # "capacidade infinita" de uma Função sem recurso
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
        self.func_queues: dict[str, str] = {}
        self.notes: list[str] = []                  # informações (não são problemas)
        self.lines: dict[str, list[str]] = {}      # tipo → linhas de palavras-chave
        self.graphics: list[str] = []
        self.used: set[str] = set()
        self.seed = 0
        self.positions: list[tuple[float, float]] = []
        # nomes JaamSim por elemento
        rule_names = {EK.RULE_AND: "Regra_E", EK.RULE_OR: "Regra_OU", EK.RULE_ANDOR: "Regra_EOU"}
        self.names = {e.id: self.unique(rule_names.get(e.kind) or jaamsim_name(e.name))
                      for e in model.elements.values()}
        # posições dos elementos do diagrama ficam reservadas (os auxiliares desviam delas)
        self.anchor_names = set(self.names.values())
        # posições exatas dos elementos (a entidade-protótipo fica 3 m à esquerda da chegada)
        self.occupied = [((e.x - (60 if e.kind == EK.ENTITY else 0)) * SCALE, -e.y * SCALE)
                         for e in model.elements.values()]
        self.attr_names = model.attribute_names()

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

    def _free(self, X: float, Y: float) -> bool:
        return all((X - a) ** 2 + (Y - b) ** 2 >= CELL * CELL for a, b in self.occupied)

    def pos(self, obj: str, x: float, y: float) -> None:
        X, Y = x * SCALE, -y * SCALE
        if obj not in self.anchor_names:  # objeto auxiliar: desvia dos que já existem
            while not self._free(X, Y):
                X += CELL
        self.occupied.append((X, Y))
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
        """Tempo: valor com unidade ou objeto de distribuição do JaamSim."""
        return self.dist_value(text, f"{owner}_Tempo", x, y, time=True)

    def dist_value(self, text: str, name: str, x: float, y: float, time: bool) -> str:
        """Converte uma distribuição em valor constante ou objeto de distribuição do JaamSim.

        Palavras-chave conferidas no código-fonte do JaamSim (ProbabilityDistributions).
        """
        try:
            d = dist.parse(text, allow_negative=not time, for_time=time)
        except dist.DistributionError as ex:
            self.warnings.append(f"{name}: distribuição inválida ({ex}); usado 0.")
            return f"0  {self.unit}" if time else "0"
        u = self.unit if time else ""
        t = lambda v: f"{_num(v)}  {u}".strip()  # noqa: E731  valor com a unidade
        a = d.args
        if d.name == "CONST":
            return t(a[0])
        spec = dist.SPECS[d.name]
        cls = spec.jaamsim
        if d.name == "EXPO":
            kws = [("Mean", t(a[0]))]
        elif d.name == "NORM":
            kws = [("Mean", t(a[0])), ("StandardDeviation", t(a[1]))]
            if time:  # truncada em zero, como no IDEF-SIM Studio
                kws.append(("MinValue", t(0)))
        elif d.name == "TRIA":
            kws = [("MinValue", t(a[0])), ("Mode", t(a[1])), ("MaxValue", t(a[2]))]
        elif d.name == "UNIF":
            kws = [("MinValue", t(a[0])), ("MaxValue", t(a[1]))]
        elif d.name == "ERLA":
            kws = [("Mean", t(a[0])), ("Shape", str(int(a[1])))]
        elif d.name == "GAMM":
            kws = [("Mean", t(a[0])), ("Shape", _num(a[1]))]
        elif d.name in ("WEIB", "LOGL"):
            kws = [("Scale", t(a[0])), ("Shape", _num(a[1]))]
        elif d.name == "BETA":  # intervalo [Location, Location + Scale]
            kws = [("AlphaParam", _num(a[0])), ("BetaParam", _num(a[1])),
                   ("Location", t(a[2])), ("Scale", t(a[3] - a[2]))]
        elif d.name == "LOGN":
            # JaamSim usa os parâmetros da normal subjacente: amostra = Scale·exp(N(μ, σ))
            mean, sd = a
            s2 = math.log(1 + (sd * sd) / (mean * mean))
            kws = [("Scale", t(1)), ("NormalMean", _num(math.log(mean) - s2 / 2)),
                   ("NormalStandardDeviation", _num(math.sqrt(s2)))]
        elif d.name in ("DISC", "CONT"):
            vals = "  ".join(_num(v) for v in d.disc_values) + (f"  {u}" if u else "")
            probs = "  ".join(_num(p) for p in d.disc_probs)
            kws = [("ValueList", vals),
                   ("ProbabilityList" if d.name == "DISC" else "CumulativeProbabilityList", probs)]
        elif d.name == "POIS":
            kws = [("Mean", _num(a[0]))]
        elif d.name == "BINO":
            kws = [("NumberOfTrials", str(int(a[0]))), ("Probability", _num(a[1]))]
        elif d.name == "GEOM":
            kws = [("Probability", _num(a[0]))]
        elif d.name == "NBIN":
            kws = [("SuccessfulTrials", str(int(a[0]))), ("Probability", _num(a[1]))]
        else:  # DUNI
            kws = [("MinValue", str(int(a[0]))), ("MaxValue", str(int(a[1])))]
        obj = self.define(cls, self.unique(name))
        if not spec.count:  # nas de contagem a unidade é fixa (palavra oculta no JaamSim)
            self.kw(cls, obj, "UnitType", "TimeUnit" if time else "DimensionlessUnit")
        self.kw(cls, obj, "RandomSeed", str(self.next_seed()))
        for k, v in kws:
            self.kw(cls, obj, k, v)
        self.pos(obj, x, y + 60)
        return obj

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
        if k == EK.FUNCTION and self.m.is_queue(node):
            # função-fila: é o Queue de espera do processo seguinte (ou passagem direta)
            return n if self.queue_active(node) else self.after(node, _seen)
        if k == EK.FUNCTION:
            return self.queue_of(node)          # o EntityProcessor puxa da sua fila
        if k == EK.MOVEMENT:
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

    def with_assign(self, entity_id: str, nxt: str) -> str:
        """Se a entidade tem atributos, cria um Assign que os sorteia antes de ``nxt``."""
        e = self.m.elements[entity_id]
        attrs = [a for a in e.params.get("attributes", []) if a.get("name", "").strip()]
        if not attrs:
            return nxt
        n = self.names[entity_id]
        asg = self.define("Assign", self.unique(f"{n}_Atributos"))
        items = []
        for a in attrs:
            nm = a["name"].strip()
            v = self.dist_value(a.get("value", "0"), f"{n}_{nm}", e.x + 40, e.y + 40, time=False)
            ref = f"[{v}].Value" if v in self.used else v
            items.append("{ " + _q(f"this.obj.{nm} = {ref}") + " }")
        self.kw("Assign", asg, "NextComponent", nxt)
        self.kw("Assign", asg, "AttributeAssignmentList", "  ".join(items))
        self.pos(asg, e.x + 40, e.y)
        return asg

    def queue_of(self, node: str) -> str:
        """Nome (estável) da fila de espera de um processo: a função-fila que o alimenta
        (a primeira, se houver mais de uma) ou uma fila criada para ele."""
        if node not in self.func_queues:
            feeders = [q.id for q in self.m.elements.values() if self.m.queue_feeds(q.id) == node]
            self.func_queues[node] = (self.names[feeders[0]] if feeders
                                      else self.unique(f"{self.names[node]}_Fila"))
        return self.func_queues[node]

    def queue_active(self, node: str) -> bool:
        """A função-fila é de fato a fila de espera do processo seguinte?"""
        fed = self.m.queue_feeds(node)
        return bool(fed) and self.queue_of(fed) == self.names[node]

    def define_queue(self, name: str, x: float, y: float) -> str:
        """Define o Queue uma única vez (pode ser compartilhado com uma função-fila)."""
        if name not in self.defs.get("Queue", []):
            self.define("Queue", name)
            self.pos(name, x, y)
        return name

    def after(self, node: str, _seen=None) -> str:
        """Componente seguinte ao processamento de ``node``."""
        outs = self.m.outgoing(node)
        if not outs:
            return self.sink_for(node)
        if len(outs) == 1:
            return self.entry(outs[0].target, outs[0].id, _seen)
        return f"{self.names[node]}_Decisao"

    def condition_choice(self, e, outs) -> str:
        """Expressão do Choice: 'c1 ? 1 : (c2 ? 2 : padrão)'."""
        default = None
        conds = []
        for i, c in enumerate(outs, start=1):
            cond = (c.condition or "").strip()
            if not cond or expr.is_default(cond):
                default = default or i
                continue
            try:
                conds.append((expr.to_jaamsim(cond), i))
            except expr.ExpressionError as ex:
                self.warnings.append(f"Condição inválida na regra '{e.name}': {ex}")
        out = str(default or len(outs))
        for js, i in reversed(conds):
            out = f"{js} ? {i} : ({out})" if out.count("?") else f"{js} ? {i} : {out}"
        return out

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
                if self.attr_names:  # todos os atributos do modelo (condições podem usá-los)
                    self.kw("SimEntity", n, "AttributeDefinitionList",
                            "  ".join(f"{{ {a}  0 }}" for a in self.attr_names))
                if not ins:
                    g = self.define("EntityGenerator", self.unique(f"{n}_Chegada"))
                    p = e.params
                    self.kw("EntityGenerator", g, "NextComponent",
                            self.with_assign(e.id, self.after(e.id)))
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
                        self.kw("Assemble", a, "NextComponent",
                                self.with_assign(e.id, self.after(e.id)))
                        self.kw("Assemble", a, "WaitQueueList", q)
                        self.kw("Assemble", a, "PrototypeEntity", n)
                        self.pos(q, e.x - 30, e.y + 40)
                        self.pos(a, e.x, e.y)
                        self.decision(e.id)
                    elif len(outs) > 1:
                        self.decision(e.id)

            elif k == EK.FUNCTION and m.is_queue(e.id):
                # Função que representa uma fila → só um Queue (WaitQueue do processo seguinte)
                if self.queue_active(e.id):
                    self.define_queue(n, e.x, e.y)
                else:
                    self.warnings.append(f"Fila '{e.name}' não alimenta uma Função (ou Movimentação "
                                         "com recurso) e foi ignorada: as entidades passam direto.")
                    self.decision(e.id)

            elif k == EK.FUNCTION:
                # Função → Queue + EntityProcessor (captura os recursos, processa e libera)
                res = m.resources_of(e.id)
                q = self.define_queue(self.queue_of(e.id), e.x - 50, e.y - 40)
                self.define("EntityProcessor", n)
                self.kw("EntityProcessor", n, "NextComponent", self.after(e.id))
                self.kw("EntityProcessor", n, "WaitQueue", q)
                if res:
                    self.kw("EntityProcessor", n, "ResourceList",
                            "  ".join(self.names[x.id] for x in res))
                    cap = min(int(x.params.get("capacity", 1)) for x in res)
                else:
                    cap = UNLIMITED
                    self.notes.append(f"Funcao '{e.name}' sem recurso: capacidade ilimitada "
                                      f"(Capacity {UNLIMITED}), como no IDEF-SIM Studio.")
                self.kw("EntityProcessor", n, "Capacity", str(cap))
                self.kw("EntityProcessor", n, "ServiceTime",
                        self.time_value(e.params.get("duration", "0"), n, e.x, e.y))
                self.pos(n, e.x, e.y)
                self.decision(e.id)

            elif k == EK.MOVEMENT:
                res = m.resources_of(e.id)
                dur = e.params.get("duration", "0")
                nxt = self.after(e.id)
                if res:
                    q = self.define_queue(self.queue_of(e.id), e.x - 50, e.y - 40)
                    s = self.define("Seize", f"{n}_Seize")
                    r = self.define("Release", f"{n}_Release")
                    self.used |= {s, r}
                    rl = "  ".join(self.names[x.id] for x in res)
                    self.kw("Seize", s, "NextComponent", n)
                    self.kw("Seize", s, "WaitQueue", q)
                    self.kw("Seize", s, "ResourceList", rl)
                    self.kw("Release", r, "NextComponent", nxt)
                    self.kw("Release", r, "ResourceList", rl)
                    self.pos(s, e.x - 50, e.y)
                    self.pos(r, e.x + 50, e.y)
                    nxt_of_proc = r
                else:
                    nxt_of_proc = nxt
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
                decision = m.decision_of(e.id)
                if decision == "condition":
                    self.kw("Branch", b, "Choice", _q(self.condition_choice(e, outs)))
                elif decision == "visual":
                    crit = e.params.get("criterion", "").strip() or "nao informado"
                    self.kw("Branch", b, "Choice", self.discrete(n, [1.0] * len(outs), e.x, e.y))
                    t = self.define("Text", self.unique(f"{n}_Criterio"))
                    self.kw("Text", t, "Format", _q(f"Decisao: {crit} (implementar a regra)"))
                    self.kw("Text", t, "TextHeight", "0.2  m")
                    self.pos(t, e.x, e.y - 40)
                    self.warnings.append(f"Regra OU '{n}' é apenas visual (critério: {crit}): "
                                         "exportada com chances iguais; implemente a regra no "
                                         f"Choice de {b}.")
                else:
                    self.kw("Branch", b, "Choice",
                            self.discrete(n, [c.probability for c in outs], e.x, e.y))
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
                        self.kw("Assemble", a, "NextComponent",
                                self.with_assign(target, self.after(target)))
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
        order = ["SimEntity", "EntityGenerator", "Queue", "EntityProcessor", "Seize", "EntityDelay",
                 "EntityConveyor",
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
        if self.notes:
            out.append("#\n# Notas:")
            out += [f"#  - {w}" for w in self.notes]
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
