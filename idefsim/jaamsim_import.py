"""Importa um modelo do JaamSim (.cfg) como diagrama IDEF-SIM.

Correspondência (inverso da exportação; palavras-chave conferidas no código-fonte do JaamSim):

=====================================  ===============================================
JaamSim                                IDEF-SIM
=====================================  ===============================================
EntityGenerator + SimEntity            Entidade com chegada externa (+ atributos)
Server                                 Função + Recurso de capacidade 1
EntityProcessor                        Função + recursos (ResourceList) ou Capacity
EntityDelay                            Função sem recurso
EntityConveyor                         Movimentação
Queue                                  Função que representa uma fila
Seize ... Release                      recursos ligados ao processo entre eles
Resource / ResourcePool(+Units)        Recurso (capacidade)
Branch                                 Regra OU (probabilidade, atributo ou visual)
Duplicate                              Regra E (divisão)
Combine / Assemble                     Regra E (junção) / junção + nova Entidade
EntitySink                             Ponto final
Pack, Unpack, AddTo, RemoveFrom ...    Função (apenas representação)
Assign, Statistics, SetGraphics ...    omitidos (só atravessam)
=====================================  ===============================================

O resultado é um modelo conceitual: o que não tem equivalente direto é anotado no
relatório da importação e na descrição do modelo.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import distributions as dist
from . import expressions as expr
from .gui_free_geometry import element_rect, overlaps
from .model import ConnectionKind as CK, ElementKind as EK, Model

UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0,
                "w": 604800.0, "y": 31536000.0}
MODEL_UNITS = {"s": "s", "min": "min", "h": "h", "d": "dia"}
PASS_THROUGH = {"Assign", "Statistics", "SetGraphics", "EntityLogger", "EntitySignal", "EntityLabel",
                "Seize", "Release", "SubModelStart", "SubModelEnd", "SubModel", "EntitySystem"}
VISUAL_FUNCTIONS = {"Pack", "Unpack", "AddTo", "RemoveFrom", "EntityContainer",
                    "Workstation"}
DX, DY = 200, 150  # espaçamento do diagrama (colunas e linhas)
RES_LANE = 70      # espaço extra abaixo de uma linha com recursos


class JaamSimImportError(ValueError):
    pass


# ------------------------------------------------------------------ leitura do .cfg
def _tokens(text: str) -> list[str]:
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{}":
            out.append(c)
            i += 1
        elif c == "'":
            j = text.find("'", i + 1)
            j = n if j < 0 else j
            out.append(text[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{}'#":
                j += 1
            out.append(text[i:j])
            i = j
    return out


def _group(toks: list[str], i: int) -> tuple[list, int]:
    """Lê de toks[i] == '{' até a chave correspondente; devolve (lista aninhada, próximo índice)."""
    out, i = [], i + 1
    while i < len(toks) and toks[i] != "}":
        if toks[i] == "{":
            sub, i = _group(toks, i)
            out.append(sub)
        else:
            out.append(toks[i])
            i += 1
    return out, i + 1


class Cfg:
    def __init__(self, text: str):
        self.types: dict[str, str] = {}
        self.kw: dict[str, dict[str, list]] = defaultdict(dict)
        toks, i = _tokens(text), 0
        while i < len(toks):
            if i + 2 < len(toks) and toks[i + 2] == "{":
                a, b = toks[i], toks[i + 1]
                val, i = _group(toks, i + 2)
                if a == "Define":
                    for name in val:
                        if isinstance(name, str):
                            self.types[name] = b
                else:
                    self.kw[a][b] = val
            else:
                i += 1

    def get(self, obj: str, key: str) -> list:
        return self.kw.get(obj, {}).get(key, [])

    def names(self, obj: str, key: str) -> list[str]:
        return [t for t in self.get(obj, key) if isinstance(t, str)]

    def of_type(self, *types: str) -> list[str]:
        return [n for n, t in self.types.items() if t in types]


def _num(tok) -> float | None:
    try:
        return float(tok)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------- importador
@dataclass
class ImportResult:
    model: Model
    notes: list[str] = field(default_factory=list)
    skipped_types: Counter = field(default_factory=Counter)


class _Importer:
    def __init__(self, cfg: Cfg, title: str):
        self.c = cfg
        self.title = title
        self.notes: list[str] = []
        self.m = Model(name=title)
        self.unit = self._choose_unit()
        self.factor = UNIT_SECONDS[self.unit]
        self.m.settings.time_unit = MODEL_UNITS[self.unit]
        self.el: dict[str, str] = {}          # objeto JaamSim → id do elemento IDEF-SIM
        self.edges: list[list] = []           # [origem, destino, probabilidade, condição]
        self.jpos: dict[str, tuple[float, float]] = {}
        self.origin: dict[str, tuple[str, int] | None] = {}   # ligação → (Branch, índice da saída)
        self.passed: set[str] = set()

    # ---------------------------------------------------------------- unidades
    def _choose_unit(self) -> str:
        cnt = Counter()
        for obj, kws in self.c.kw.items():
            for v in kws.values():
                for t in v:
                    if isinstance(t, str) and t in ("s", "min", "h", "d"):
                        cnt[t] += 1
        return cnt.most_common(1)[0][0] if cnt else "s"

    def _quantity(self, toks, time: bool) -> float | None:
        """Número (convertido para a unidade do modelo se for tempo) ou InputValue."""
        if not toks:
            return None
        t0 = toks[0]
        if isinstance(t0, str) and self.c.types.get(t0) == "InputValue":
            return self._quantity(self.c.get(t0, "Value"), time)
        if isinstance(t0, str) and "[" in t0 and t0.endswith("]"):    # ex.: 0[s]
            m = re.match(r"^(-?[\d.eE+-]+)\[(\w+)\]$", t0)
            if m:
                t0, toks = m.group(1), [m.group(1), m.group(2)]
        v = _num(t0)
        if v is None:
            return None
        if time:
            unit = toks[1] if len(toks) > 1 and isinstance(toks[1], str) else "s"
            return v * UNIT_SECONDS.get(unit, 1.0) / self.factor
        return v

    def _dist_text(self, toks, owner: str, time: bool = True) -> str | None:
        """Valor/objeto do JaamSim → texto de distribuição do IDEF-SIM (None se impossível)."""
        q = self._quantity(toks, time)
        if q is not None:
            return dist.fmt("CONST", [max(q, 0.0) if time else q])
        name = toks[0] if toks and isinstance(toks[0], str) else ""
        typ = self.c.types.get(name, "")
        g = lambda k, t=time: self._quantity(self.c.get(name, k), t)  # noqa: E731
        try:
            if typ == "ExponentialDistribution":
                code, args = "EXPO", [g("Mean")]
            elif typ == "UniformDistribution":
                code, args = "UNIF", [g("MinValue"), g("MaxValue")]
            elif typ == "TriangularDistribution":
                code, args = "TRIA", [g("MinValue"), g("Mode"), g("MaxValue")]
            elif typ == "NormalDistribution":
                code, args = "NORM", [g("Mean"), g("StandardDeviation")]
            elif typ in ("ErlangDistribution", "GammaDistribution"):
                code, args = ("ERLA" if typ[0] == "E" else "GAMM"), [g("Mean"), g("Shape", False)]
            elif typ in ("WeibullDistribution", "LogLogisticDistribution"):
                code, args = ("WEIB" if typ[0] == "W" else "LOGL"), [g("Scale"), g("Shape", False)]
            elif typ == "LogNormalDistribution":
                mu = g("NormalMean", False) or 0.0
                sg = g("NormalStandardDeviation", False)
                sg = 1.0 if sg is None else sg
                scale = g("Scale")
                scale = (1.0 / self.factor if time else 1.0) if scale is None else scale
                mean = scale * math.exp(mu + sg * sg / 2)
                code, args = "LOGN", [mean, mean * math.sqrt(math.exp(sg * sg) - 1)]
            elif typ == "BetaDistribution":
                loc = g("Location") or 0.0
                sc = g("Scale")
                sc = 1.0 if sc is None else sc
                code, args = "BETA", [g("AlphaParam", False), g("BetaParam", False), loc, loc + sc]
            elif typ in ("DiscreteDistribution", "ContinuousDistribution"):
                vals = self.c.get(name, "ValueList")
                unit = vals[-1] if vals and _num(vals[-1]) is None else "s"
                nums = [_num(v) for v in vals if _num(v) is not None]
                if time:
                    nums = [v * UNIT_SECONDS.get(unit, 1.0) / self.factor for v in nums]
                key = "ProbabilityList" if typ[0] == "D" else "CumulativeProbabilityList"
                probs = [_num(p) for p in self.c.get(name, key) if _num(p) is not None]
                code = "DISC" if typ[0] == "D" else "CONT"
                args = [x for pair in zip(nums, probs) for x in pair]
            elif typ in ("PoissonDistribution",) and not time:
                code, args = "POIS", [g("Mean", False)]
            elif typ == "NonStatExponentialDist":
                self.notes.append(f"{owner}: chegadas não estacionárias ({name}) aproximadas por "
                                  "Exponencial de média 1 (ajuste o intervalo).")
                return dist.fmt("EXPO", [1.0])
            else:
                return None
            if any(a is None for a in args):
                return None
            text = dist.fmt(code, args)
            dist.parse(text, allow_negative=not time, for_time=time)
            return text
        except (dist.DistributionError, ValueError, ZeroDivisionError, OverflowError):
            return None

    def _time(self, obj: str, key: str, default: str = "0") -> str:
        toks = self.c.get(obj, key)
        if not toks:
            return default
        text = self._dist_text(toks, obj)
        if text is None:
            raw = " ".join(t for t in toks if isinstance(t, str))
            self.notes.append(f"{obj}: {key} '{raw}' não tem equivalente direto; usado o valor 1.")
            self._describe(obj, f"No JaamSim, {key} = {raw}")
            return dist.fmt("CONST", [1.0])
        return text

    def _one_second(self) -> str:
        """Padrão do JaamSim para InterArrivalTime: 1 s (na unidade do modelo)."""
        return dist.fmt("CONST", [1.0 / self.factor])

    def _describe(self, obj: str, text: str) -> None:
        if obj in self.el:
            e = self.m.elements[self.el[obj]]
            e.description = (e.description + "\n" if e.description else "") + text

    # ------------------------------------------------------------------ elementos
    def _label(self, obj: str) -> str:
        """Nome legível: 'MoveToTables' → 'Move To Tables' (quebra linha dentro da caixa)."""
        t = obj.replace("_", " ").replace(".", " · ")
        t = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def _add(self, obj: str, kind: EK, name: str | None = None, **params) -> str:
        e = self.m.add_element(kind, 0, 0, name or self._label(obj), **params)
        self.el[obj] = e.id
        pos = self.c.get(obj, "Position")
        pts = self.c.get(obj, "Points")
        if len(pos) >= 2 and _num(pos[0]) is not None:
            self.jpos[e.id] = (_num(pos[0]), _num(pos[1]))
        elif pts and isinstance(pts[0], list):
            xs = [_num(p[0]) for p in pts if isinstance(p, list) and _num(p[0]) is not None]
            ys = [_num(p[1]) for p in pts if isinstance(p, list) and len(p) > 1 and _num(p[1]) is not None]
            if xs and ys:
                self.jpos[e.id] = (sum(xs) / len(xs), sum(ys) / len(ys))
        return e.id

    def _resource(self, obj: str) -> str:
        if obj in self.el:
            return self.el[obj]
        typ = self.c.types.get(obj, "")
        if typ == "ResourcePool":
            cap = sum(1 for u in self.c.of_type("ResourceUnit") if obj in self.c.names(u, "ResourcePool"))
            cap = cap or int(self._quantity(self.c.get(obj, "Capacity"), False) or 1)
        else:
            cap = int(self._quantity(self.c.get(obj, "Capacity"), False) or 1)
        return self._add(obj, EK.RESOURCE, capacity=max(1, cap))

    def _drop_unused_submodel_prototypes(self) -> None:
        """Submodelo que nenhum fluxo usa é só um molde (protótipo de clones): ignora o interior."""
        c = self.c
        targets = {t for kws in c.kw.values()
                   for k in ("NextComponent", "NextComponentList", "TargetComponentList")
                   for t in kws.get(k, []) if isinstance(t, str)}
        for sm in c.of_type("SubModel"):
            if sm not in targets:
                for n in [n for n in c.types if n.startswith(sm + ".")]:
                    del c.types[n]

    def _proto(self, obj: str) -> str:
        """Protótipo da entidade; se for uma expressão do JaamSim, usa o nome do gerador."""
        p = (self.c.names(obj, "PrototypeEntity") or [obj])[0]
        return obj if (p.startswith("'") or "[" in p or "(" in p) else p

    def build(self) -> Model:
        c = self.c
        self._drop_unused_submodel_prototypes()
        protos = Counter(self._proto(g) for g in c.of_type("EntityGenerator"))
        attrs = {s: self._attributes(s) for s in c.of_type("SimEntity")}
        for obj, typ in list(c.types.items()):
            if typ == "EntityLauncher":  # lança entidades quando sinalizado
                proto = self._proto(obj)
                eid = self._add(obj, EK.ENTITY, self._label(proto), interarrival="CONST(1)",
                                attributes=attrs.get(proto, []))
                self._describe(obj, "No JaamSim: EntityLauncher (chegadas disparadas por evento)")
                self.notes.append(f"{obj}: EntityLauncher lança entidades por evento; representado "
                                  "como chegada a cada 1 unidade de tempo (ajuste o intervalo).")
            elif typ == "EntityGenerator":
                proto = self._proto(obj)
                name = self._label(proto if protos[proto] <= 1 else obj)
                eid = self._add(obj, EK.ENTITY, name,
                                interarrival=self._time(obj, "InterArrivalTime", self._one_second()),
                                first_arrival=self._time(obj, "FirstArrivalTime", "0"))
                e = self.m.elements[eid]
                n = self._quantity(c.get(obj, "EntitiesPerArrival"), False)
                if n and n > 1:
                    e.params["batch_size"] = int(n)
                mx = self._quantity(c.get(obj, "MaxNumber"), False)
                if mx and mx > 0:
                    e.params["max_arrivals"] = int(mx)
                e.params["attributes"] = attrs.get(proto, [])
                if e.params["interarrival"] == "CONST(0)":
                    e.params["interarrival"] = "CONST(1)"
                    self.notes.append(f"{obj}: intervalo entre chegadas nulo; usado 1.")
            elif typ == "Server":
                fid = self._add(obj, EK.FUNCTION, duration=self._time(obj, "ServiceTime"))
                rid = self._add(f"{obj}#recurso", EK.RESOURCE, f"Recurso {self._label(obj)}", capacity=1)
                self.jpos.pop(rid, None)
                self.m.add_connection(CK.RESOURCE, rid, fid)
            elif typ == "EntityProcessor":
                fid = self._add(obj, EK.FUNCTION, duration=self._time(obj, "ServiceTime"))
                res = c.names(obj, "ResourceList")
                if res:
                    for r in res:
                        self.m.add_connection(CK.RESOURCE, self._resource(r), fid)
                else:
                    cap = int(self._quantity(c.get(obj, "Capacity"), False) or 1)
                    rid = self._add(f"{obj}#recurso", EK.RESOURCE, f"Recurso {self._label(obj)}",
                                    capacity=max(1, cap))
                    self.m.add_connection(CK.RESOURCE, rid, fid)
            elif typ == "EntityDelay":
                self._add(obj, EK.FUNCTION, duration=self._time(obj, "Duration"))
            elif typ == "EntityConveyor":
                self._add(obj, EK.MOVEMENT, duration=self._time(obj, "TravelTime"))
            elif typ in ("Queue", "EntityGate"):
                self._add(obj, EK.FUNCTION, is_queue=True, duration="CONST(0)")
            elif typ == "Branch":
                self._add(obj, EK.RULE_OR)
            elif typ in ("Duplicate", "Combine"):
                self._add(obj, EK.RULE_AND)
            elif typ == "Assemble":
                self._add(obj, EK.RULE_AND)
                proto = self._proto(obj)
                pid = self._add(f"{obj}#entidade", EK.ENTITY, self._label(proto),
                                attributes=attrs.get(proto, []))
                if self.el[obj] in self.jpos:  # a nova entidade fica logo após a junção
                    self.jpos[pid] = self._shift(self.jpos[self.el[obj]], 1.0)
            elif typ == "EntitySink":
                self._add(obj, EK.EXIT)
            elif typ in ("Resource", "ResourcePool"):
                self._resource(obj)
            elif typ in VISUAL_FUNCTIONS:
                fid = self._add(obj, EK.FUNCTION,
                                duration=self._time(obj, "ServiceTime") if c.get(obj, "ServiceTime")
                                else "CONST(0)")
                self._describe(obj, f"No JaamSim: {typ} (apenas representado)")
                self.notes.append(f"{obj} ({typ}) representado como Função, sem a lógica de {typ}.")
        not_represented = {
            "DowntimeEntity": "paradas/manutenção", "ExpressionThreshold": "limiares (condições de abertura)",
            "TimeSeriesThreshold": "limiares por série temporal", "SignalThreshold": "sinais",
            "EventSchedule": "programação de eventos", "EntitlementSelector": "seleção por direito",
            "TimeSeries": "séries temporais"}
        found = sorted({d for t, d in not_represented.items() if c.of_type(t)})
        if found:
            self.notes.append("Não representados no IDEF-SIM: " + ", ".join(found) + ".")
        self._flows()
        self._contract()
        self._seize_resources()
        self._branches()
        self._settings()
        self._layout()
        self.m.description = (
            f"Convertido do exemplo do JaamSim '{self.title}' (JaamSim: Apache License 2.0, "
            "© JaamSim Software Inc.). Modelo conceitual: confira tempos e regras."
            + ("\n\nObservações da conversão:\n- " + "\n- ".join(self.notes) if self.notes else ""))
        return self.m

    @staticmethod
    def _shift(p, dx):
        return (p[0] + dx, p[1]) if p else None

    def _attributes(self, proto: str) -> list[dict]:
        out = []
        for item in self.c.get(proto, "AttributeDefinitionList"):
            pair = item if isinstance(item, list) else None
            if pair is None:
                continue
            name = pair[0] if pair and isinstance(pair[0], str) else ""
            val = _num(pair[1]) if len(pair) > 1 else 0.0
            if expr.valid_attribute_name(name):
                out.append({"name": name, "value": dist.fmt("CONST", [val or 0.0])})
        flat = self.c.get(proto, "AttributeDefinitionList")
        if flat and all(isinstance(t, str) for t in flat) and expr.valid_attribute_name(flat[0]):
            out.append({"name": flat[0], "value": dist.fmt("CONST", [_num(flat[1]) or 0.0
                                                                     if len(flat) > 1 else 0.0])})
        return out

    # ------------------------------------------------------------------- fluxos
    def _consumer_queue(self, obj: str) -> str | None:
        q = self.c.names(obj, "WaitQueue")
        return q[0] if q else None

    def _target(self, obj: str) -> str:
        """Destino efetivo de uma entidade enviada a ``obj`` (fila de espera, submodelo...)."""
        typ = self.c.types.get(obj, "")
        if typ in ("Server", "EntityProcessor", "Seize"):
            q = self._consumer_queue(obj)
            if q:
                return q
        if typ == "SubModel":
            starts = [s for s in self.c.of_type("SubModelStart") if s.startswith(obj + ".")]
            if starts:
                return starts[0]
        return obj

    def _flows(self) -> None:
        c = self.c
        for obj, typ in c.types.items():
            nexts = c.names(obj, "NextComponent")
            if typ == "Branch":
                nexts = c.names(obj, "NextComponentList")
            if typ == "Duplicate":
                nexts = nexts + c.names(obj, "TargetComponentList")
            if typ == "SubModelEnd":
                parent = obj.rsplit(".", 1)[0]
                nexts = c.names(parent, "NextComponent")
            src = f"{obj}#entidade" if typ == "Assemble" else obj
            for i, t in enumerate(nexts):
                self.edges.append([src, self._target(t), 1.0, "", (obj, i)])
            if typ == "Assemble":
                self.edges.append([obj, src, 1.0, "", None])
            for key in ("WaitQueue", "WaitQueueList"):     # fila → quem a consome
                for q in c.names(obj, key):
                    self.edges.append([q, obj, 1.0, "", None])

    def _is_pass(self, obj: str) -> bool:
        return self.c.types.get(obj, "") in PASS_THROUGH or obj not in self.el and "#" not in obj

    def _contract(self) -> None:
        """Remove objetos sem símbolo IDEF-SIM (Assign, Seize...), ligando quem chega a quem sai."""
        changed = True
        while changed:
            changed = False
            for p in {e[1] for e in self.edges} | {e[0] for e in self.edges}:
                if p in self.el or not self._is_pass(p):
                    continue
                ins = [e for e in self.edges if e[1] == p]
                outs = [e for e in self.edges if e[0] == p]
                if len(outs) == 1 or not outs:
                    for e in ins:
                        if outs:
                            e[1] = outs[0][1]
                            e[4] = e[4] or outs[0][4]
                        else:
                            sink = f"{p}#fim"
                            if sink not in self.el:
                                self._add(sink, EK.EXIT, f"Fim ({self._label(p)})")
                                self.notes.append(f"{p}: destino sem equivalente; criado um Ponto final.")
                            e[1] = sink
                    self.edges = [e for e in self.edges if e[0] != p]
                    if p not in self.c.types or self.c.types.get(p) in PASS_THROUGH:
                        self.passed.add(p)
                    changed = True
                    break
                else:  # vários destinos (ex.: Seize compartilhado): representa como função
                    self._add(p, EK.FUNCTION, duration="CONST(0)")
                    changed = True
                    break
        for s, t, prob, cond, origin in self.edges:
            if s in self.el and t in self.el and s != t:
                try:
                    cnx = self.m.add_connection(CK.FLOW, self.el[s], self.el[t])
                    cnx.probability = prob
                    self.origin[cnx.id] = origin
                except Exception:  # noqa: BLE001  ligação repetida/ inválida
                    pass

    def _seize_resources(self) -> None:
        """Seize/Release: os recursos capturados vão para o primeiro processo depois do Seize."""
        c = self.c
        for s in c.of_type("Seize"):
            res = c.names(s, "ResourceList")
            nxt = c.names(s, "NextComponent")
            seen, cur = set(), (nxt[0] if nxt else None)
            while cur and cur not in seen:
                seen.add(cur)
                if cur in self.el and self.m.elements[self.el[cur]].kind in (EK.FUNCTION, EK.MOVEMENT) \
                        and not self.m.is_queue(self.el[cur]):
                    for r in res:
                        try:
                            self.m.add_connection(CK.RESOURCE, self._resource(r), self.el[cur])
                        except Exception:  # noqa: BLE001
                            pass
                    break
                n2 = c.names(cur, "NextComponent")
                cur = n2[0] if n2 else None

    def _branches(self) -> None:
        c = self.c
        for b in c.of_type("Branch"):
            if b not in self.el:
                continue
            bid = self.el[b]
            outs = self.m.outgoing(bid)
            by_index = {}
            for cnx in outs:
                o = self.origin.get(cnx.id)
                if o and o[0] == b:
                    by_index[o[1] + 1] = cnx
            n = len(c.names(b, "NextComponentList"))
            choice = c.get(b, "Choice")
            rule = self.m.elements[bid]
            ch = choice[0] if choice and isinstance(choice[0], str) else "1"
            k = _num(ch)
            typ = c.types.get(ch, "")
            if k is not None:                                         # índice fixo
                for i, cnx in by_index.items():
                    cnx.probability = 1.0 if i == int(k) else 0.0
            elif typ == "DiscreteDistribution":
                vals = [_num(v) for v in c.get(ch, "ValueList") if _num(v) is not None]
                probs = [_num(p) for p in c.get(ch, "ProbabilityList") if _num(p) is not None]
                weight = Counter()
                for v, p in zip(vals, probs):
                    weight[int(v)] += p
                for i, cnx in by_index.items():
                    cnx.probability = round(weight.get(i, 0.0), 6)
            else:
                text = ch.strip("'")
                conds = self._choice_conditions(text, n)
                if conds:
                    rule.params["decision"] = "condition"
                    for i, cnx in by_index.items():
                        cnx.condition = conds.get(i, "senão")
                else:
                    rule.params.update(decision="visual", criterion=text[:80])
                    self.notes.append(f"{b}: regra de escolha '{text}' mantida como texto "
                                      "(regra OU apenas visual).")

    @staticmethod
    def _choice_conditions(text: str, n: int) -> dict[int, str] | None:
        """Traduz escolhas por atributo: 'this.obj.X' → X == i; '(cond)+1' → cond na saída 2."""
        def tr(s: str) -> str:
            s = re.sub(r"this\.obj\.(\w+)", r"\1", s)
            return s.replace("&&", " e ").replace("||", " ou ")
        m = re.fullmatch(r"\s*this\.obj\.(\w+)\s*", text)
        if m and expr.valid_attribute_name(m.group(1)):
            return {i: f"{m.group(1)} == {i}" for i in range(1, n)} | {n: "senão"}
        m = re.fullmatch(r"\s*\((.+)\)\s*\+\s*1\s*", text)
        if m and n == 2 and "[" not in m.group(1):
            cond = tr(m.group(1))
            try:
                expr.parse(cond)
                return {2: cond, 1: "senão"}
            except expr.ExpressionError:
                return None
        m = re.fullmatch(r"\s*(.+?)\s*\?\s*1\s*:\s*2\s*", text)
        if m and n == 2 and "[" not in m.group(1):
            cond = tr(m.group(1))
            try:
                expr.parse(cond)
                return {1: cond, 2: "senão"}
            except expr.ExpressionError:
                return None
        return None

    def _settings(self) -> None:
        s, c = self.m.settings, self.c
        run = self._quantity(c.get("Simulation", "RunDuration"), True)
        if run is None or run <= 0:
            run = 8 * 3600 / self.factor
            self.notes.append("Duração da simulação não definida no JaamSim; usadas 8 h.")
        s.duration = round(run, 6)
        warm = self._quantity(c.get("Simulation", "InitializationDuration"), True)
        s.warmup = round(warm, 6) if warm and 0 < warm < run else 0.0
        reps = self._quantity(c.get("Simulation", "NumberOfReplications"), False)
        s.replications = max(1, int(reps)) if reps else 1
        seed = self._quantity(c.get("Simulation", "GlobalSubstreamSeed"), False)
        if seed is not None:
            s.seed = int(seed)

    # -------------------------------------------------------------------- layout
    def _layout(self) -> None:
        """Camadas da esquerda para a direita (como num IDEF-SIM), ordenadas pela posição no
        JaamSim; recursos abaixo da sua função."""
        m = self.m
        flow_nodes = [e.id for e in m.elements.values() if e.kind != EK.RESOURCE]
        succ = defaultdict(list)
        indeg = Counter()
        for cnx in m.connections.values():
            if cnx.kind == CK.FLOW:
                succ[cnx.source].append(cnx.target)
                indeg[cnx.target] += 1
        # remove arestas de retorno (DFS) para obter camadas
        order, state, back = [], {}, set()

        def dfs(u):
            stack = [(u, iter(succ[u]))]
            state[u] = 1
            while stack:
                v, it = stack[-1]
                nxt = next(it, None)
                if nxt is None:
                    state[v] = 2
                    order.append(v)
                    stack.pop()
                elif state.get(nxt) == 1:
                    back.add((v, nxt))
                elif nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter(succ[nxt])))
        roots = sorted([n for n in flow_nodes if indeg[n] == 0],
                       key=lambda n: -self.jpos.get(n, (0, 0))[1])
        for r in roots + flow_nodes:
            if r not in state:
                dfs(r)
        rank = {n: 0 for n in flow_nodes}
        for u in reversed(order):  # ordem topológica (sem as arestas de retorno)
            for v in succ[u]:
                if (u, v) not in back:
                    rank[v] = max(rank[v], rank[u] + 1)
        # linhas: cada nó tenta ficar na linha do seu antecessor; setas que saltam colunas
        # reservam as células do caminho, para nenhum símbolo ficar atravessado por elas
        preds = defaultdict(list)
        for u in succ:
            for v in succ[u]:
                if (u, v) not in back:
                    preds[v].append(u)
        occupied: dict[tuple[int, int], str] = {}
        row: dict[str, int] = {}
        topo = [n for n in reversed(order) if n in rank]
        topo.sort(key=lambda n: (rank[n], -self.jpos.get(n, (0, 0))[1]))

        def free(r0, r1, line):
            return all((c, line) not in occupied for c in range(r0, r1 + 1))
        for n in topo:
            ps = [p for p in preds[n] if p in row]
            wish = [row[p] for p in sorted(ps, key=lambda p: rank[p], reverse=True)] or [0]
            start = rank[ps[0]] + 1 if ps else rank[n]
            chosen = None
            for w in wish:
                for d in range(0, 60):
                    for line in ((w + d, w - d) if d else (w,)):
                        if line < 0:
                            continue
                        lo = min(start, rank[n]) if ps and row.get(ps[0]) == w else rank[n]
                        if free(lo, rank[n], line):
                            chosen = line
                            break
                    if chosen is not None:
                        break
                if chosen is not None:
                    break
            row[n] = chosen if chosen is not None else 0
            if ps and row[ps[0]] == row[n]:
                for c in range(rank[ps[0]] + 1, rank[n]):
                    occupied[(c, row[n])] = n
            occupied[(rank[n], row[n])] = n
        # altura das linhas: com funções que têm recursos, a linha seguinte desce para abrir
        # uma faixa onde os recursos ficam logo abaixo da sua função
        has_res = {row.get(c.target, 0) for c in m.connections.values() if c.kind == CK.RESOURCE}
        nrows = max(row.values(), default=0) + 1
        ys, y = [], 100.0
        for r in range(nrows):
            ys.append(y)
            y += DY + (RES_LANE if r in has_res else 0)
        for n in flow_nodes:
            m.elements[n].x = 80 + rank[n] * DX
            m.elements[n].y = ys[row.get(n, 0)]
        # recursos: abaixo da primeira função que os usa, sem sobrepor nenhum símbolo
        placed = [element_rect(e) for e in m.elements.values() if e.kind != EK.RESOURCE]
        for e in m.by_kind(EK.RESOURCE):
            users = [c.target for c in m.outgoing(e.id, CK.RESOURCE)]
            f = m.elements[users[0]] if users else None
            bx, by = (f.x, f.y + 105) if f else (80, y + 40)
            for dy in (0, 40, 80, 120, 160):
                cand = [(bx + dx, by + dy) for dx in (0, 135, -135, 270, -270)]
                spot = next((c for c in cand if not any(
                    overlaps(element_rect(e, *c), r) for r in placed)), None)
                if spot:
                    break
            e.x, e.y = spot or (bx, by)
            placed.append(element_rect(e))


def import_jaamsim_text(text: str, title: str = "Modelo JaamSim") -> ImportResult:
    cfg = Cfg(text)
    if not cfg.of_type("EntityGenerator", "EntityLauncher"):
        raise JaamSimImportError("O modelo não gera entidades (sem EntityGenerator): não há fluxo "
                                 "de entidades para representar em IDEF-SIM.")
    imp = _Importer(cfg, title)
    model = imp.build()
    known = {"EntityGenerator", "Server", "EntityProcessor", "EntityDelay", "EntityConveyor", "Queue",
             "EntityGate", "Branch", "Duplicate", "Combine", "Assemble", "EntitySink", "Resource",
             "EntityLauncher",
             "ResourcePool", "ResourceUnit", "SimEntity"} | PASS_THROUGH | VISUAL_FUNCTIONS
    flow_like = {t for t in cfg.types.values()
                 if t not in known and any(cfg.get(n, "NextComponent")
                                           for n, tt in cfg.types.items() if tt == t)}
    res = ImportResult(model, imp.notes)
    for t in flow_like:
        res.skipped_types[t] += 1
        imp.notes.append(f"Objetos do tipo {t} não foram convertidos.")
    return res


def import_jaamsim(path: str | Path) -> ImportResult:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^Title Format \{ '([^']*)' \}", text, re.M)
    return import_jaamsim_text(text, m.group(1) if m else p.stem)
