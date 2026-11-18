#!/usr/bin/env bash
# Uso: ./scripts/carga.sh SISTEMA N DURACAO PASTA [opcoes extras do gerador.py]
# Roda o gerador de carga e, ao mesmo tempo, registra a CPU de todos os conteineres
# (docker stats), para conferir que o gerador nao saturou.
# PASTA e relativa a gerador/ (ex.: resultados/e2/etcd/20261115-101500).
# PROCESSOS (variavel de ambiente, padrao 8): processos geradores em paralelo. Com 4, o gerador
# saturou (~4 nucleos em uso); com 8, cada processo fica abaixo de 100% de CPU.
set -euo pipefail
# Os 4 primeiros argumentos tem nome; "shift 4" os remove, e o que sobrar em "$@"
# (ex.: --troca-no no E6) e repassado ao gerador.py
SISTEMA="$1"; N="$2"; DURACAO="$3"; PASTA="$4"; shift 4
PROCESSOS="${PROCESSOS:-8}"
cd "$(dirname "$0")/.."
# A pasta fica dentro de gerador/, que e montada em /app no conteiner: o gerador
# (dentro do conteiner) e este script (no Mac) enxergam os mesmos arquivos
mkdir -p "gerador/$PASTA"

# Comando exato, para a reprodutibilidade
echo "python gerador.py $SISTEMA $N $DURACAO $PASTA --processos $PROCESSOS $*" > "gerador/$PASTA/comando.txt"

# CPU em segundo plano: cada docker stats --no-stream leva ~2 s
# Cada linha do cpu.csv: instante, nome do conteiner, % de CPU (100% = 1 nucleo) e memoria.
# O "&" no fim roda o bloco em segundo plano, enquanto a carga roda abaixo.
( echo "instante,conteiner,cpu,memoria"
  while true; do
    docker stats --no-stream --format "$(date +%s),{{.Name}},{{.CPUPerc}},{{.MemUsage}}"
  done ) > "gerador/$PASTA/cpu.csv" &
CPU=$!   # PID do bloco em segundo plano
# trap ... EXIT: quando este script terminar (bem ou com erro), para a coleta de CPU
trap 'kill $CPU 2>/dev/null' EXIT

# A carga em si: roda o gerador.py dentro do conteiner gerador, que esta na rede dos clientes
docker exec gerador python gerador.py "$SISTEMA" "$N" "$DURACAO" "$PASTA" --processos "$PROCESSOS" "$@"
