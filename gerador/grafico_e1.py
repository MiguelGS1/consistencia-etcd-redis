"""
E1: curva latência p99 × vazão efetiva, com os dois sistemas no mesmo gráfico (eixos em log;
no x porque a vazão do Redis é ~20× a do etcd e a curva do etcd ficaria espremida).

Uso: python grafico_e1.py
Lê resultados/e1/<sistema>/N<n>/<execução>/. Para cada N usa a mediana das execuções;
as barras vão do mínimo ao máximo. Marca o N ótimo (maior razão vazão / p99) e o ponto
de vazão máxima (platô). Gera resultados/e1.png e resultados/e1.txt.
"""
import glob
import statistics

import matplotlib
matplotlib.use("Agg")  # gera o PNG sem abrir janela
import matplotlib.pyplot as plt

from metricas import cpu_gerador, resumo

CORES = {"etcd": "#2a78d6", "redis": "#eb6834"}  # azul e laranja da paleta categórica
MARCADORES = {"etcd": "o", "redis": "s"}
TEXTO = "#52514e"


def pontos(sistema):
    """Um ponto por N: mediana, mínimo e máximo da vazão e do p99 nas execuções."""
    lista = []
    for pasta_n in glob.glob(f"resultados/e1/{sistema}/N*"):
        execucoes = sorted(glob.glob(pasta_n + "/*/"))
        if not execucoes:
            continue
        resumos = [resumo(e) for e in execucoes]
        vazoes = [r["vazao"] for r in resumos]
        p99s = [r["p99"] for r in resumos]
        cpus = [c for c in (cpu_gerador(e)[1] for e in execucoes) if c is not None]
        lista.append({"n": int(pasta_n.rsplit("N", 1)[1]), "execucoes": len(execucoes),
                      "vazao": statistics.median(vazoes), "vazao_min": min(vazoes), "vazao_max": max(vazoes),
                      "p99": statistics.median(p99s), "p99_min": min(p99s), "p99_max": max(p99s),
                      "cpu_max": max(cpus) if cpus else None})
    lista.sort(key=lambda p: p["n"])
    for p in lista:
        p["razao"] = p["vazao"] / p["p99"]  # req/s por ms: critério do ponto ótimo
    return lista


def tabela(sistema, lista):
    """Texto com a tabela do E1, o N ótimo e a vazão máxima sustentada."""
    linhas = [f"{sistema}",
              f"  {'N':>4} {'exec':>4} {'vazão req/s (mín–máx)':>26} {'p99 ms (mín–máx)':>24} "
              f"{'vazão/p99':>10} {'CPU ger. máx':>12}"]
    for p in lista:
        vazao = f"{p['vazao']:.0f} ({p['vazao_min']:.0f}–{p['vazao_max']:.0f})"
        p99 = f"{p['p99']:.2f} ({p['p99_min']:.2f}–{p['p99_max']:.2f})"
        cpu = f"{p['cpu_max']:.0f}%" if p["cpu_max"] is not None else "-"
        linhas.append(f"  {p['n']:>4} {p['execucoes']:>4} {vazao:>26} {p99:>24} {p['razao']:>10.1f} {cpu:>12}")
    otimo = max(lista, key=lambda p: p["razao"])
    maximo = max(lista, key=lambda p: p["vazao"])
    linhas.append(f"  N ótimo = {otimo['n']} (vazão/p99 = {otimo['razao']:.1f} req/s por ms)")
    linhas.append(f"  vazão máxima sustentada = {maximo['vazao']:.0f} req/s (N = {maximo['n']})")
    return linhas


def main():
    fig, ax = plt.subplots(figsize=(9, 5.5))
    texto = []
    for sistema in ["etcd", "redis"]:
        lista = pontos(sistema)
        if not lista:
            continue
        texto += tabela(sistema, lista) + [""]
        cor = CORES[sistema]
        x = [p["vazao"] for p in lista]
        y = [p["p99"] for p in lista]
        erro_x = [[p["vazao"] - p["vazao_min"] for p in lista], [p["vazao_max"] - p["vazao"] for p in lista]]
        erro_y = [[p["p99"] - p["p99_min"] for p in lista], [p["p99_max"] - p["p99"] for p in lista]]
        ax.errorbar(x, y, xerr=erro_x, yerr=erro_y, color=cor, marker=MARCADORES[sistema],
                    markersize=6, linewidth=2, elinewidth=1, capsize=0, label=sistema)

        # rótulos só nos pontos que interessam: N=1, ótimo, vazão máxima e o último N
        otimo = max(lista, key=lambda p: p["razao"])
        maximo = max(lista, key=lambda p: p["vazao"])
        ax.plot(otimo["vazao"], otimo["p99"], marker="*", markersize=16, color=cor,
                markeredgecolor="white", linestyle="none")
        for p in lista:
            if p is lista[0] or p is otimo or p is maximo or p is lista[-1]:
                rotulo = f"N={p['n']}" + (" (ótimo)" if p is otimo else "") + (" (vazão máx.)" if p is maximo else "")
                # o último N fica à esquerda do ponto, para não cobrir o rótulo da vazão máxima
                deslocamento, alinhamento = ((-8, 4), "right") if p is lista[-1] else ((8, -12), "left")
                ax.annotate(rotulo, (p["vazao"], p["p99"]), textcoords="offset points",
                            xytext=deslocamento, ha=alinhamento, fontsize=8, color=TEXTO)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Vazão efetiva (req/s com sucesso, escala log)")
    ax.set_ylabel("Latência p99 (ms, escala log)")
    ax.set_title("E1: latência p99 × vazão (mediana das execuções; barras = mín–máx)", fontsize=11)
    ax.grid(True, which="both", color="#e5e4e0", linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.savefig("resultados/e1.png", dpi=150, bbox_inches="tight")

    print("\n".join(texto))
    with open("resultados/e1.txt", "w") as f:
        f.write("\n".join(texto) + "\n")
    print("gráfico: resultados/e1.png")


if __name__ == "__main__":
    main()
