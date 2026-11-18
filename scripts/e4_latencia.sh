#!/usr/bin/env bash
# Uso: ./scripts/e4_latencia.sh etcd|redis N [REPETICOES]
# E4: mesmo N do E2, 3 min, com 50 ms de atraso por sentido entre os nos (RTT 100 ms).
# O trafego gerador <-> nos nao recebe atraso. Comparar com o E2: python tabelas.py
set -euo pipefail
SISTEMA="$1"; N="$2"; REPETICOES="${3:-3}"
cd "$(dirname "$0")/.."

for R in $(seq 1 "$REPETICOES"); do
  echo "=== E4 $SISTEMA N=$N repeticao $R de $REPETICOES"
  PASTA="resultados/e4/$SISTEMA/$(date +%Y%m%d-%H%M%S)"
  ./scripts/ambiente.sh "$SISTEMA"
  mkdir -p "gerador/$PASTA"
  # Liga o netem (script fornecido): 50 ms na saida de cada no, so na rede lab_cluster.
  # "tee" mostra a saida na tela e tambem grava em latencia.txt
  ./scripts/latencia_on.sh 50ms n1 n2 n3 | tee "gerador/$PASTA/latencia.txt"
  # confirma o RTT entre nos (~100 ms) e que o gerador continua sem atraso
  { echo "n1 -> n2 (rede entre nos)"; ./scripts/rtt.sh n1 172.20.0.12
    echo "gerador -> n1 (rede de clientes)"; ./scripts/rtt.sh gerador 172.21.0.11; } > "gerador/$PASTA/rtt.txt"
  # A mesma carga do E2 (mesmo N, 180 s); depois desliga o atraso e mostra o resumo
  ./scripts/carga.sh "$SISTEMA" "$N" 180 "$PASTA"
  ./scripts/latencia_off.sh n1 n2 n3
  docker exec gerador python metricas.py "$PASTA"
done
