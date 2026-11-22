"""Converte os exemplos oficiais do JaamSim em exemplos IDEF-SIM (examples/jaamsim_oficiais/).

Uso:  python packaging/convert_jaamsim_examples.py <pasta examples do código-fonte do JaamSim>
      (ex.: jaamsim/src/main/resources/resources/examples)
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from idefsim.jaamsim_import import JaamSimImportError, import_jaamsim  # noqa: E402
from idefsim.storage import save_model  # noqa: E402
from idefsim.validation import has_errors, validate  # noqa: E402

CATEGORIES = {".": "Modelos completos", "Process_Flow": "Fluxo de processo",
              "Resource_Objects": "Recursos", "Basic_Objects": "Objetos básicos",
              "Probability_Distributions": "Distribuições", "SubModel_Objects": "Submodelos",
              "Big_Lean_Simulation_Library": "Biblioteca Big Lean",
              "Graphics_Objects": "Gráficos", "Calculation_Objects": "Cálculo",
              "Fluid_Objects": "Fluidos"}


def main(src: Path) -> None:
    out = ROOT / "examples" / "jaamsim_oficiais"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    done, skipped = [], []
    for f in sorted(src.glob("**/*.cfg")):
        rel = f.relative_to(src)
        cat = CATEGORIES.get(str(rel.parent), str(rel.parent))
        try:
            res = import_jaamsim(f)
        except JaamSimImportError as ex:
            skipped.append((rel, str(ex)))
            continue
        if has_errors(validate(res.model)):
            skipped.append((rel, "erros de validação"))
            continue
        res.model.name = f.stem
        dest = out / cat / f"{f.stem}.idefsim"
        dest.parent.mkdir(parents=True, exist_ok=True)
        save_model(res.model, dest)
        done.append((cat, f.stem, len(res.notes)))
    lic = next((d / "LICENSE" for d in src.parents if (d / "LICENSE").exists()), None)
    if lic is None:
        raise SystemExit("LICENSE do JaamSim não encontrada: é obrigatória para redistribuir.")
    shutil.copy(lic, out / "LICENSE-JaamSim.txt")
    lines = ["# Exemplos do JaamSim convertidos para IDEF-SIM", "",
             "Modelos convertidos automaticamente dos exemplos oficiais do JaamSim "
             "(<https://github.com/jaamsim/jaamsim>, Apache License 2.0, "
             "© JaamSim Software Inc. e Ausenco Engineering Canada Inc.), com o importador do "
             "IDEF-SIM Studio. São modelos conceituais: o que não tem equivalente em IDEF-SIM está "
             "anotado na descrição de cada modelo. A licença original está em "
             "`LICENSE-JaamSim.txt`.", "",
             f"Convertidos: {len(done)} · Não convertidos: {len(skipped)}", "",
             "| Categoria | Exemplo | Observações |", "|---|---|---|"]
    lines += [f"| {c} | {n} | {k} |" for c, n, k in done]
    lines += ["", "## Não convertidos (sem fluxo de entidades)", ""]
    lines += [f"- `{r}` — {why}" for r, why in skipped]
    (out / "LEIA-ME.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(done)} convertidos, {len(skipped)} não convertidos → {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
