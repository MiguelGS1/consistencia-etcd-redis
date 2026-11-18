"""
Funções comuns da análise: ler as amostras, descartar o aquecimento, percentis, vazão e CPU.

Uso direto (resumo de uma execução; é o que mostramos no E2 ao vivo):
  python metricas.py PASTA

As outras análises (grafico_e1.py, tabelas.py, convergencia.py, linha_tempo.py)
importam as funções daqui, para todas calcularem as métricas do mesmo jeito.
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
    # O arquivo tem uma linha só: "inicio,fim" (timestamps absolutos)
    with open(os.path.join(pasta, "execucao.txt")) as f:
        inicio, fim = f.read().split(",")
    return float(inicio), float(fim)


def ler_amostras(pasta):
    """Devolve as amostras uma por vez (yield), sem carregar tudo na memória:
    no Redis uma execução pode ter dezenas de milhões de amostras."""
    # Junta os arquivos de todos os processos do gerador (amostras_p0, amostras_p1, ...)
    for arquivo in sorted(glob.glob(os.path.join(pasta, "amostras_p*.csv.gz"))):
        with gzip.open(arquivo, "rt", newline="") as f:
            # DictReader devolve cada linha como dicionário {coluna: texto}.
            # Aqui convertemos os textos para os tipos certos (número, booleano).
            for a in csv.DictReader(f):
                a["inicio"] = float(a["inicio"])
                a["fim"] = float(a["fim"])
                a["sucesso"] = a["sucesso"] == "1"
                a["latencia_ms"] = float(a["latencia_ms"]) if a["latencia_ms"] else None
                yield a


def percentis(valores, lista_p):
    """Percentis pelo método do posto mais próximo. Ordena a lista no lugar (economiza memória)."""
    # Posto mais próximo: o percentil p é o valor na posição ceil(p/100 * n) da lista ordenada
    # (contando a partir de 1). Ex.: com 1.000 latências, o p99 é a 990ª menor.
    # É sempre uma latência que foi medida de verdade, sem interpolação.
    if not valores:
        return {p: None for p in lista_p}
    valores.sort()
    return {p: valores[max(0, math.ceil(p / 100 * len(valores)) - 1)] for p in lista_p}


def resumo(pasta):
    """Métricas de uma execução, só com as requisições iniciadas depois do aquecimento:
    vazão efetiva (req/s com sucesso) e p50/p95/p99 de GET e de PUT."""
    inicio, fim = ler_execucao(pasta)
    inicio_janela = inicio + DESCARTE   # a janela medida vai de início + 30 s até o fim
    sucessos = erros = 0
    latencias = {"GET": [], "PUT": [], "todas": []}
    for a in ler_amostras(pasta):
        if a["inicio"] < inicio_janela:
            continue   # requisição do aquecimento: ignorada
        if a["sucesso"]:
            sucessos += 1
            latencias[a["operacao"]].append(a["latencia_ms"])
            latencias["todas"].append(a["latencia_ms"])
        else:
            erros += 1  # erros e timeouts não entram nos percentis

    # Vazão efetiva (enunciado): só as requisições com sucesso, divididas pela duração da janela
    duracao = fim - inicio_janela
    r = {"amostras": sucessos + erros, "erros": erros, "duracao": duracao, "vazao": sucessos / duracao,
         "p99": percentis(latencias["todas"], [99])[99]}   # p99 geral: eixo y da curva do E1
    # Chaves como "GET_p50", "PUT_p99"... (usadas pelas tabelas do E2 e do E4)
    for op in ["GET", "PUT"]:
        for p, valor in percentis(latencias[op], [50, 95, 99]).items():
            r[f"{op}_p{p}"] = valor
    return r


def cpu_gerador(pasta):
    """CPU média e máxima do contêiner gerador, lida do cpu.csv (100% = 1 núcleo)."""
    # O cpu.csv é gravado pelo scripts/carga.sh com o docker stats. Serve para provar
    # que o gerador não saturou (o enunciado exige monitorar a CPU do gerador).
    valores = []
    arquivo = os.path.join(pasta, "cpu.csv")
    if os.path.exists(arquivo):
        with open(arquivo, newline="") as f:
            for linha in csv.DictReader(f):
                if linha["conteiner"] == "gerador" and linha["cpu"].endswith("%"):
                    valores.append(float(linha["cpu"].rstrip("%")))   # "139.52%" -> 139.52
    if not valores:
        return None, None
    return sum(valores) / len(valores), max(valores)


def main():
    # Imprime o resumo de uma execução no formato mostrado no E2 ao vivo
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
