"""
Verificação depois do E5 (partição curada) e do E6 (nó reiniciado).

Uso: python convergencia.py SISTEMA PASTA

1. Convergência: lê as 10.000 chaves no estado local de cada nó e conta em quantas
   chaves os três nós discordam.
2. Escritas confirmadas perdidas: para cada chave, pega nas amostras do gerador o
   último PUT com sucesso (maior instante de fim) e confere, em cada nó, se o valor
   final é o desse PUT ou o de um PUT que ainda não tinha terminado quando ele começou.
   Esses PUTs (concorrentes ou posteriores) podem ter sido aplicados depois dele,
   mesmo tendo dado erro ou timeout, então o valor deles também é aceito.
Grava o resultado em PASTA/convergencia.txt.

Isso só funciona porque cada PUT do gerador grava um valor único (ex.: t3-1520),
registrado na amostra: dá para saber exatamente qual escrita está em cada nó.
"""
import os
import sys

import adaptadores
from gerador import NOS, NUM_CHAVES, id_de
from metricas import ler_amostras


def ler_estado(sistema):
    """Valor (id) de cada chave em cada nó, lido do estado local do nó."""
    # get_local: no etcd é uma leitura serializable (sem passar pelo líder), para ver
    # o que cada nó realmente tem; no Redis já é a leitura normal do nó.
    # Resultado: estado["n2"]["k15"] = id do valor da chave k15 no n2.
    estado = {}
    for no in NOS:
        adaptador = adaptadores.criar(sistema, no)
        estado[no] = {f"k{i}": id_de(adaptador.get_local(f"k{i}")) for i in range(NUM_CHAVES)}
    return estado


def puts_por_chave(pasta):
    """Todos os PUTs das amostras (com sucesso ou não), agrupados por chave,
    como tuplas (inicio, fim, sucesso, valor) para ocupar pouca memória."""
    # Resultado: puts["k15"] = [(inicio, fim, sucesso, valor), ...] de todos os PUTs na k15
    puts = {}
    for a in ler_amostras(pasta):
        if a["operacao"] == "PUT":
            puts.setdefault(a["chave"], []).append((a["inicio"], a["fim"], a["sucesso"], a["valor"]))
    return puts


def main():
    sistema, pasta = sys.argv[1], sys.argv[2]
    estado = ler_estado(sistema)

    # 1. chaves em que os nós não têm o mesmo valor
    # (o conjunto dos 3 valores tem mais de 1 elemento quando algum nó discorda)
    divergentes = sum(1 for i in range(NUM_CHAVES)
                      if len({estado[no][f"k{i}"] for no in NOS}) > 1)

    # 2. escritas confirmadas perdidas, por nó
    confirmadas = 0
    perdidas = {no: 0 for no in NOS}
    for chave, lista in puts_por_chave(pasta).items():
        com_sucesso = [(fim, inicio) for inicio, fim, sucesso, valor in lista if sucesso]
        if not com_sucesso:
            continue   # nenhuma escrita confirmada nesta chave: não há o que perder
        confirmadas += 1
        fim_ultimo, inicio_ultimo = max(com_sucesso)  # o PUT confirmado de maior instante de fim
        # Valores aceitos no estado final: o do último PUT confirmado e os de todos os PUTs
        # que terminaram depois de ele começar (fim >= inicio_ultimo), porque esses podem ter
        # sido aplicados depois dele. Qualquer outro valor significa que a escrita se perdeu.
        aceitos = {valor for inicio, fim, sucesso, valor in lista if fim >= inicio_ultimo}
        for no in NOS:
            if estado[no][chave] not in aceitos:
                perdidas[no] += 1

    # Resumo impresso na tela e gravado na pasta da execução
    linhas = [f"convergência ({sistema}, {pasta})",
              f"  chaves em que os nós discordam: {divergentes} de {NUM_CHAVES}",
              f"  chaves vazias por nó: " + ", ".join(
                  f"{no}={sum(1 for v in estado[no].values() if v == '')}" for no in NOS),
              f"  chaves com escrita confirmada durante a execução: {confirmadas}",
              f"  última escrita confirmada perdida, por nó: " + ", ".join(
                  f"{no}={perdidas[no]}" for no in NOS)]
    print("\n".join(linhas))
    with open(os.path.join(pasta, "convergencia.txt"), "w") as f:
        f.write("\n".join(linhas) + "\n")


if __name__ == "__main__":
    main()
