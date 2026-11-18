"""
Carga inicial: grava as 10.000 chaves antes de medir, para os GETs encontrarem valor.

Uso: python carga_inicial.py SISTEMA

É sequencial de propósito: se alguma escrita falhar, o script para com erro
e o experimento não começa com dados faltando.

Sem esta carga, no começo da medição quase todo GET buscaria uma chave que ainda não
existe. Também é por causa dela que um "GET sem valor" durante o E6 indica dado perdido.
"""
import sys

import adaptadores
from gerador import NUM_CHAVES, valor_de   # mesmas chaves e mesmo tamanho de valor da carga


def main():
    sistema = sys.argv[1]
    adaptador = adaptadores.criar(sistema, "n1")  # no Redis, n1 é o primário
    # Grava k0 ... k9999, todas com o valor "inicial" preenchido até 256 B.
    # Sem try/except: qualquer erro interrompe o script, e o ambiente.sh também para (set -e).
    for i in range(NUM_CHAVES):
        adaptador.put(f"k{i}", valor_de("inicial"))
    print(f"carga inicial: {NUM_CHAVES} chaves gravadas no {sistema}")


if __name__ == "__main__":
    main()
