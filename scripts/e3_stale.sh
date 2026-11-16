#!/usr/bin/env bash
# Uso: ./scripts/e3_stale.sh etcd|redis [PARES] [REPETICOES]
# E3: coordenador faz PUT no n1 e, depois da confirmacao, GET no n3 (no Redis, uma replica).
# Duas condicoes: latencia original da rede e a latencia do E4 (50 ms por sentido, RTT 100 ms).
set -euo pipefail
SISTEMA="$1"; PARES="${2:-10000}"; REPETICOES="${3:-3}"
cd "$(dirname "$0")/.."

for R in $(seq 1 "$REPETICOES"); do
  for CONDICAO in sem_latencia com_latencia; do
    echo "=== E3 $SISTEMA $CONDICAO repeticao $R de $REPETICOES"
    PASTA="resultados/e3/$SISTEMA/$CONDICAO/$(date +%Y%m%d-%H%M%S)"
    ./scripts/ambiente.sh "$SISTEMA"
    mkdir -p "gerador/$PASTA"
    if [ "$CONDICAO" = "com_latencia" ]; then
      ./scripts/latencia_on.sh 50ms n1 n2 n3
      ./scripts/rtt.sh n1 172.20.0.12 > "gerador/$PASTA/rtt.txt"   # deve dar ~100 ms
    fi
    docker exec gerador python coordenador.py "$SISTEMA" "$PARES" "$PASTA/pares.csv"
    if [ "$CONDICAO" = "com_latencia" ]; then
      ./scripts/latencia_off.sh n1 n2 n3
    fi
  done
done
