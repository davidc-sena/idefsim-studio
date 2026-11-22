"""Modelos de exemplo."""
from __future__ import annotations

import sys
from pathlib import Path

from . import AUTHOR
from .model import ConnectionKind as CK, ElementKind as EK, Model


def usinagem_inspecao() -> Model:
    """Célula de usinagem com inspeção e retrabalho (10% de rejeição)."""
    m = Model(name="Célula de usinagem com inspeção", author=AUTHOR,
              description="Peças chegam, são usinadas no torno, transportadas até a "
                          "inspeção; 10% seguem para retrabalho e voltam à inspeção.")
    m.settings.duration, m.settings.warmup, m.settings.replications = 480, 60, 10
    peca = m.add_element(EK.ENTITY, 60, 200, "Peça", interarrival="EXPO(6)")
    usin = m.add_element(EK.FUNCTION, 220, 200, "Usinar", duration="TRIA(3, 4.5, 6)")
    torno = m.add_element(EK.RESOURCE, 220, 320, "Torno", capacity=1)
    ctrl = m.add_element(EK.CONTROL, 220, 80, "Plano de produção")
    mov = m.add_element(EK.MOVEMENT, 400, 200, "Transportar", duration="UNIF(1, 2)")
    oper = m.add_element(EK.RESOURCE, 400, 320, "Operador logístico", capacity=1)
    insp = m.add_element(EK.FUNCTION, 580, 200, "Inspecionar", duration="NORM(4; 0,5)")
    inspetor = m.add_element(EK.RESOURCE, 580, 320, "Inspetor", capacity=1)
    regra = m.add_element(EK.RULE_OR, 720, 200)
    fim = m.add_element(EK.EXIT, 860, 200, "Expedição")
    retr = m.add_element(EK.FUNCTION, 720, 420, "Retrabalhar", duration="EXPO(8)")
    nota = m.add_element(EK.NOTE, 880, 80, "Taxa de rejeição histórica: 10%")
    m.add_connection(CK.FLOW, peca.id, usin.id)
    m.add_connection(CK.FLOW, usin.id, mov.id)
    m.add_connection(CK.FLOW, mov.id, insp.id)
    m.add_connection(CK.FLOW, insp.id, regra.id)
    m.add_connection(CK.FLOW, regra.id, fim.id, probability=0.9)
    m.add_connection(CK.FLOW, regra.id, retr.id, probability=0.1)
    m.add_connection(CK.FLOW, retr.id, insp.id)
    m.add_connection(CK.RESOURCE, torno.id, usin.id)
    m.add_connection(CK.RESOURCE, oper.id, mov.id)
    m.add_connection(CK.RESOURCE, inspetor.id, insp.id)
    m.add_connection(CK.CONTROL, ctrl.id, usin.id)
    m.add_connection(CK.NOTE, nota.id, regra.id)
    return m


def montagem() -> Model:
    """Montagem: base e tampa esperam uma pela outra (filas antes do &) e formam o produto."""
    m = Model(name="Montagem com junção E", author=AUTHOR,
              description="Base e tampa são preparadas em paralelo e esperam uma pela outra "
                          "nas filas antes da junção E; juntas formam o Produto, que é montado.")
    m.settings.duration, m.settings.replications = 600, 5
    base = m.add_element(EK.ENTITY, 60, 120, "Base", interarrival="EXPO(5)")
    tampa = m.add_element(EK.ENTITY, 60, 300, "Tampa", interarrival="EXPO(5)")
    pb = m.add_element(EK.FUNCTION, 220, 120, "Preparar base", duration="TRIA(2, 3, 4)")
    pt = m.add_element(EK.FUNCTION, 220, 300, "Preparar tampa", duration="TRIA(1, 2, 3)")
    qb = m.add_element(EK.FUNCTION, 390, 120, "Aguardar base", is_queue=True)
    qt = m.add_element(EK.FUNCTION, 390, 300, "Aguardar tampa", is_queue=True)
    j = m.add_element(EK.RULE_AND, 530, 210)
    prod = m.add_element(EK.ENTITY, 630, 210, "Produto")
    mont = m.add_element(EK.FUNCTION, 770, 210, "Montar", duration="NORM(3.5, 0.4)")
    mont_r = m.add_element(EK.RESOURCE, 770, 330, "Montador", capacity=1)
    fim = m.add_element(EK.EXIT, 930, 210, "Armazém")
    for a, b in ((base, pb), (tampa, pt), (pb, qb), (pt, qt), (qb, j), (qt, j), (j, prod),
                 (prod, mont), (mont, fim)):
        m.add_connection(CK.FLOW, a.id, b.id)
    m.add_connection(CK.RESOURCE, mont_r.id, mont.id)
    return m


def triagem_atributos() -> Model:
    """Pedidos com atributos (tipo, peso): regra OU por condição e regra OU apenas visual."""
    m = Model(name="Triagem de pedidos por atributos", author=AUTHOR,
              description="Pedidos leves do tipo 1 seguem para a embalagem leve; os demais para "
                          "a pesada. A escolha da doca é só documentada (menor fila).")
    m.settings.duration, m.settings.replications = 480, 5
    ped = m.add_element(EK.ENTITY, 60, 200, "Pedido", interarrival="EXPO(4)")
    ped.params["attributes"] = [{"name": "tipo", "value": "DISC(1; 0,6; 2; 0,4)"},
                                {"name": "peso", "value": "NORM(12; 3)"}]
    tri = m.add_element(EK.FUNCTION, 220, 200, "Triar", duration="UNIF(1; 2)")
    triador = m.add_element(EK.RESOURCE, 220, 320, "Triador", capacity=1)
    ou = m.add_element(EK.RULE_OR, 370, 200)
    ou.params["decision"] = "condition"
    leve = m.add_element(EK.FUNCTION, 530, 100, "Embalar leve", duration="TRIA(2; 3; 4)")
    pes = m.add_element(EK.FUNCTION, 530, 300, "Embalar pesado", duration="GAMM(6; 2)")
    emb = m.add_element(EK.RESOURCE, 530, 420, "Embalador", capacity=2)
    doca = m.add_element(EK.RULE_OR, 690, 200)
    doca.params.update(decision="visual", criterion="menor fila")
    d1 = m.add_element(EK.EXIT, 850, 120, "Doca 1")
    d2 = m.add_element(EK.EXIT, 850, 280, "Doca 2")
    for a, b in ((ped, tri), (tri, ou), (leve, doca), (pes, doca), (doca, d1), (doca, d2)):
        m.add_connection(CK.FLOW, a.id, b.id)
    m.add_connection(CK.FLOW, ou.id, leve.id).condition = "tipo == 1 e peso < 15"
    m.add_connection(CK.FLOW, ou.id, pes.id).condition = "senão"
    m.add_connection(CK.RESOURCE, triador.id, tri.id)
    m.add_connection(CK.RESOURCE, emb.id, pes.id)
    return m


def oficina_bombas() -> Model:
    """Exemplo do manual: usa todos os símbolos e funções do IDEF-SIM Studio."""
    m = Model(name="Oficina de manutenção de bombas", author=AUTHOR, version="1.0",
              description="Bombas com defeito chegam à oficina, esperam e são inspecionadas. "
                          "As simples e não urgentes têm reparo simples; as demais aguardam um kit "
                          "de peças, que é montado na bomba (reparo complexo). Todas são testadas "
                          "(15% passam por retrabalho e voltam ao teste), recebem laudo e limpeza em paralelo, são "
                          "transportadas à expedição e saem por uma das docas; 30% dos clientes "
                          "recebem pesquisa de satisfação.")
    s = m.settings
    s.time_unit, s.duration, s.warmup, s.replications, s.seed = "min", 2400, 240, 10, 2026
    add, flow = m.add_element, lambda a, b: m.add_connection(CK.FLOW, a.id, b.id)
    # --- chegada, fila e inspeção
    bomba = add(EK.ENTITY, 60, 200, "Bomba com defeito", interarrival="EXPO(30)")
    bomba.params["attributes"] = [{"name": "tipo", "value": "DISC(1; 0,6; 2; 0,4)"},
                                  {"name": "urgente", "value": "DISC(0; 0,8; 1; 0,2)"}]
    q_insp = add(EK.FUNCTION, 220, 200, "Aguardar inspeção", is_queue=True)
    insp = add(EK.FUNCTION, 390, 200, "Inspecionar", duration="TRIA(10; 15; 25)")
    tecnico = add(EK.RESOURCE, 390, 320, "Técnico", capacity=2)
    proc = add(EK.CONTROL, 390, 80, "Procedimento de inspeção")
    # --- decisão por atributo
    ou_tipo = add(EK.RULE_OR, 540, 200)
    ou_tipo.params["decision"] = "condition"
    simples = add(EK.FUNCTION, 700, 90, "Reparo simples", duration="UNIF(20; 40)")
    q_bomba = add(EK.FUNCTION, 700, 330, "Aguardar kit", is_queue=True)
    # --- kit de peças e montagem (junção E com nova entidade)
    kit = add(EK.ENTITY, 540, 520, "Kit de peças", interarrival="EXPO(55)", arrival_side="bottom")
    q_kit = add(EK.FUNCTION, 700, 520, "Aguardar bomba", is_queue=True)
    junta = add(EK.RULE_AND, 850, 425)
    montada = add(EK.ENTITY, 950, 425, "Bomba com kit")
    complexo = add(EK.FUNCTION, 1090, 425, "Reparo complexo", duration="GAMM(60; 3)")
    mecanico = add(EK.RESOURCE, 1090, 545, "Mecânico", capacity=2)
    nota = add(EK.NOTE, 300, 520, "Kits vêm do almoxarifado central")
    # --- teste e retrabalho
    teste = add(EK.FUNCTION, 1250, 200, "Testar", duration="NORM(10; 2)")
    bancada = add(EK.RESOURCE, 1250, 320, "Bancada de teste", capacity=1)
    ou_teste = add(EK.RULE_OR, 1400, 200)
    retrab = add(EK.FUNCTION, 1400, 340, "Retrabalhar", duration="UNIF(10; 20)")
    # --- laudo e limpeza em paralelo (divisão e junção E)
    divide = add(EK.RULE_AND, 1540, 200)
    laudo = add(EK.FUNCTION, 1680, 90, "Emitir laudo", duration="CONST(5)")
    limpar = add(EK.FUNCTION, 1680, 310, "Limpar e pintar", duration="TRIA(10; 15; 20)")
    reune = add(EK.RULE_AND, 1820, 200)
    transp = add(EK.MOVEMENT, 1970, 200, "Transportar à expedição", duration="UNIF(3; 6)")
    empilh = add(EK.RESOURCE, 1970, 320, "Empilhadeira", capacity=1)
    con_a1 = add(EK.CONNECTOR, 2110, 200)
    # --- expedição (continua na linha de baixo pela conexão A)
    con_a2 = add(EK.CONNECTOR, 1250, 700)
    eou = add(EK.RULE_ANDOR, 1400, 700)
    doca = add(EK.RULE_OR, 1540, 640)
    doca.params.update(decision="visual", criterion="doca livre")
    doca1 = add(EK.EXIT, 1700, 580, "Doca 1")
    doca2 = add(EK.EXIT, 1700, 700, "Doca 2")
    pesquisa = add(EK.FUNCTION, 1540, 800, "Enviar pesquisa", duration="CONST(2)")
    contato = add(EK.EXIT, 1700, 800, "Cliente contatado")
    for a, b in ((bomba, q_insp), (q_insp, insp), (insp, ou_tipo), (q_bomba, junta), (kit, q_kit),
                 (q_kit, junta), (junta, montada), (montada, complexo), (simples, teste),
                 (complexo, teste), (teste, ou_teste), (divide, laudo), (divide, limpar),
                 (laudo, reune), (limpar, reune), (reune, transp), (transp, con_a1),
                 (con_a2, eou), (doca, doca1), (doca, doca2), (pesquisa, contato)):
        flow(a, b)
    flow(ou_tipo, simples).condition = "tipo == 1 e urgente == 0"
    flow(ou_tipo, q_bomba).condition = "senão"
    flow(ou_teste, divide).probability = 0.85
    flow(ou_teste, retrab).probability = 0.15
    flow(retrab, teste)
    flow(eou, doca).probability = 1.0
    flow(eou, pesquisa).probability = 0.3
    for r, f in ((tecnico, insp), (mecanico, complexo), (bancada, teste),
                 (empilh, transp)):
        m.add_connection(CK.RESOURCE, r.id, f.id)
    m.add_connection(CK.CONTROL, proc.id, insp.id)
    m.add_connection(CK.NOTE, nota.id, kit.id).head_end = True   # ponta escolhida na seta
    return m


def examples_dir() -> Path:
    """Pasta 'examples' (no código-fonte ou dentro do executável)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "examples"


def manual_path() -> Path | None:
    """Manual de uso (HTML) no código-fonte ou dentro do executável."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    p = base / "docs" / "manual" / "manual.html"
    return p if p.exists() else None


def jaamsim_examples() -> dict[str, list[Path]]:
    """Exemplos oficiais do JaamSim convertidos, por categoria."""
    root = examples_dir() / "jaamsim_oficiais"
    if not root.is_dir():
        return {}
    return {d.name: sorted(d.glob("*.idefsim")) for d in sorted(root.iterdir()) if d.is_dir()}


ALL = {"Célula de usinagem com inspeção": usinagem_inspecao,
       "Montagem com junção E": montagem,
       "Triagem de pedidos por atributos": triagem_atributos,
       "Oficina de manutenção de bombas (manual)": oficina_bombas}
