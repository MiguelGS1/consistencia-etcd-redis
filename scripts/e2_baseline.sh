#!/usr/bin/env bash
# Uso: ./scripts/e2_baseline.sh etcd|redis N [REPETICOES]
# E2: N otimo do E1, 3 min, sem falhas. Mostra p50/p95/p99 de GET e PUT e a vazao efetiva.
# E o experimento reproduzido ao vivo na apresentacao (ex.: ./scripts/e2_baseline.sh etcd 4 1).
set -euo pipefail
SISTEMA="$1"; N="$2"; REPETICOES="${3:-3}"
cd "$(dirname "$0")/.."

for R in $(seq 1 "$REPETICOES"); do
  echo "=== E2 $SISTEMA N=$N repeticao $R de $REPETICOES"
  PASTA="resultados/e2/$SISTEMA/$(date +%Y%m%d-%H%M%S)"
  ./scripts/ambiente.sh "$SISTEMA"
  ./scripts/carga.sh "$SISTEMA" "$N" 180 "$PASTA"
  docker exec gerador python metricas.py "$PASTA"
done
