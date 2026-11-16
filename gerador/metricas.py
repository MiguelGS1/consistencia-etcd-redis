"""
Funções comuns da análise: ler as amostras, descartar o aquecimento, percentis, vazão e CPU.

Uso direto (resumo de uma execução; é o que mostramos no E2 ao vivo):
  python metricas.py PASTA
"""
import csv
import glob
import gzip
import math
import os
import sys

DESCARTE = 30  # segundos iniciais descartados (aquecimento)


def ler_execucao(pasta):
    """Instantes de início e fim da carga, gravados pelo gerador em execucao.txt."""
    with open(os.path.join(pasta, "execucao.txt")) as f:
        inicio, fim = f.read().split(",")
    return float(inicio), float(fim)


def ler_amostras(pasta):
    """Devolve as amostras uma por vez (yield), sem carregar tudo na memória:
    no Redis uma execução pode ter dezenas de milhões de amostras."""
    for arquivo in sorted(glob.glob(os.path.join(pasta, "amostras_p*.csv.gz"))):
        with gzip.open(arquivo, "rt", newline="") as f:
            for a in csv.DictReader(f):
                a["inicio"] = float(a["inicio"])
                a["fim"] = float(a["fim"])
                a["sucesso"] = a["sucesso"] == "1"
                a["latencia_ms"] = float(a["latencia_ms"]) if a["latencia_ms"] else None
                yield a


def percentis(valores, lista_p):
    """Percentis pelo método do posto mais próximo. Ordena a lista no lugar (economiza memória)."""
    if not valores:
        return {p: None for p in lista_p}
    valores.sort()
    return {p: valores[max(0, math.ceil(p / 100 * len(valores)) - 1)] for p in lista_p}


def resumo(pasta):
    """Métricas de uma execução, só com as requisições iniciadas depois do aquecimento:
    vazão efetiva (req/s com sucesso) e p50/p95/p99 de GET e de PUT."""
    inicio, fim = ler_execucao(pasta)
    inicio_janela = inicio + DESCARTE
    sucessos = erros = 0
    latencias = {"GET": [], "PUT": [], "todas": []}
    for a in ler_amostras(pasta):
        if a["inicio"] < inicio_janela:
            continue
        if a["sucesso"]:
            sucessos += 1
            latencias[a["operacao"]].append(a["latencia_ms"])
            latencias["todas"].append(a["latencia_ms"])
        else:
            erros += 1  # erros e timeouts não entram nos percentis

    duracao = fim - inicio_janela
    r = {"amostras": sucessos + erros, "erros": erros, "duracao": duracao, "vazao": sucessos / duracao,
         "p99": percentis(latencias["todas"], [99])[99]}
    for op in ["GET", "PUT"]:
        for p, valor in percentis(latencias[op], [50, 95, 99]).items():
            r[f"{op}_p{p}"] = valor
    return r


def cpu_gerador(pasta):
    """CPU média e máxima do contêiner gerador, lida do cpu.csv (100% = 1 núcleo)."""
    valores = []
    arquivo = os.path.join(pasta, "cpu.csv")
    if os.path.exists(arquivo):
        with open(arquivo, newline="") as f:
            for linha in csv.DictReader(f):
                if linha["conteiner"] == "gerador" and linha["cpu"].endswith("%"):
                    valores.append(float(linha["cpu"].rstrip("%")))
    if not valores:
        return None, None
    return sum(valores) / len(valores), max(valores)


def main():
    pasta = sys.argv[1]
    r = resumo(pasta)
    print(pasta)
    print(f"  amostras na janela: {r['amostras']} (erros: {r['erros']}), janela de {r['duracao']:.0f} s")
    print(f"  vazão efetiva: {r['vazao']:.0f} req/s")
    print(f"  {'':4} {'p50':>9} {'p95':>9} {'p99':>9}   (ms)")
    for op in ["GET", "PUT"]:
        print(f"  {op:4} " + " ".join(f"{r[f'{op}_p{p}']:9.2f}" for p in [50, 95, 99]))
    media, maximo = cpu_gerador(pasta)
    if media is not None:
        print(f"  CPU do gerador: média {media:.0f}%, máximo {maximo:.0f}% (100% = 1 núcleo)")


if __name__ == "__main__":
    main()
