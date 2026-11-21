"""Distribuições estatísticas (as mesmas do JaamSim), em notação semelhante à do Arena.

Exemplos aceitos::

    5             CONST(5)          EXPO(10)          NORM(5; 0,5)
    TRIA(2, 4, 7) UNIF(1, 3)        LOGN(5, 1)        ERLA(6, 3)
    WEIB(5, 2)    GAMM(6, 2)        BETA(2, 5, 1, 9)  LOGL(4, 3)
    DISC(1, 0.3, 2, 0.7)            (valor, probabilidade, valor, probabilidade, ...)
    CONT(2, 0, 4, 0.6, 9, 1)        (valor, prob. acumulada, ...; empírica contínua)

Só para contagens (atributos), como no JaamSim, onde não aceitam unidade de tempo::

    POIS(3)  BINO(10, 0.2)  GEOM(0.3)  NBIN(2, 0.4)  DUNI(1, 6)

Os argumentos podem ser separados por vírgula (decimal com ponto) ou por
ponto-e-vírgula (permitindo vírgula decimal, ex.: ``NORM(5,5; 0,8)``).
Em tempos, amostras negativas são truncadas em zero.
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass


class DistributionError(ValueError):
    pass


@dataclass(frozen=True)
class DistSpec:
    code: str
    label: str            # nome exibido na interface
    params: tuple[str, ...]  # rótulos dos parâmetros (DISC: variável)
    jaamsim: str          # classe correspondente no JaamSim
    count: bool = False   # só contagens (adimensional no JaamSim): não serve para tempos


CATALOG: list[DistSpec] = [
    DistSpec("CONST", "Constante", ("Valor médio",), "—"),
    DistSpec("EXPO", "Exponencial", ("Média",), "ExponentialDistribution"),
    DistSpec("NORM", "Normal", ("Média", "Desvio padrão"), "NormalDistribution"),
    DistSpec("TRIA", "Triangular", ("Mínimo", "Moda", "Máximo"), "TriangularDistribution"),
    DistSpec("UNIF", "Uniforme", ("Mínimo", "Máximo"), "UniformDistribution"),
    DistSpec("LOGN", "Log-normal", ("Média", "Desvio padrão"), "LogNormalDistribution"),
    DistSpec("ERLA", "Erlang", ("Média", "k (forma, inteiro)"), "ErlangDistribution"),
    DistSpec("GAMM", "Gama", ("Média", "Forma"), "GammaDistribution"),
    DistSpec("WEIB", "Weibull", ("Escala", "Forma"), "WeibullDistribution"),
    DistSpec("LOGL", "Log-logística", ("Escala", "Forma"), "LogLogisticDistribution"),
    DistSpec("BETA", "Beta", ("Alfa", "Beta", "Mínimo", "Máximo"), "BetaDistribution"),
    DistSpec("DISC", "Discreta", ("Valores", "Probabilidades"), "DiscreteDistribution"),
    DistSpec("CONT", "Contínua empírica", ("Valores", "Probabilidades acumuladas"),
             "ContinuousDistribution"),
    DistSpec("POIS", "Poisson", ("Média",), "PoissonDistribution", True),
    DistSpec("BINO", "Binomial", ("Nº de tentativas", "Probabilidade"), "BinomialDistribution", True),
    DistSpec("GEOM", "Geométrica", ("Probabilidade",), "GeometricDistribution", True),
    DistSpec("NBIN", "Binomial negativa", ("Nº de sucessos", "Probabilidade"),
             "NegativeBinomialDistribution", True),
    DistSpec("DUNI", "Uniforme discreta", ("Mínimo", "Máximo"), "DiscreteUniformDistribution", True),
]
PAIRED = {"DISC", "CONT"}  # parâmetros em pares (valor, probabilidade)
TIME_CATALOG = [s for s in CATALOG if not s.count]
SPECS = {s.code: s for s in CATALOG}
SUPPORTED = ["CONST(valor)", "EXPO(média)", "NORM(média, desvio)", "TRIA(mín, moda, máx)",
             "UNIF(mín, máx)", "LOGN(média, desvio)", "ERLA(média, k)", "GAMM(média, forma)",
             "WEIB(escala, forma)", "LOGL(escala, forma)", "BETA(alfa, beta, mín, máx)",
             "DISC(valor1, prob1, valor2, prob2, ...)", "CONT(valor1, acum1, ...)",
             "POIS(média)", "BINO(n, p)", "GEOM(p)", "NBIN(k, p)", "DUNI(mín, máx)"]

_RE = re.compile(r"^\s*([A-Za-z]+)\s*\((.*)\)\s*$")


@dataclass(frozen=True)
class Distribution:
    name: str
    args: tuple[float, ...]

    @property
    def disc_values(self) -> tuple[float, ...]:
        return self.args[0::2]

    @property
    def disc_probs(self) -> tuple[float, ...]:
        return self.args[1::2]

    def sample(self, rng: random.Random, clip: bool = True) -> float:
        """Amostra; ``clip`` trunca em zero (tempos). Atributos usam clip=False."""
        a, n = self.args, self.name
        if n == "CONST":
            v = a[0]
        elif n == "EXPO":
            v = rng.expovariate(1.0 / a[0])
        elif n == "NORM":
            v = rng.gauss(a[0], a[1])
        elif n == "TRIA":
            v = rng.triangular(a[0], a[2], a[1])
        elif n == "UNIF":
            v = rng.uniform(a[0], a[1])
        elif n == "LOGN":
            mean, sd = a
            s2 = math.log(1 + (sd * sd) / (mean * mean))
            v = rng.lognormvariate(math.log(mean) - s2 / 2, math.sqrt(s2))
        elif n == "ERLA":
            mean, k = a[0], int(a[1])
            v = sum(rng.expovariate(k / mean) for _ in range(k))
        elif n == "GAMM":
            mean, k = a
            v = rng.gammavariate(k, mean / k)
        elif n == "WEIB":
            v = rng.weibullvariate(a[0], a[1])
        elif n == "LOGL":
            u = rng.random()
            v = a[0] * (u / (1 - u)) ** (1 / a[1]) if 0 < u < 1 else 0.0
        elif n == "BETA":
            v = a[2] + (a[3] - a[2]) * rng.betavariate(a[0], a[1])
        elif n == "DISC":
            u, acc = rng.random(), 0.0
            v = self.disc_values[-1]
            for val, p in zip(self.disc_values, self.disc_probs):
                acc += p
                if u <= acc:
                    v = val
                    break
        elif n == "CONT":  # inversa da acumulada, interpolação linear
            u, vals, cps = rng.random(), self.disc_values, self.disc_probs
            v = vals[-1]
            for i in range(1, len(vals)):
                if u <= cps[i]:
                    span = cps[i] - cps[i - 1]
                    f = (u - cps[i - 1]) / span if span > 0 else 0.0
                    v = vals[i - 1] + f * (vals[i] - vals[i - 1])
                    break
        elif n == "POIS":  # Knuth (médias moderadas)
            lim, k, prod = math.exp(-a[0]), 0, rng.random()
            while prod > lim:
                k += 1
                prod *= rng.random()
            v = k
        elif n == "BINO":
            v = sum(1 for _ in range(int(a[0])) if rng.random() <= a[1])
        elif n == "GEOM":  # nº de falhas antes do 1º sucesso (como no JaamSim)
            v = 0 if a[0] >= 1 else int(math.log(1 - rng.random()) / math.log(1 - a[0]))
        elif n == "NBIN":
            v = sum(0 if a[1] >= 1 else int(math.log(1 - rng.random()) / math.log(1 - a[1]))
                    for _ in range(int(a[0])))
        elif n == "DUNI":
            v = rng.randint(int(a[0]), int(a[1]))
        else:  # pragma: no cover
            raise DistributionError(n)
        return max(0.0, v) if clip else v

    def mean(self) -> float:
        a, n = self.args, self.name
        if n in ("CONST", "EXPO", "NORM", "LOGN", "ERLA", "GAMM"):
            return a[0]
        if n == "TRIA":
            return sum(a) / 3
        if n == "UNIF":
            return (a[0] + a[1]) / 2
        if n == "WEIB":
            return a[0] * math.gamma(1 + 1 / a[1])
        if n == "LOGL":
            b = math.pi / a[1]
            return a[0] * b / math.sin(b) if a[1] > 1 else math.inf
        if n == "BETA":
            return a[2] + (a[3] - a[2]) * a[0] / (a[0] + a[1])
        if n == "DISC":
            return sum(v * p for v, p in zip(self.disc_values, self.disc_probs))
        if n == "CONT":
            vs, cs = self.disc_values, self.disc_probs
            return sum((cs[i] - cs[i - 1]) * (vs[i] + vs[i - 1]) / 2 for i in range(1, len(vs)))
        if n == "POIS":
            return a[0]
        if n == "BINO":
            return a[0] * a[1]
        if n == "GEOM":
            return (1 - a[0]) / a[0]
        if n == "NBIN":
            return a[0] * (1 - a[1]) / a[1]
        if n == "DUNI":
            return (a[0] + a[1]) / 2
        raise DistributionError(n)  # pragma: no cover

    def __str__(self) -> str:
        return f"{self.name}({', '.join(f'{x:g}' for x in self.args)})"


def _num(s: str) -> float:
    try:
        return float(s.strip())
    except ValueError:
        raise DistributionError(f"'{s.strip()}' não é um número válido.") from None


def fmt(name: str, args) -> str:
    """Monta o texto de uma distribuição (separador ';' e vírgula decimal, legível em pt-BR)."""
    nums = [f"{float(x):g}".replace(".", ",") for x in args]
    return f"{name}({'; '.join(nums)})"


def parse(text: str, allow_negative: bool = False, for_time: bool = False) -> Distribution:
    """Interpreta a expressão.

    ``allow_negative`` permite valores negativos (atributos); ``for_time`` recusa as
    distribuições só de contagem, que o JaamSim não aceita com unidade de tempo.
    """
    if text is None or not str(text).strip():
        raise DistributionError("Expressão vazia.")
    text = str(text).strip()
    m = _RE.match(text)
    if not m:
        name, args = "CONST", (_num(text.replace(",", ".")),)
    else:
        name, body = m.group(1).upper(), m.group(2)
        if name not in SPECS:
            raise DistributionError(f"Distribuição '{name}' desconhecida. Use: {', '.join(SUPPORTED)}")
        if ";" in body:
            parts = [p.replace(",", ".") for p in body.split(";")]
        elif len(SPECS[name].params) == 1 and name not in PAIRED:
            parts = [body.replace(",", ".")]   # um só parâmetro: vírgula é decimal (CONST(4,5))
        else:
            parts = body.split(",")
        args = tuple(_num(p) for p in parts)
    _check(name, args, allow_negative)
    if for_time and SPECS[name].count:
        raise DistributionError(f"{SPECS[name].label} é só para contagens (atributos); "
                                "não pode ser usada como tempo.")
    return Distribution(name, args)


def _check(name: str, a: tuple[float, ...], allow_negative: bool) -> None:
    spec = SPECS[name]
    if name == "CONT":
        if len(a) < 4 or len(a) % 2:
            raise DistributionError("Contínua empírica requer pares valor, probabilidade acumulada "
                                    "(pelo menos 2 pontos): CONT(2; 0; 9; 1)")
        vs, cs = a[0::2], a[1::2]
        if abs(cs[0]) > 1e-9 or abs(cs[-1] - 1) > 1e-9:
            raise DistributionError("Contínua empírica: a 1ª probabilidade acumulada deve ser 0 "
                                    "e a última 1.")
        if any(cs[i] < cs[i - 1] or vs[i] < vs[i - 1] for i in range(1, len(vs))):
            raise DistributionError("Contínua empírica: valores e probabilidades devem ser crescentes.")
        if not allow_negative and vs[0] < 0:
            raise DistributionError("Contínua empírica: tempos não podem ser negativos.")
        return
    if name == "DISC":
        if len(a) < 2 or len(a) % 2:
            raise DistributionError("DISC requer pares valor, probabilidade: DISC(1; 0,3; 2; 0,7)")
        probs = a[1::2]
        if any(p < 0 for p in probs):
            raise DistributionError("DISC: probabilidades não podem ser negativas.")
        if abs(sum(probs) - 1) > 1e-6:
            raise DistributionError(f"DISC: as probabilidades somam {sum(probs):g}; devem somar 1.")
        if not allow_negative and any(v < 0 for v in a[0::2]):
            raise DistributionError("DISC: valores de tempo não podem ser negativos.")
        return
    if len(a) != len(spec.params):
        raise DistributionError(f"{name} requer {len(spec.params)} parâmetro(s): "
                                + ", ".join(spec.params))
    def pos(i: int, what: str) -> None:
        if a[i] <= 0:
            raise DistributionError(f"{spec.label}: {what} deve ser positivo.")

    if name in ("EXPO", "LOGN", "ERLA", "GAMM"):
        pos(0, spec.params[0].lower())
    if name in ("NORM", "LOGN") and a[1] < 0:
        raise DistributionError(f"{spec.label}: o desvio padrão não pode ser negativo.")
    if name == "TRIA" and not (a[0] <= a[1] <= a[2]):
        raise DistributionError("Triangular: deve valer mínimo ≤ moda ≤ máximo.")
    if name == "UNIF" and a[0] > a[1]:
        raise DistributionError("Uniforme: o mínimo deve ser ≤ máximo.")
    if name == "ERLA" and (a[1] < 1 or a[1] != int(a[1])):
        raise DistributionError("Erlang: k deve ser inteiro ≥ 1.")
    if name in ("GAMM", "WEIB", "LOGL"):
        pos(1, "a forma")
    if name in ("WEIB", "LOGL"):
        pos(0, "a escala")
    if name in ("BINO", "NBIN") and (a[0] < 1 or a[0] != int(a[0])):
        raise DistributionError(f"{spec.label}: {spec.params[0].lower()} deve ser inteiro ≥ 1.")
    if name in ("BINO", "NBIN", "GEOM"):
        p_ = a[-1]
        if not (0 < p_ <= 1):
            raise DistributionError(f"{spec.label}: a probabilidade deve estar entre 0 e 1.")
    if name == "POIS":
        pos(0, "a média")
    if name == "DUNI" and (a[0] != int(a[0]) or a[1] != int(a[1]) or a[0] > a[1]):
        raise DistributionError("Uniforme discreta: mínimo e máximo inteiros, com mínimo ≤ máximo.")
    if name == "BETA":
        pos(0, "alfa")
        pos(1, "beta")
        if a[2] >= a[3]:
            raise DistributionError("Beta: o mínimo deve ser menor que o máximo.")
    if not allow_negative:
        if name == "CONST" and a[0] < 0:
            raise DistributionError("Constante: o valor não pode ser negativo.")
        if name in ("UNIF", "TRIA", "BETA") and min(a[-2:] if name == "BETA" else a) < 0:
            raise DistributionError(f"{spec.label}: tempos não podem ser negativos.")


def is_valid(text: str, allow_negative: bool = False, for_time: bool = False) -> bool:
    try:
        parse(text, allow_negative, for_time)
        return True
    except DistributionError:
        return False
