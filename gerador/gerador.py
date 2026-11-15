"""
Gerador de carga em loop fechado (seção 3 do enunciado).

Uso (dentro do contêiner gerador):
  python gerador.py SISTEMA N DURACAO PASTA [--processos P] [--troca-no]

  SISTEMA        etcd ou redis
  N              número total de threads cliente (regula a intensidade da carga)
  DURACAO        segundos de execução
  PASTA          onde gravar as amostras (um CSV compactado por processo)
  --processos P  divide as N threads em P processos: por causa do GIL,
                 um processo Python usa no máximo ~1 núcleo
  --troca-no     quando uma requisição falha, a thread passa para o próximo nó
                 (usado só no E6, para o cliente sair do nó morto)

Cada thread repete: sorteia operação e chave, mede o tempo da requisição e
registra uma amostra. Não há espera entre uma requisição e a próxima.
"""
import argparse
import csv
import gzip
import multiprocessing
import os
import random
import threading
import time

import adaptadores

NUM_CHAVES = 10_000
TAM_VALOR = 256   # bytes
PROB_GET = 0.8    # 80% GET, 20% PUT
SEMENTE = 42      # semente fixa: o mesmo N gera a mesma sequência de operações
NOS = ["n1", "n2", "n3"]
COLUNAS = ["inicio", "fim", "latencia_ms", "operacao", "sucesso", "no", "chave", "valor", "erro"]


def valor_de(id_valor):
    """Valor de 256 B: o id único seguido de '.' até completar o tamanho."""
    return id_valor.ljust(TAM_VALOR, ".")


def id_de(valor):
    """Recupera o id a partir de um valor lido (tira o preenchimento)."""
    return "" if valor is None else valor.rstrip(".")


def cliente(id_thread, sistema, fim_execucao, troca_no, registrar):
    """Uma thread cliente em loop fechado: a próxima requisição só sai quando a anterior termina."""
    rng = random.Random(f"{SEMENTE}-{id_thread}")  # sorteio reprodutível e diferente por thread
    indice_no = id_thread % len(NOS)               # espalha as threads entre n1, n2 e n3
    adaptador = adaptadores.criar(sistema, NOS[indice_no])
    contador = 0

    while time.time() < fim_execucao:
        # 1. sorteia a operação e a chave
        operacao = "GET" if rng.random() < PROB_GET else "PUT"
        chave = f"k{rng.randrange(NUM_CHAVES)}"
        if operacao == "PUT":
            contador += 1
            id_valor = f"t{id_thread}-{contador}"  # único: thread + contador
            no = adaptador.no_put
        else:
            id_valor = ""
            no = adaptador.no_get

        # 2. t0, envia e espera a resposta ou o timeout
        t0 = time.time()
        try:
            if operacao == "PUT":
                adaptador.put(chave, valor_de(id_valor))
            else:
                id_valor = id_de(adaptador.get(chave))
            # 3. t1 e amostra com sucesso
            t1 = time.time()
            registrar([t0, t1, round((t1 - t0) * 1000, 3), operacao, 1, no, chave, id_valor, ""])
        except Exception as erro:
            # erro ou timeout: não registra latência, só o tipo do erro
            t1 = time.time()
            registrar([t0, t1, "", operacao, 0, no, chave, id_valor, type(erro).__name__])
            if troca_no:
                indice_no = (indice_no + 1) % len(NOS)
                adaptador = adaptadores.criar(sistema, NOS[indice_no])
        # 4. recomeça imediatamente


def processo(p, args, fim_execucao):
    """O processo p roda as threads p, p+P, p+2P, ...
    Os ids são globais, então a semente e o nó de cada thread não dependem de P."""
    ids = range(p, args.n, args.processos)
    # Cada amostra vai direto para o arquivo, para a memória não crescer: no Redis são
    # milhões de amostras por execução. gzip nível 1 compacta rápido e gasta pouca CPU.
    arquivo = os.path.join(args.pasta, f"amostras_p{p}.csv.gz")
    with gzip.open(arquivo, "wt", compresslevel=1, newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(COLUNAS)
        trava = threading.Lock()  # as threads do processo escrevem no mesmo arquivo

        def registrar(amostra):
            with trava:
                escritor.writerow(amostra)

        threads = [threading.Thread(target=cliente,
                                    args=(i, args.sistema, fim_execucao, args.troca_no, registrar))
                   for i in ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()


def main():
    parser = argparse.ArgumentParser(description="Gerador de carga em loop fechado")
    parser.add_argument("sistema", choices=["etcd", "redis"])
    parser.add_argument("n", type=int)
    parser.add_argument("duracao", type=float)
    parser.add_argument("pasta")
    parser.add_argument("--processos", type=int, default=1)
    parser.add_argument("--troca-no", action="store_true")
    args = parser.parse_args()
    args.processos = min(args.processos, args.n)  # nunca mais processos que threads
    os.makedirs(args.pasta, exist_ok=True)

    inicio = time.time()
    fim_execucao = inicio + args.duracao  # todos os processos param no mesmo instante
    with open(os.path.join(args.pasta, "execucao.txt"), "w") as f:
        f.write(f"{inicio},{fim_execucao}\n")  # a análise usa para a janela e a linha do tempo
    processos = [multiprocessing.Process(target=processo, args=(p, args, fim_execucao))
                 for p in range(args.processos)]
    for pr in processos:
        pr.start()
    for pr in processos:
        pr.join()
    print(f"{args.sistema}: N={args.n} em {args.processos} processo(s), {args.duracao:.0f} s -> {args.pasta}")


if __name__ == "__main__":
    main()
