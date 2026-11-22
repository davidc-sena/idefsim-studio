"""Modelos de exemplo."""
from __future__ import annotations

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


ALL = {"Célula de usinagem com inspeção": usinagem_inspecao,
       "Montagem com junção E": montagem,
       "Triagem de pedidos por atributos": triagem_atributos}
