"""
Tabelas do relatório (mediana das execuções e, entre parênteses, mínimo–máximo):
  E2 × E4: p50/p95/p99 de GET e PUT e vazão efetiva, lado a lado
  E3: taxa de stale reads sem e com a latência do E4

Uso: python tabelas.py   (gera também resultados/tabelas.txt)
"""
import csv
import glob
import statistics

from metricas import resumo

METRICAS = [("GET_p50", "GET p50 (ms)"), ("GET_p95", "GET p95 (ms)"), ("GET_p99", "GET p99 (ms)"),
            ("PUT_p50", "PUT p50 (ms)"), ("PUT_p95", "PUT p95 (ms)"), ("PUT_p99", "PUT p99 (ms)"),
            ("vazao", "vazão (req/s)")]


def mediana_variacao(valores):
    if not valores:
        return "-"
    return f"{statistics.median(valores):.2f} ({min(valores):.2f}–{max(valores):.2f})"


def tabela_e2_e4(sistema):
    e2 = [resumo(p) for p in sorted(glob.glob(f"resultados/e2/{sistema}/*/"))]
    e4 = [resumo(p) for p in sorted(glob.glob(f"resultados/e4/{sistema}/*/"))]
    linhas = [f"{sistema}: E2 ({len(e2)} execuções) × E4 ({len(e4)} execuções)",
              f"  {'':14} {'E2 (sem atraso)':>28} {'E4 (RTT 100 ms)':>28}"]
    for chave, nome in METRICAS:
        linhas.append(f"  {nome:14} {mediana_variacao([r[chave] for r in e2]):>28} "
                      f"{mediana_variacao([r[chave] for r in e4]):>28}")
    return linhas


def taxa_stale(arquivo):
    """Porcentagem de stale reads de uma execução do coordenador (pares com GET bem-sucedido)."""
    with open(arquivo, newline="") as f:
        pares = [l for l in csv.DictReader(f) if l["stale"] != ""]
    return 100 * sum(int(l["stale"]) for l in pares) / len(pares), len(pares)


def tabela_e3(sistema):
    linhas = [f"{sistema}: E3, stale reads (% dos pares)"]
    for condicao in ["sem_latencia", "com_latencia"]:
        arquivos = sorted(glob.glob(f"resultados/e3/{sistema}/{condicao}/*/pares.csv"))
        taxas = [taxa_stale(a) for a in arquivos]
        linhas.append(f"  {condicao:14} {mediana_variacao([t for t, _ in taxas]):>28}"
                      f"   {len(arquivos)} execuções, {sum(n for _, n in taxas)} pares")
    return linhas


def main():
    linhas = []
    for sistema in ["etcd", "redis"]:
        linhas += tabela_e2_e4(sistema) + [""] + tabela_e3(sistema) + [""]
    print("\n".join(linhas))
    with open("resultados/tabelas.txt", "w") as f:
        f.write("\n".join(linhas) + "\n")


if __name__ == "__main__":
    main()
