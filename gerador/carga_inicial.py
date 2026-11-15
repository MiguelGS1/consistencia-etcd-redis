"""
Carga inicial: grava as 10.000 chaves antes de medir, para os GETs encontrarem valor.

Uso: python carga_inicial.py SISTEMA

É sequencial de propósito: se alguma escrita falhar, o script para com erro
e o experimento não começa com dados faltando.
"""
import sys

import adaptadores
from gerador import NUM_CHAVES, valor_de


def main():
    sistema = sys.argv[1]
    adaptador = adaptadores.criar(sistema, "n1")  # no Redis, n1 é o primário
    for i in range(NUM_CHAVES):
        adaptador.put(f"k{i}", valor_de("inicial"))
    print(f"carga inicial: {NUM_CHAVES} chaves gravadas no {sistema}")


if __name__ == "__main__":
    main()
