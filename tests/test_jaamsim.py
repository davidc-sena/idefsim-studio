"""Validação estrutural do .cfg gerado para o JaamSim.

As palavras-chave aceitas por tipo de objeto foram extraídas do código-fonte oficial do
JaamSim (com.jaamsim.ProcessFlow, ProbabilityDistributions, basicsim) e dos exemplos.
"""
import re

import pytest

from idefsim.examples import montagem, usinagem_inspecao
from idefsim.jaamsim_export import export_jaamsim, jaamsim_name
from idefsim.model import ConnectionKind as CK, ElementKind as EK, Model
from idefsim.validation import validate

DIST = {"UnitType", "RandomSeed", "MinValue", "MaxValue", "Location", "Scale"}
KEYWORDS = {
    "SimEntity": {"AttributeDefinitionList"},
    "Assign": {"NextComponent", "AttributeAssignmentList"},
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
    "GammaDistribution": DIST | {"Mean", "Shape"},
    "BetaDistribution": DIST | {"AlphaParam", "BetaParam"},
    "LogLogisticDistribution": DIST | {"Shape"},
    "ContinuousDistribution": DIST | {"ValueList", "CumulativeProbabilityList"},
    "PoissonDistribution": DIST | {"Mean"},
    "BinomialDistribution": DIST | {"NumberOfTrials", "Probability"},
    "GeometricDistribution": DIST | {"Probability"},
    "NegativeBinomialDistribution": DIST | {"SuccessfulTrials", "Probability"},
    "DiscreteUniformDistribution": DIST,
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
FLOW = {"EntityGenerator", "Assign", "EntityProcessor", "Seize", "Release", "EntityDelay", "EntityConveyor", "Branch",
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
            assert (tok[0] in types or re.match(r"^-?[\d.]+(e-?\d+)?$", tok[0])
                    or (key == "Choice" and val.startswith("'") and val.endswith("'"))), f"{obj} {key}: {val}"
        if key == "ProbabilityList":
            assert abs(sum(float(x) for x in val.split()) - 1) < 1e-6
        if key == "ValueList":
            vals = [v for v in val.split() if re.match(r"^-?[\d.]", v)]   # sem a unidade
            plist = "ProbabilityList" if types[obj] == "DiscreteDistribution" else \
                "CumulativeProbabilityList"
            probs = dict(((o, k), v) for o, k, v in kws)[(obj, plist)].split()
            assert len(vals) == len(probs)
    # referências [Objeto] e this.obj.atributo dentro de expressões
    defined_attrs = set()
    for obj, key, val in kws:
        if key == "AttributeDefinitionList":
            defined_attrs |= set(re.findall(r"\{ (\w+)  ", val))
    for obj, key, val in kws:
        for ref in re.findall(r"\[(\w+)\]", val):
            assert ref in types, f"{obj} {key}: [{ref}] não existe"
        for att in re.findall(r"this\.obj\.(\w+)", val):
            assert att in defined_attrs, f"{obj} {key}: atributo {att} não definido"
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



def _demo_attributes_model():
    m = Model(name="Triagem")
    ped = m.add_element(EK.ENTITY, 0, 200, "Pedido", interarrival="GAMM(4; 2)",
                        first_arrival="BETA(2; 3; 0; 5)")
    ped.params["attributes"] = [{"name": "tipo", "value": "DISC(1; 0,6; 2; 0,4)"},
                                {"name": "peso", "value": "NORM(12; 3)"},
                                {"name": "itens", "value": "POIS(3)"},
                                {"name": "fixo", "value": "-2"}]
    tri = m.add_element(EK.FUNCTION, 180, 200, "Triar", duration="LOGL(2; 3)")
    ou = m.add_element(EK.RULE_OR, 340, 200)
    ou.params["decision"] = "condition"
    leve = m.add_element(EK.FUNCTION, 500, 100, "Leve", duration="CONT(1; 0; 2; 0,5; 4; 1)")
    pes = m.add_element(EK.FUNCTION, 500, 300, "Pesado", duration="DISC(3; 0,5; 5; 0,5)")
    vis = m.add_element(EK.RULE_OR, 660, 200)
    vis.params.update(decision="visual", criterion="menor fila")
    a = m.add_element(EK.EXIT, 820, 100, "Doca A")
    b = m.add_element(EK.EXIT, 820, 300, "Doca B")
    for s_, t_ in ((ped, tri), (tri, ou), (leve, vis), (pes, vis), (vis, a), (vis, b)):
        m.add_connection(CK.FLOW, s_.id, t_.id)
    m.add_connection(CK.FLOW, ou.id, leve.id).condition = "tipo == 1 e peso < 15"
    m.add_connection(CK.FLOW, ou.id, pes.id).condition = "senão"
    return m


def test_attributes_conditions_and_visual_rule():
    res = export_jaamsim(_demo_attributes_model())
    types, kws = check(res.text)
    d = {(o, k): v for o, k, v in kws}
    assert d[("Pedido", "AttributeDefinitionList")] == "{ tipo  0 }  { peso  0 }  { itens  0 }  { fixo  0 }"
    asg = next(n for n, t in types.items() if t == "Assign")
    assert d[("Pedido_Chegada", "NextComponent")] == asg          # sorteia antes de seguir
    assert "'this.obj.tipo = [Pedido_tipo].Value'" in d[(asg, "AttributeAssignmentList")]
    assert "'this.obj.fixo = -2'" in d[(asg, "AttributeAssignmentList")]
    assert types["Pedido_itens"] == "PoissonDistribution"
    assert ("Pedido_itens", "UnitType") not in d                   # contagem: unidade fixa
    assert d[("Regra_OU_Branch", "Choice")] == \
        "'this.obj.tipo == 1 && this.obj.peso < 15 ? 1 : 2'"
    assert d[("Regra_OU_2_Branch", "Choice")] == "Regra_OU_2_Prob"   # visual: chances iguais
    assert d[("Regra_OU_2_Prob", "ProbabilityList")] == "0.5  0.5"
    assert any("menor fila" in w for w in res.warnings)
    assert types["Leve_Tempo"] == "ContinuousDistribution"
    assert d[("Leve_Tempo", "ValueList")] == "1  2  4  min"
    assert d[("Pesado_Tempo", "ProbabilityList")] == "0.5  0.5"
    assert d[("Pedido_Primeira_Tempo", "Location")] == "0  min"
    assert d[("Pedido_Primeira_Tempo", "Scale")] == "5  min"


def test_objects_are_spaced():
    import itertools
    for model in (usinagem_inspecao(), montagem(), _demo_attributes_model()):
        pts = [tuple(map(float, m.groups())) for m in re.finditer(
            r"Position \{ (-?[\d.e-]+)  (-?[\d.e-]+)  0.0  m \}", export_jaamsim(model).text)]
        closest = min(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                      for a, b in itertools.combinations(pts, 2))
        assert closest >= 1.0, f"objetos a {closest:.2f} m um do outro"


def _q_model():
    m = Model()
    e = m.add_element(EK.ENTITY, 0, 0, "Peca")
    q = m.add_element(EK.FUNCTION, 160, 0, "Aguardar torno", is_queue=True)
    f = m.add_element(EK.FUNCTION, 320, 0, "Tornear", duration="EXPO(4)")
    r = m.add_element(EK.RESOURCE, 320, 120, "Torno")
    x = m.add_element(EK.EXIT, 480, 0, "Fim")
    for a, b in ((e, q), (q, f), (f, x)):
        m.add_connection(CK.FLOW, a.id, b.id)
    m.add_connection(CK.RESOURCE, r.id, f.id)
    return m, q, x


def test_queue_function_is_waitqueue_of_next_processor():
    m, q, x = _q_model()
    types, kws = check(export_jaamsim(m).text)
    d = {(o, k): v for o, k, v in kws}
    assert types["Aguardar_torno"] == "Queue"
    assert d[("Peca_Chegada", "NextComponent")] == "Aguardar_torno"
    assert d[("Tornear", "WaitQueue")] == "Aguardar_torno"
    assert [n for n, t in types.items() if t == "Queue"] == ["Aguardar_torno"]  # nenhuma fila extra
    # fila sem processo depois: ignorada (passagem direta) com aviso
    for c in list(m.outgoing(q.id)):
        del m.connections[c.id]
    m.add_connection(CK.FLOW, q.id, x.id)
    res = export_jaamsim(m)
    types, kws = check(res.text)
    assert "Aguardar_torno" not in types
    assert dict(((o, k), v) for o, k, v in kws)[("Peca_Chegada", "NextComponent")] == "Fim"
    assert any("Aguardar torno" in w for w in res.warnings)


def test_functions_without_queue_function_keep_their_own_queue():
    """Só a função precedida por uma função-fila usa essa fila; as demais ganham a sua."""
    m, q, x = _q_model()
    tornear = next(e for e in m.elements.values() if e.name == "Tornear")
    for c in list(m.outgoing(tornear.id)):
        del m.connections[c.id]
    polir = m.add_element(EK.FUNCTION, 480, 0, "Polir", duration="EXPO(3)")
    m.add_connection(CK.FLOW, tornear.id, polir.id)
    m.add_connection(CK.FLOW, polir.id, x.id)
    types, kws = check(export_jaamsim(m).text)
    d = {(o, k): v for o, k, v in kws}
    assert d[("Tornear", "WaitQueue")] == "Aguardar_torno"
    assert d[("Polir", "WaitQueue")] == "Polir_Fila" and types["Polir_Fila"] == "Queue"
    assert d[("Tornear", "NextComponent")] == "Polir_Fila"
    # exemplo sem função-fila: toda função com tempo tem a sua fila
    types, kws = check(export_jaamsim(usinagem_inspecao()).text)
    d = {(o, k): v for o, k, v in kws}
    for f in ("Usinar", "Inspecionar", "Retrabalhar"):
        assert d[(f, "WaitQueue")] == f"{f}_Fila"


def _join_model(assemble: bool):
    """Dois ramos esperando um pelo outro no &: o de cima com função-fila, o de baixo sem."""
    m = Model()
    a = m.add_element(EK.ENTITY, 0, 0, "Base")
    b = m.add_element(EK.ENTITY, 0, 200, "Tampa")
    qa = m.add_element(EK.FUNCTION, 160, 0, "Aguardar base", is_queue=True)
    pb = m.add_element(EK.FUNCTION, 160, 200, "Preparar tampa", duration="2")
    j = m.add_element(EK.RULE_AND, 320, 100)
    x = m.add_element(EK.EXIT, 600, 100, "Fim")
    for s_, t_ in ((a, qa), (b, pb), (qa, j), (pb, j)):
        m.add_connection(CK.FLOW, s_.id, t_.id)
    if assemble:
        p = m.add_element(EK.ENTITY, 440, 100, "Produto")
        m.add_connection(CK.FLOW, j.id, p.id)
        m.add_connection(CK.FLOW, p.id, x.id)
    else:
        m.add_connection(CK.FLOW, j.id, x.id)
    return m


def test_queue_functions_are_the_waitqueues_of_assemble_and_combine():
    for assemble, kind in ((True, "Assemble"), (False, "Combine")):
        m = _join_model(assemble)
        assert not [i for i in validate(m) if "Aguardar" in i.message]
        types, kws = check(export_jaamsim(m).text)
        d = {(o, k): v for o, k, v in kws}
        obj = next(n for n, t in types.items() if t == kind)
        # ramo com função-fila usa a própria; ramo sem ganha uma fila do &
        assert d[(obj, "WaitQueueList")] == "Aguardar_base  Regra_E_Fila_2"
        assert d[("Base_Chegada", "NextComponent")] == "Aguardar_base"
        assert d[("Preparar_tampa", "NextComponent")] == "Regra_E_Fila_2"
