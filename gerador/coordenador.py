"""
E3: stale reads.

Uso: python coordenador.py SISTEMA PARES ARQUIVO_CSV

Em loop: PUT(k, v) no n1, com v único e crescente. Assim que o PUT volta com
sucesso, faz GET(k) no n3 (no Redis, o n3 é uma réplica). O GET só começa
depois do retorno do PUT.
Stale read = valor lido menor que o último v cujo PUT voltou com sucesso.
Um PUT com erro ou timeout não conta como confirmado e não gera par.
"""
import csv
import sys
import time

import adaptadores


def main():
    sistema, pares, arquivo = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    chave = f"e3-{time.time()}"  # chave nova a cada execução: um valor antigo não mascara stale reads
    escrita = adaptadores.criar(sistema, "n1")
    leitura = adaptadores.criar(sistema, "n3")

    linhas = []
    v = 0
    while len(linhas) < pares:
        v += 1
        t0 = time.time()
        try:
            escrita.put(chave, str(v))
        except Exception:
            continue  # não confirmado: pode ou não ter sido aplicado
        confirmado = v  # último v cujo PUT voltou com sucesso
        t1 = time.time()
        try:
            lido = leitura.get(chave)
        except Exception as erro:
            linhas.append([t0, t1, time.time(), confirmado, "", "", type(erro).__name__])
            continue
        t2 = time.time()
        lido = int(lido) if lido else 0  # chave que ainda não chegou na réplica conta como 0
        stale = 1 if lido < confirmado else 0
        linhas.append([t0, t1, t2, confirmado, lido, stale, ""])

    with open(arquivo, "w", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["inicio_put", "fim_put", "fim_get", "v_confirmado", "v_lido", "stale", "erro"])
        escritor.writerows(linhas)

    lidos = [l for l in linhas if l[5] != ""]
    stales = sum(l[5] for l in lidos)
    print(f"{sistema}: {len(lidos)} pares, {stales} stale reads "
          f"({100 * stales / max(1, len(lidos)):.2f}%), {len(linhas) - len(lidos)} GETs com erro -> {arquivo}")


if __name__ == "__main__":
    main()
