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

Loop fechado: cada thread tem no máximo UMA requisição em andamento. Então N define
quantas requisições estão no sistema ao mesmo tempo, e a vazão resultante é
aproximadamente N / latência média (lei de Little). Aumentar N aumenta a carga.
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

# Parâmetros fixos da carga, todos definidos pelo enunciado
NUM_CHAVES = 10_000
TAM_VALOR = 256   # bytes
PROB_GET = 0.8    # 80% GET, 20% PUT
SEMENTE = 42      # semente fixa: o mesmo N gera a mesma sequência de operações
NOS = ["n1", "n2", "n3"]
# Uma linha do CSV por requisição (a "amostra"):
#   inicio, fim   timestamps absolutos (time.time(), segundos desde 1970) de t0 e t1
#   latencia_ms   t1 - t0 em ms; vazia em erro ou timeout
#   operacao      GET ou PUT;  sucesso: 1 ou 0;  no: nó que atendeu (n1, n2 ou n3)
#   chave, valor  a chave e o id do valor escrito (PUT) ou lido (GET), para o E5/E6
#   erro          nome da exceção em caso de erro (ex.: ReadTimeout, ConnectionError)
COLUNAS = ["inicio", "fim", "latencia_ms", "operacao", "sucesso", "no", "chave", "valor", "erro"]


def valor_de(id_valor):
    """Valor de 256 B: o id único seguido de '.' até completar o tamanho."""
    # ex.: "t3-1520" -> "t3-1520......" (256 caracteres = 256 bytes, por serem ASCII)
    return id_valor.ljust(TAM_VALOR, ".")


def id_de(valor):
    """Recupera o id a partir de um valor lido (tira o preenchimento)."""
    # Chave inexistente (None) vira "", que a análise conta como "GET sem valor".
    return "" if valor is None else valor.rstrip(".")


def cliente(id_thread, sistema, fim_execucao, troca_no, registrar):
    """Uma thread cliente em loop fechado: a próxima requisição só sai quando a anterior termina."""
    rng = random.Random(f"{SEMENTE}-{id_thread}")  # sorteio reprodutível e diferente por thread
    indice_no = id_thread % len(NOS)               # espalha as threads entre n1, n2 e n3
    # Cada thread tem o próprio adaptador (a própria conexão) e fica presa ao seu nó.
    # Sem --troca-no ela nunca muda de nó, o que deixa visível o lado isolado no E5.
    adaptador = adaptadores.criar(sistema, NOS[indice_no])
    contador = 0  # número de PUTs desta thread, para gerar valores únicos

    # Todas as threads param no mesmo instante absoluto (fim_execucao), em todos os processos
    while time.time() < fim_execucao:
        # 1. sorteia a operação e a chave
        operacao = "GET" if rng.random() < PROB_GET else "PUT"
        chave = f"k{rng.randrange(NUM_CHAVES)}"   # uniforme entre k0 e k9999
        if operacao == "PUT":
            contador += 1
            id_valor = f"t{id_thread}-{contador}"  # único: thread + contador
            no = adaptador.no_put                  # no Redis é sempre o n1 (primário)
        else:
            id_valor = ""                          # o GET preenche com o id que ler
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
            # (o enunciado manda contar o timeout como erro, sem latência)
            t1 = time.time()
            registrar([t0, t1, "", operacao, 0, no, chave, id_valor, type(erro).__name__])
            if troca_no:
                # Reconfiguração do cliente (E6): passa para o próximo nó da lista
                # e cria um adaptador novo, ligado a ele.
                indice_no = (indice_no + 1) % len(NOS)
                adaptador = adaptadores.criar(sistema, NOS[indice_no])
        # 4. recomeça imediatamente


def processo(p, args, fim_execucao):
    """O processo p roda as threads p, p+P, p+2P, ...
    Os ids são globais, então a semente e o nó de cada thread não dependem de P."""
    # ex.: N = 8 e P = 4 -> o processo 0 roda as threads 0 e 4; o processo 1, as threads 1 e 5...
    ids = range(p, args.n, args.processos)
    # Cada amostra vai direto para o arquivo, para a memória não crescer: no Redis são
    # milhões de amostras por execução. gzip nível 1 compacta rápido e gasta pouca CPU.
    arquivo = os.path.join(args.pasta, f"amostras_p{p}.csv.gz")
    with gzip.open(arquivo, "wt", compresslevel=1, newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(COLUNAS)
        trava = threading.Lock()  # as threads do processo escrevem no mesmo arquivo

        def registrar(amostra):
            # A trava garante que duas threads não misturem as linhas no arquivo
            with trava:
                escritor.writerow(amostra)

        # Cria todas as threads do processo, inicia todas e espera todas terminarem
        threads = [threading.Thread(target=cliente,
                                    args=(i, args.sistema, fim_execucao, args.troca_no, registrar))
                   for i in ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    # Ao sair do "with", o arquivo .csv.gz é fechado e fica completo


def main():
    # Lê os argumentos da linha de comando (ver o uso no topo do arquivo)
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
    # Um processo do sistema operacional por grupo de threads: cada um tem o próprio GIL,
    # então juntos usam vários núcleos e o gerador não vira o gargalo da medição.
    processos = [multiprocessing.Process(target=processo, args=(p, args, fim_execucao))
                 for p in range(args.processos)]
    for pr in processos:
        pr.start()
    for pr in processos:
        pr.join()
    print(f"{args.sistema}: N={args.n} em {args.processos} processo(s), {args.duracao:.0f} s -> {args.pasta}")


if __name__ == "__main__":
    main()
