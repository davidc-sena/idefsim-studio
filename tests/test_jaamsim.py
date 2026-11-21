"""Validação estrutural do .cfg gerado para o JaamSim.

As palavras-chave aceitas por tipo de objeto foram extraídas do código-fonte oficial do
JaamSim (com.jaamsim.ProcessFlow, ProbabilityDistributions, basicsim) e dos exemplos.
"""
import re

import pytest

from idefsim.examples import montagem, usinagem_inspecao
from idefsim.jaamsim_export import export_jaamsim, jaamsim_name
from idefsim.model import ConnectionKind as CK, ElementKind as EK, Model

DIST = {"UnitType", "RandomSeed", "MinValue", "MaxValue", "Location", "Scale"}
KEYWORDS = {
    "SimEntity": set(),
    "EntityGenerator": {"NextComponent", "FirstArrivalTime", "InterArrivalTime",
                        "EntitiesPerArrival", "PrototypeEntity", "MaxNumber", "BaseName"},
    "Queue": set(),
    "EntityProcessor": {"NextComponent", "WaitQueue", "ResourceList", "NumberOfUnits",
                        "Capacity", "ServiceTime"},
    "Seize": {"NextComponent", "WaitQueue", "ResourceList", "NumberOfUnits"},
    "Release": {"NextComponent", "ResourceList", "NumberOfUnits"},
    "Resource": {"Capacity"},
    "EntityDelay": {"NextComponent", "Duration"},
    "EntityConveyor": {"NextComponent", "TravelTime"},
    "Branch": {"NextComponentList", "Choice"},
    "Duplicate": {"NextComponent", "TargetComponentList"},
    "Combine": {"NextComponent", "WaitQueueList", "ServiceTime"},
    "Assemble": {"NextComponent", "WaitQueueList", "PrototypeEntity", "ServiceTime"},
    "EntitySink": set(),
    "ExponentialDistribution": DIST | {"Mean"},
    "NormalDistribution": DIST | {"Mean", "StandardDeviation"},
    "TriangularDistribution": DIST | {"Mode"},
    "UniformDistribution": DIST,
    "LogNormalDistribution": DIST | {"NormalMean", "NormalStandardDeviation"},
    "ErlangDistribution": DIST | {"Mean", "Shape"},
    "WeibullDistribution": DIST | {"Shape"},
    "DiscreteDistribution": DIST | {"ValueList", "ProbabilityList"},
    "Text": {"Format", "TextHeight"},
    "View": {"Description", "ViewCenter", "ViewPosition", "ShowWindow", "Lock2D"},
    "OverlayText": {"ScreenPosition", "TextHeight", "Format"},
    "Simulation": {"Description", "RunDuration", "InitializationDuration", "NumberOfReplications",
                   "GlobalSubstreamSeed", "PrintReport", "DisplayedUnits", "RealTime",
                   "ShowLabels", "ShowModelBuilder", "ShowObjectSelector", "ShowInputEditor",
                   "ShowOutputViewer"},
}
GRAPHICS = {"Position", "Points"}
REFS = {"NextComponent": "flow", "NextComponentList": "flow", "TargetComponentList": "flow",
        "WaitQueue": "Queue", "WaitQueueList": "Queue", "ResourceList": "Resource",
        "PrototypeEntity": "SimEntity"}
FLOW = {"EntityGenerator", "EntityProcessor", "Seize", "Release", "EntityDelay", "EntityConveyor", "Branch",
        "Duplicate", "Combine", "Assemble", "EntitySink", "Queue"}
INVALID = set(" \t\n{}'\"[]#.")


def parse(cfg: str):
    types, kws = {"Simulation": "Simulation"}, []
    for line in cfg.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line == "RecordEdits":
            continue
        m = re.match(r"^Define (\w+) \{ (.*) \}$", line)
        if m:
            for n in m.group(2).split():
                assert n not in types, f"objeto definido duas vezes: {n}"
                types[n] = m.group(1)
            continue
        m = re.match(r"^(\S+) (\w+) \{ (.*) \}$", line)
        assert m, f"linha fora da sintaxe 'Objeto Palavra {{ valor }}': {line}"
        kws.append((m.group(1), m.group(2), m.group(3)))
    return types, kws


def check(cfg: str):
    assert cfg.isascii(), "o .cfg deve ser ASCII puro"
    types, kws = parse(cfg)
    for name in types:
        assert not (set(name) & INVALID), f"nome inválido no JaamSim: {name}"
    used_queues = []
    nexts = {}
    for obj, key, val in kws:
        assert obj in types, f"palavra-chave para objeto não definido: {obj}"
        t = types[obj]
        assert key in KEYWORDS[t] | GRAPHICS, f"{t} não tem a palavra-chave {key}"
        if key in REFS:
            for ref in val.split():
                assert ref in types, f"{obj} {key} refere objeto inexistente: {ref}"
                want = REFS[key]
                assert (types[ref] in FLOW) if want == "flow" else types[ref] == want, \
                    f"{obj} {key}: {ref} é {types[ref]}"
            if key in ("WaitQueue", "WaitQueueList"):
                used_queues += val.split()
                for q in val.split():  # o consumidor puxa as entidades da fila
                    nexts.setdefault(q, []).append(obj)
            if key in ("NextComponent", "NextComponentList", "TargetComponentList"):
                nexts.setdefault(obj, []).extend(val.split())
        if key in ("Duration", "TravelTime", "InterArrivalTime", "FirstArrivalTime", "Choice",
                   "ServiceTime"):
            tok = val.split()
            assert tok[0] in types or re.match(r"^-?[\d.]+(e-?\d+)?$", tok[0]), f"{obj} {key}: {val}"
        if key == "ProbabilityList":
            assert abs(sum(float(x) for x in val.split()) - 1) < 1e-6
        if key == "ValueList":
            vals = val.split()
            probs = dict(((o, k), v) for o, k, v in kws)[(obj, "ProbabilityList")].split()
            assert len(vals) == len(probs)
    queues = [n for n, t in types.items() if t == "Queue"]
    assert sorted(queues) == sorted(used_queues), "cada Queue deve ser usada por exatamente um objeto"
    # toda saída de fluxo alcança um EntitySink
    sinks = {n for n, t in types.items() if t == "EntitySink"}
    for g in [n for n, t in types.items() if t == "EntityGenerator"]:
        seen, stack = set(), [g]
        while stack:
            o = stack.pop()
            if o in seen:
                continue
            seen.add(o)
            stack += nexts.get(o, [])
        assert seen & sinks, f"entidades de {g} não chegam a nenhum EntitySink"
    return types, kws


def test_examples_generate_valid_cfg():
    for model in (usinagem_inspecao(), montagem()):
        types, _ = check(export_jaamsim(model).text)
        assert "EntityGenerator" in types.values()


def test_machining_mapping():
    types, kws = check(export_jaamsim(usinagem_inspecao()).text)
    d = {(o, k): v for o, k, v in kws}
    assert types["Usinar"] == "EntityProcessor"
    assert d[("Usinar", "WaitQueue")] == "Usinar_Fila"
    assert d[("Usinar", "ResourceList")] == "Torno"
    assert d[("Usinar", "Capacity")] == "1"
    assert d[("Usinar", "ServiceTime")] == "Usinar_Tempo"
    assert d[("Peca_Chegada", "NextComponent")] == "Usinar_Fila"   # entra pela fila
    assert "EntityDelay" not in types.values()
    assert d[("Regra_OU_Branch", "NextComponentList")] == "Expedicao  Retrabalhar_Fila"
    assert d[("Regra_OU_Prob", "ProbabilityList")] == "0.9  0.1"
    assert d[("Retrabalhar", "NextComponent")] == "Inspecionar_Fila"    # laço de retrabalho
    assert d[("Retrabalhar", "Capacity")] == "1000000"                  # sem recurso: ilimitada
    assert types["Transportar"] == "EntityConveyor"
    assert d[("Simulation", "RunDuration")] == "480  min"
    assert d[("Simulation", "InitializationDuration")] == "60  min"


def test_assembly_mapping():
    types, kws = check(export_jaamsim(montagem()).text)
    d = {(o, k): v for o, k, v in kws}
    asm = next(n for n, t in types.items() if t == "Assemble")
    assert d[(asm, "PrototypeEntity")] == "Produto"
    assert len(d[(asm, "WaitQueueList")].split()) == 2


def test_all_elements_and_distributions():
    m = Model(name="Todos os símbolos")
    m.settings.time_unit = "h"
    e = m.add_element(EK.ENTITY, 0, 0, "Pedido Nº 1", interarrival="LOGN(5, 2)",
                      first_arrival="UNIF(0, 1)", batch_size=2, max_arrivals=50)
    f = m.add_element(EK.FUNCTION, 150, 0, "Triagem", duration="WEIB(3, 2)")
    split = m.add_element(EK.RULE_AND, 250, 0)
    a = m.add_element(EK.FUNCTION, 350, -80, "Ramo A", duration="ERLA(4, 2)")
    b = m.add_element(EK.MOVEMENT, 350, 80, "Levar B", duration="2")
    join = m.add_element(EK.RULE_AND, 450, 0)
    eo = m.add_element(EK.RULE_ANDOR, 550, 0)
    c1 = m.add_element(EK.CONNECTOR, 650, -60, "A")
    c2 = m.add_element(EK.CONNECTOR, 650, 200, "A")
    g = m.add_element(EK.FUNCTION, 750, 200, "Embalar", duration="NORM(1, 0.2)")
    h = m.add_element(EK.FUNCTION, 750, 60, "Beco sem saída", duration="1")
    x = m.add_element(EK.EXIT, 900, 200, "Fim")
    r = m.add_element(EK.RESOURCE, 150, 100, "Operador [turno A]", capacity=2)
    r2 = m.add_element(EK.RESOURCE, 350, 160, "Empilhadeira")
    ctl = m.add_element(EK.CONTROL, 150, -100, "Ordem 'urgente'")
    note = m.add_element(EK.NOTE, 300, -150, "Nota # com {chaves}")
    for s_, t_ in ((e, f), (f, split), (split, a), (split, b), (a, join), (b, join), (join, eo),
                   (eo, c1), (eo, h), (c2, g), (g, x)):
        m.add_connection(CK.FLOW, s_.id, t_.id)
    m.add_connection(CK.RESOURCE, r.id, f.id)
    m.add_connection(CK.RESOURCE, r2.id, b.id)
    m.add_connection(CK.CONTROL, ctl.id, f.id)
    m.add_connection(CK.NOTE, note.id, f.id)
    res = export_jaamsim(m)
    types, kws = check(res.text)
    d = {(o, k): v for o, k, v in kws}
    kinds = set(types.values())
    for t in ("Duplicate", "Combine", "LogNormalDistribution", "WeibullDistribution",
              "ErlangDistribution", "NormalDistribution", "UniformDistribution", "EntityConveyor",
              "Text", "Branch"):
        assert t in kinds, t
    assert d[("Simulation", "RunDuration")].endswith(" h")
    assert d[("Triagem", "Capacity")] == "2"          # menor capacidade dos recursos
    assert d[("Pedido_No_1_Chegada", "EntitiesPerArrival")] == "2"
    assert d[("Pedido_No_1_Chegada", "MaxNumber")] == "50"
    assert "Embalar" in res.text and "Beco_sem_saida_Saida" in types   # sink automático
    assert any("E/OU" in w for w in res.warnings)
    assert any("Beco sem saída" in w for w in res.warnings)
    # log-normal: parâmetros da normal subjacente reproduzem média 5 e desvio 2
    import math
    ln = next(n for n, t in types.items() if t == "LogNormalDistribution")
    mu, sg = float(d[(ln, "NormalMean")]), float(d[(ln, "NormalStandardDeviation")])
    assert math.exp(mu + sg * sg / 2) == pytest.approx(5, rel=1e-4)
    assert math.exp(mu + sg * sg / 2) * math.sqrt(math.exp(sg * sg) - 1) == pytest.approx(2, rel=1e-4)


def test_name_sanitizing():
    assert jaamsim_name("Peça usinada #2 [lote].x") == "Peca_usinada_2_lote_x"
    assert jaamsim_name("1ª etapa") == "N1a_etapa"
