"""Fluxo entra pela esquerda e sai pela direita; setas de volta viram pares de conexões."""
from idefsim.examples import montagem, oficina_bombas, triagem_atributos, usinagem_inspecao
from idefsim.flow_rules import fix_backward_flows, is_backward
from idefsim.jaamsim_export import export_jaamsim
from idefsim.jaamsim_import import import_jaamsim_text
from idefsim.model import Connection, ConnectionKind as CK, ElementKind as EK, Model, new_id
from idefsim.simulation import run_simulation
from idefsim.validation import has_errors, validate


def _loop_model():
    m = Model()
    m.settings.duration, m.settings.replications = 600, 2
    e = m.add_element(EK.ENTITY, 0, 0, "Peça", interarrival="EXPO(5)")
    t = m.add_element(EK.FUNCTION, 200, 0, "Testar", duration="CONST(1)")
    ou = m.add_element(EK.RULE_OR, 360, 0)
    fim = m.add_element(EK.EXIT, 520, 0, "Fim")
    rt = m.add_element(EK.FUNCTION, 520, 160, "Retrabalhar", duration="CONST(2)")
    for a, b in ((e, t), (t, ou), (ou, fim), (ou, rt)):
        m.add_connection(CK.FLOW, a.id, b.id)
    for c in m.outgoing(ou.id):
        c.probability = 0.8 if m.elements[c.target].name == "Fim" else 0.2
    back = Connection(new_id(), CK.FLOW, rt.id, t.id)   # retrabalho → teste: volta para trás
    m.connections[back.id] = back
    return m, back


def test_backward_flow_becomes_connector_pair():
    m, back = _loop_model()
    assert is_backward(m, back)
    assert any("volta para trás" in i.message for i in validate(m))
    letters = fix_backward_flows(m)
    assert letters == ["A"] and back.id not in m.connections
    cons = m.by_kind(EK.CONNECTOR)
    assert sorted(c.name for c in cons) == ["A", "A"]
    assert not any(is_backward(m, c) for c in m.connections.values())
    assert not [i for i in validate(m) if "volta para trás" in i.message]
    rows = {(r.obj, r.metric): r.mean for r in run_simulation(m).rows()}
    assert rows[("Retrabalhar", "Atendimentos concluídos")] > 0   # o laço continua funcionando
    # a conexão da origem fica à direita dela; a do destino, à esquerda
    rt = next(e for e in m.elements.values() if e.name == "Retrabalhar")
    t = next(e for e in m.elements.values() if e.name == "Testar")
    c_out = m.elements[m.outgoing(rt.id)[0].target]
    c_in = m.elements[m.incoming(t.id)[-1].source] if m.elements[m.incoming(t.id)[-1].source].kind == EK.CONNECTOR \
        else next(m.elements[c.source] for c in m.incoming(t.id) if m.elements[c.source].kind == EK.CONNECTOR)
    assert c_out.x > rt.x and c_in.x < t.x


def test_probability_and_condition_kept():
    m = Model()
    e = m.add_element(EK.ENTITY, 300, 0)
    ou = m.add_element(EK.RULE_OR, 400, 0)
    ou.params["decision"] = "condition"
    a = m.add_element(EK.FUNCTION, 100, 0, "Atrás")
    b = m.add_element(EK.EXIT, 560, 0)
    m.add_connection(CK.FLOW, e.id, ou.id)
    c = m.add_connection(CK.FLOW, ou.id, a.id)
    c.condition, c.probability = "tipo == 1", 0.3
    m.add_connection(CK.FLOW, ou.id, b.id).condition = "senão"
    fix_backward_flows(m)
    to_con = [x for x in m.outgoing(ou.id) if m.elements[x.target].kind == EK.CONNECTOR][0]
    assert (to_con.condition, to_con.probability) == ("tipo == 1", 0.3)


def test_examples_have_no_backward_flows():
    for f in (usinagem_inspecao, montagem, triagem_atributos, oficina_bombas):
        m = f()
        assert not any(is_backward(m, c) for c in m.connections.values()), f.__name__
        assert not has_errors(validate(m))


def test_import_turns_loops_into_connectors():
    m0, _ = _loop_model()
    fix_backward_flows(m0)
    back = import_jaamsim_text(export_jaamsim(m0).text).model
    assert not any(is_backward(back, c) for c in back.connections.values())
    assert back.by_kind(EK.CONNECTOR)
