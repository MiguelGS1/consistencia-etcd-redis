#!/usr/bin/env bash
# Uso: ./scripts/e5_particao.sh etcd|redis N [REPETICOES]
# E5: carga do E2 com clientes em todos os nos. Aos 30 s isola o n1 dos outros nos por 60 s,
# depois cura a particao e deixa a carga rodar mais 90 s. No fim verifica a convergencia,
# procura escritas confirmadas perdidas e gera a linha do tempo.
set -euo pipefail
SISTEMA="$1"; N="$2"; REPETICOES="${3:-3}"
cd "$(dirname "$0")/.."

# Registra um evento no relogio do conteiner gerador (o mesmo relogio das amostras)
evento() { echo "$(docker exec gerador date +%s.%N),$1" >> "gerador/$PASTA/eventos.csv"; }

for R in $(seq 1 "$REPETICOES"); do
  echo "=== E5 $SISTEMA N=$N repeticao $R de $REPETICOES"
  PASTA="resultados/e5/$SISTEMA/$(date +%Y%m%d-%H%M%S)"
  ./scripts/ambiente.sh "$SISTEMA"
  mkdir -p "gerador/$PASTA"
  if [ "$SISTEMA" = "etcd" ]; then
    docker exec n1 etcdctl --endpoints=http://172.21.0.11:2379 endpoint status --cluster -w table \
      > "gerador/$PASTA/lider_antes.txt"
  fi

  ./scripts/carga.sh "$SISTEMA" "$N" 180 "$PASTA" &   # 30 s normal + 60 s particao + 90 s depois
  CARGA=$!
  sleep 30
  evento "particao n1"
  ./scripts/particao.sh
  INICIO=$SECONDS

  # Verificacao obrigatoria do apendice (A.9): se algum item der errado, o resultado nao vale
  { echo "n2 -> n3 (deve funcionar)";                         ./scripts/rtt.sh n2 172.20.0.13 || true
    echo "n1 -> n2 (deve falhar)";                            ./scripts/rtt.sh n1 172.20.0.12 || true
    echo "gerador -> n1, rede de clientes (deve funcionar)";  ./scripts/rtt.sh gerador 172.21.0.11 || true
  } > "gerador/$PASTA/verificacao_particao.txt" 2>&1

  sleep $((60 - (SECONDS - INICIO)))   # completa os 60 s de particao
  evento "cura n1"
  ./scripts/cura.sh
  wait $CARGA

  # Logs dos nos: eleicao e pre-vote no etcd; reconexao e ressincronizacao das replicas no Redis
  for NO in n1 n2 n3; do docker logs "$NO" > "gerador/$PASTA/log_$NO.txt" 2>&1; done
  docker exec gerador python convergencia.py "$SISTEMA" "$PASTA"
  docker exec gerador python linha_tempo.py "$PASTA"
done
