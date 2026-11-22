import pytest

from idefsim import distributions as dist
from idefsim.examples import montagem, usinagem_inspecao
from idefsim.model import ConnectionError_, ConnectionKind as CK, ElementKind as EK, Model
from idefsim.simulation import run_simulation
from idefsim.storage import load_model, save_model
from idefsim.validation import has_errors, validate


def test_parse_distributions():
    assert dist.parse("5").mean() == 5
    assert dist.parse("2,5").mean() == 2.5
    assert dist.parse("tria(1,2,3)").mean() == 2
    assert dist.parse("NORM(5; 0,5)").args == (5.0, 0.5)
    for bad in ("", "TRIA(3,2,1)", "FOO(1)", "EXPO(0)", "NORM(1)"):
        with pytest.raises(dist.DistributionError):
            dist.parse(bad)


def test_connection_rules():
    m = Model()
    e = m.add_element(EK.ENTITY)
    f = m.add_element(EK.FUNCTION)
    r = m.add_element(EK.RESOURCE)
    m.add_connection(CK.FLOW, e.id, f.id)
    c = m.add_connection(CK.RESOURCE, f.id, r.id)  # normalizado
    assert (c.source, c.target) == (r.id, f.id)
    with pytest.raises(ConnectionError_):
        m.add_connection(CK.FLOW, e.id, f.id)
    with pytest.raises(ConnectionError_):
        m.add_connection(CK.FLOW, r.id, f.id)
    m.remove_element(f.id)
    assert not m.connections


def test_roundtrip(tmp_path):
    m = usinagem_inspecao()
    p = tmp_path / "m.idefsim"
    save_model(m, p)
    m2 = load_model(p)
    assert m2.to_dict() == m.to_dict()


def test_validation_examples_ok():
    assert not has_errors(validate(usinagem_inspecao()))
    assert not has_errors(validate(montagem()))
    assert has_errors(validate(Model()))


def test_simulation_mm1_utilization():
    m = Model()
    m.settings.duration, m.settings.warmup, m.settings.replications = 20000, 1000, 3
    e = m.add_element(EK.ENTITY, interarrival="EXPO(10)")
    f = m.add_element(EK.FUNCTION, duration="EXPO(8)")
    r = m.add_element(EK.RESOURCE)
    x = m.add_element(EK.EXIT)
    m.add_connection(CK.FLOW, e.id, f.id)
    m.add_connection(CK.FLOW, f.id, x.id)
    m.add_connection(CK.RESOURCE, r.id, f.id)
    res = {(row.category, row.metric): row.mean for row in run_simulation(m).rows()}
    assert 75 < res[("Recurso", "Utilização (%)")] < 85        # ρ = 0.8
    assert 25 < res[("Sistema", "Tempo médio no sistema")] < 55  # W = 40


def test_simulation_examples_run():
    r = run_simulation(usinagem_inspecao())
    rows = {(x.obj, x.metric): x for x in r.rows()}
    assert rows[("Expedição", "Entidades")].mean > 0
    assert rows[("Retrabalhar", "Atendimentos concluídos")].mean > 0
    r2 = run_simulation(montagem())
    rows2 = {(x.obj, x.metric): x.mean for x in r2.rows()}
    assert rows2[("Produto", "Saídas")] > 0
    assert rows2[("Global", "Entidades consumidas em junções")] > 0
    assert "Categoria;Objeto" in r2.to_csv()


def test_resource_below_control_above():
    from idefsim.validation import INFO
    m = usinagem_inspecao()
    assert not [i for i in validate(m) if "notação IDEF-SIM" in i.message]
    torno = next(e for e in m.elements.values() if e.name == "Torno")
    torno.y = 0  # acima da função
    msgs = [i for i in validate(m) if "notação IDEF-SIM" in i.message]
    assert len(msgs) == 1 and msgs[0].level == INFO


def test_entry_arrow_on_entity():
    m = Model()
    e = m.add_element(EK.ENTITY, interarrival="CONST(5)")
    f = m.add_element(EK.FUNCTION, duration="CONST(1)")
    x = m.add_element(EK.EXIT)
    assert e.params["external_arrival"] is True          # entidade nova chega de fora
    m.add_connection(CK.FLOW, e.id, f.id)
    m.add_connection(CK.FLOW, f.id, x.id)
    assert not [i for i in validate(m) if "Fluxo de entrada" in i.message]
    e.params["external_arrival"] = False
    assert [i for i in validate(m) if "Fluxo de entrada" in i.message]
    prod = m.add_element(EK.ENTITY)
    m.add_connection(CK.FLOW, f.id, prod.id)             # entidade de transformação
    assert prod.params["external_arrival"] is False


def test_legacy_entry_connection_is_converted():
    m = Model()
    e = m.add_element(EK.ENTITY)
    f = m.add_element(EK.FUNCTION)
    m.add_connection(CK.FLOW, e.id, f.id)
    d = m.to_dict()
    d["connections"][0]["kind"] = "entry"
    for ed in d["elements"]:
        ed["params"].pop("external_arrival", None)
    m2 = Model.from_dict(d)
    c = next(iter(m2.connections.values()))
    assert c.kind == CK.FLOW and m2.elements[e.id].params["external_arrival"] is True


def test_arrow_heads_saved_and_defaults():
    m = usinagem_inspecao()
    ctrl = next(c for c in m.connections.values() if c.kind == CK.CONTROL)
    note = next(c for c in m.connections.values() if c.kind == CK.NOTE)
    assert ctrl.heads == (False, True) and note.heads == (False, False)   # padrões
    ctrl.head_end = False
    ctrl.head_start = True
    m2 = Model.from_dict(m.to_dict())
    assert m2.connections[ctrl.id].heads == (True, False)
    assert "head_end" not in m2.connections[note.id].to_dict()  # padrão não é gravado


def test_all_jaamsim_distributions_sample_near_mean():
    import random
    rng = random.Random(7)
    for t in ("GAMM(6; 2)", "BETA(2; 5; 1; 9)", "LOGL(4; 3)", "DISC(1; 0,3; 2; 0,7)",
              "CONT(2; 0; 4; 0,6; 9; 1)", "POIS(3)", "BINO(10; 0,2)", "GEOM(0,3)",
              "NBIN(2; 0,4)", "DUNI(1; 6)"):
        d = dist.parse(t, allow_negative=True)
        mean = sum(d.sample(rng, clip=False) for _ in range(20000)) / 20000
        assert mean == pytest.approx(d.mean(), rel=0.05), t
    with pytest.raises(dist.DistributionError):
        dist.parse("POIS(3)", for_time=True)          # contagem não serve como tempo
    with pytest.raises(dist.DistributionError):
        dist.parse("DISC(1; 0,5; 2; 0,4)")             # probabilidades não somam 1


def test_conditions_are_safe_and_translated():
    from idefsim import expressions as x
    assert x.evaluate("tipo == 1 e peso < 15", {"tipo": 1, "peso": 10})
    assert not x.evaluate("não (tipo == 1) ou peso > 20", {"tipo": 1, "peso": 10})
    assert x.to_jaamsim("tipo == 1 e peso < 15") == "this.obj.tipo == 1 && this.obj.peso < 15"
    for bad in ('__import__("os")', "tipo.x == 1", "open('f')"):
        with pytest.raises(x.ExpressionError):
            x.parse(bad)


def test_simulation_routes_by_attribute():
    from idefsim.examples import triagem_atributos
    m = triagem_atributos()
    m.settings.replications = 3
    rows = {(r.obj, r.metric): r.mean for r in run_simulation(m).rows()}
    leve, pesado = rows[("Embalar leve", "Atendimentos concluídos")], \
        rows[("Embalar pesado", "Atendimentos concluídos")]
    # P(tipo == 1 e peso < 15) = 0,6 · Φ(1) ≈ 0,505
    assert 0.40 < leve / (leve + pesado) < 0.60
    ou = next(e for e in m.elements.values() if e.kind == EK.RULE_OR)
    for c in m.outgoing(ou.id):
        c.condition = "tipo == 99" if "leve" in m.elements[c.target].name else "senão"
    rows = {(r.obj, r.metric): r.mean for r in run_simulation(m).rows()}
    assert rows.get(("Embalar leve", "Atendimentos concluídos"), 0) == 0


def test_connector_letters_pair_automatically():
    m = Model()
    names = [m.add_element(EK.CONNECTOR).name for _ in range(5)]
    assert names == ["A", "A", "B", "B", "C"]


def _queue_model(target_kind=EK.FUNCTION):
    m = Model()
    m.settings.duration, m.settings.replications = 2000, 2
    e = m.add_element(EK.ENTITY, 0, 0, "Peça", interarrival="EXPO(5)")
    q = m.add_element(EK.FUNCTION, 150, 0, "Aguardar torno", is_queue=True)
    f = m.add_element(target_kind, 300, 0, "Tornear", duration="EXPO(4)")
    r = m.add_element(EK.RESOURCE, 300, 120, "Torno")
    x = m.add_element(EK.EXIT, 450, 0, "Fim")
    for a, b in ((e, q), (q, f), (f, x)):
        m.add_connection(CK.FLOW, a.id, b.id)
    m.add_connection(CK.RESOURCE, r.id, f.id)
    return m, q, f


def test_queue_function_simulation():
    m, q, f = _queue_model()
    assert m.is_queue(q.id) and m.queue_feeds(q.id) == f.id
    assert not has_errors(validate(m))
    rows = {(r.category, r.obj, r.metric): r.mean for r in run_simulation(m).rows()}
    # a espera é a do processo alimentado; a fila não tem tempo próprio
    assert rows[("Fila", "Aguardar torno", "Tempo médio em fila")] == \
        rows[("Função", "Tornear", "Tempo médio em fila")]
    assert rows[("Fila", "Aguardar torno", "Entidades que entraram")] > 0
    assert ("Função", "Aguardar torno", "Atendimentos concluídos") not in rows


def test_queue_function_without_process_warns():
    m, q, f = _queue_model()
    for c in list(m.outgoing(q.id)):
        del m.connections[c.id]
    x = next(e for e in m.elements.values() if e.kind == EK.EXIT)
    m.add_connection(CK.FLOW, q.id, x.id)
    assert any("Fila 'Aguardar torno'" in str(i) for i in validate(m))
    run_simulation(m)   # passa direto, sem erro


def test_queue_before_and_measures_wait_for_other_parts():
    from idefsim.examples import montagem
    m = montagem()
    m.settings.replications = 2
    rows = {(r.category, r.obj, r.metric): r.mean for r in run_simulation(m).rows()}
    wb = rows[("Fila", "Aguardar base", "Tempo médio em fila")]
    wt = rows[("Fila", "Aguardar tampa", "Tempo médio em fila")]
    assert wb >= 0 and wt >= 0 and (wb + wt) > 0
    assert rows[("Fila", "Aguardar tampa", "Fila máxima")] >= 1
    assert not has_errors(validate(m))
