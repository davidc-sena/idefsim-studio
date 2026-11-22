"""Importação de modelos do JaamSim (.cfg) para IDEF-SIM."""
import pytest

from idefsim.examples import examples_dir, montagem, triagem_atributos, usinagem_inspecao
from idefsim.jaamsim_export import export_jaamsim
from idefsim.jaamsim_import import JaamSimImportError, import_jaamsim_text
from idefsim.model import ConnectionKind as CK, ElementKind as EK
from idefsim.simulation import run_simulation
from idefsim.storage import load_model
from idefsim.validation import has_errors, validate


def _by_name(m):
    return {e.name: e for e in m.elements.values()}


SERVER_QUEUE = """
RecordEdits
Define ExponentialDistribution { IATDistribution }
Define InputValue { ServiceTimeInput }
Define EntityGenerator { Generator }
Define Queue { Queue1 }
Define Server { Server1 }
Define EntitySink { Sink }
Define SimEntity { Part }
IATDistribution UnitType { TimeUnit }
Simulation RunDuration { 2  h }
ServiceTimeInput Value { 51  s }
IATDistribution Mean { 1  min }
Generator NextComponent { Server1 }
Generator InterArrivalTime { IATDistribution }
Generator PrototypeEntity { Part }
Server1 NextComponent { Sink }
Server1 WaitQueue { Queue1 }
Server1 ServiceTime { ServiceTimeInput }
Generator Position { 0  0  0  m }
"""


def test_server_and_queue():
    r = import_jaamsim_text(SERVER_QUEUE, "Servidor")
    m = r.model
    n = _by_name(m)
    assert m.settings.time_unit in ("s", "min") and not has_errors(validate(m))
    unit = 60 if m.settings.time_unit == "s" else 1
    assert n["Part"].params["interarrival"] == f"EXPO({unit:g})"          # 1 min
    assert m.is_queue(n["Queue1"].id)                                      # Queue → função-fila
    assert m.queue_feeds(n["Queue1"].id) == n["Server1"].id                # entra pela fila
    assert m.outgoing(n["Part"].id)[0].target == n["Queue1"].id
    res = m.resources_of(n["Server1"].id)                                   # Server: capacidade 1
    assert len(res) == 1 and res[0].params["capacity"] == 1
    assert m.settings.duration == pytest.approx(2 * 3600 / (60 / unit))    # InputValue resolvido:
    assert "51" in n["Server1"].params["duration"] or "0,85" in n["Server1"].params["duration"]
    run_simulation(m)


def test_seize_release_and_assemble():
    cfg = """
Define EntityGenerator { G1  G2 }
Define SimEntity { Base  Tampa  Produto }
Define Seize { Seize1 }
Define Release { Release1 }
Define Resource { Montador }
Define EntityDelay { Montar }
Define Queue { QB  QT  QS }
Define Assemble { Juntar }
Define Assign { Marcar }
Define EntitySink { Fim }
Simulation RunDuration { 100  s }
Montador Capacity { 2 }
G1 NextComponent { QB }
G1 PrototypeEntity { Base }
G2 NextComponent { QT }
G2 PrototypeEntity { Tampa }
Juntar WaitQueueList { QB  QT }
Juntar PrototypeEntity { Produto }
Juntar NextComponent { Marcar }
Marcar NextComponent { Seize1 }
Seize1 WaitQueue { QS }
Seize1 ResourceList { Montador }
Seize1 NextComponent { Montar }
Montar Duration { 5  s }
Montar NextComponent { Release1 }
Release1 ResourceList { Montador }
Release1 NextComponent { Fim }
"""
    m = import_jaamsim_text(cfg, "Montagem").model
    n = _by_name(m)
    assert not has_errors(validate(m))
    j = next(e for e in m.elements.values() if e.kind == EK.RULE_AND)
    assert {m.elements[c.source].name for c in m.incoming(j.id)} == {"QB", "QT"}
    assert m.elements[m.outgoing(j.id)[0].target].name == "Produto"          # Assemble → nova entidade
    assert "Marcar" not in n and "Seize1" not in n and "Release1" not in n   # sem símbolo IDEF-SIM
    assert [r.name for r in m.resources_of(n["Montar"].id)] == ["Montador"]  # Seize/Release
    assert n["Montador"].params["capacity"] == 2
    run_simulation(m)


def test_roundtrip_of_own_examples():
    for model in (usinagem_inspecao(), montagem(), triagem_atributos()):
        back = import_jaamsim_text(export_jaamsim(model).text, model.name).model
        assert not has_errors(validate(back)), model.name
        funcs = {e.name for e in model.by_kind(EK.FUNCTION) if not e.params.get("is_queue")}
        back_funcs = {e.name for e in back.by_kind(EK.FUNCTION) if not back.is_queue(e.id)}
        assert {f.replace(" ", "") for f in funcs} <= {f.replace(" ", "") for f in back_funcs}
    back = import_jaamsim_text(export_jaamsim(usinagem_inspecao()).text).model
    ou = next(e for e in back.by_kind(EK.RULE_OR))
    assert sorted(c.probability for c in back.outgoing(ou.id)) == [0.1, 0.9]
    back = import_jaamsim_text(export_jaamsim(triagem_atributos()).text).model
    peds = [e for e in back.by_kind(EK.ENTITY) if e.params.get("attributes")]
    assert {a["name"] for a in peds[0].params["attributes"]} == {"tipo", "peso"}


def test_choice_by_attribute_becomes_condition():
    cfg = """
Define EntityGenerator { G }
Define SimEntity { Peca }
Define Branch { B }
Define EntitySink { Bom  Ruim }
Peca AttributeDefinitionList { { GoodPart  1 } }
G NextComponent { B }
G PrototypeEntity { Peca }
B NextComponentList { Bom  Ruim }
B Choice { this.obj.GoodPart }
"""
    m = import_jaamsim_text(cfg).model
    ou = next(e for e in m.by_kind(EK.RULE_OR))
    assert m.decision_of(ou.id) == "condition"
    conds = {m.elements[c.target].name: c.condition for c in m.outgoing(ou.id)}
    assert conds == {"Bom": "GoodPart == 1", "Ruim": "senão"}
    assert not has_errors(validate(m))


def test_model_without_entities_is_refused():
    with pytest.raises(JaamSimImportError):
        import_jaamsim_text("Define SineWave { S }\nS Amplitude { 1 }\n")


def test_bundled_jaamsim_examples_open_and_validate():
    files = sorted((examples_dir() / "jaamsim_oficiais").glob("*/*.idefsim"))
    assert len(files) >= 80
    for f in files:
        m = load_model(f)
        assert not has_errors(validate(m)), f.name
        assert "Apache License 2.0" in m.description
    assert (examples_dir() / "jaamsim_oficiais" / "LICENSE-JaamSim.txt").exists()
