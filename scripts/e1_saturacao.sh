#!/usr/bin/env bash
# Uso: ./scripts/e1_saturacao.sh etcd|redis [REPETICOES]
# E1: varia N = 1, 2, 4, ..., 512, 2 min por ponto, sem falhas.
# Cada ponto parte de um ambiente limpo. Os primeiros 30 s sao descartados na analise.
# Depois de rodar os dois sistemas: docker exec gerador python grafico_e1.py
set -euo pipefail
SISTEMA="$1"; REPETICOES="${2:-3}"   # 3 repeticoes se nao for informado
cd "$(dirname "$0")/.."

# Repeticao por fora e N por dentro: cada repeticao percorre a curva inteira
for R in $(seq 1 "$REPETICOES"); do
  for N in 1 2 4 8 16 32 64 128 256 512; do
    echo "=== E1 $SISTEMA N=$N repeticao $R de $REPETICOES"
    ./scripts/ambiente.sh "$SISTEMA"
    # 120 s de carga; a pasta leva o N e a data/hora, para cada execucao ter a sua
    ./scripts/carga.sh "$SISTEMA" "$N" 120 "resultados/e1/$SISTEMA/N$N/$(date +%Y%m%d-%H%M%S)"
  done
done
