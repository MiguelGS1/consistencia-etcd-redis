#!/usr/bin/env bash
# Uso: ./scripts/e6_failover.sh etcd|redis N lider|seguidor [REPETICOES]
# E6: carga do E2, sem latencia extra. Aos 30 s mata um no (docker kill), 60 s depois
# reinicia (docker start) e deixa a carga rodar mais 90 s. Os clientes trocam de no
# depois de um erro (--troca-no), entao o failover medido inclui essa reconfiguracao.
#   lider:    etcd -> lider atual do Raft;   redis -> n1 (primario)
#   seguidor: etcd -> um no que nao e lider; redis -> n3 (replica)
set -euo pipefail
SISTEMA="$1"; N="$2"; VARIANTE="$3"; REPETICOES="${4:-3}"
cd "$(dirname "$0")/.."

# Registra um evento no relogio do conteiner gerador (o mesmo relogio das amostras)
evento() { echo "$(docker exec gerador date +%s.%N),$1" >> "gerador/$PASTA/eventos.csv"; }

for R in $(seq 1 "$REPETICOES"); do
  echo "=== E6 $SISTEMA N=$N $VARIANTE repeticao $R de $REPETICOES"
  PASTA="resultados/e6/$SISTEMA/$VARIANTE/$(date +%Y%m%d-%H%M%S)"
  ./scripts/ambiente.sh "$SISTEMA"
  mkdir -p "gerador/$PASTA"

  # Escolhe o no alvo
  if [ "$SISTEMA" = "etcd" ]; then
    # O lider do Raft muda de uma execucao para outra, entao e consultado na hora
    docker exec n1 etcdctl --endpoints=http://172.21.0.11:2379 endpoint status --cluster -w table \
      > "gerador/$PASTA/lider_antes.txt"
    # a linha com IS LEADER = true tem o endereco do lider: 172.21.0.1X -> nX
    LIDER=$(grep true "gerador/$PASTA/lider_antes.txt" | sed 's/.*172\.21\.0\.1\([1-3]\):2379.*/n\1/')
    if [ "$VARIANTE" = "lider" ]; then
      ALVO="$LIDER"
    else
      # seguidor: o primeiro no da lista que nao e o lider
      for NO in n1 n2 n3; do
        if [ "$NO" != "$LIDER" ]; then ALVO="$NO"; break; fi
      done
    fi
  else
    # No Redis a topologia e fixa: n1 e sempre o primario
    if [ "$VARIANTE" = "lider" ]; then ALVO=n1; else ALVO=n3; fi
  fi
  echo "alvo: $ALVO ($VARIANTE)" | tee "gerador/$PASTA/alvo.txt"

  # Carga em segundo plano, com --troca-no para os clientes sairem do no morto
  ./scripts/carga.sh "$SISTEMA" "$N" 180 "$PASTA" --troca-no &   # 30 s + 60 s fora + 90 s depois
  CARGA=$!
  sleep 30
  # docker kill manda SIGKILL: o processo morre na hora, sem desligamento organizado (queda)
  evento "kill $ALVO"
  docker kill "$ALVO" >/dev/null
  sleep 60
  # docker start religa o mesmo conteiner (no Redis, sem persistencia, ele volta vazio)
  evento "start $ALVO"
  docker start "$ALVO" >/dev/null
  wait $CARGA

  # No etcd, guarda quem ficou lider depois da falha
  if [ "$SISTEMA" = "etcd" ]; then
    docker exec n1 etcdctl --endpoints=http://172.21.0.11:2379 endpoint status --cluster -w table \
      > "gerador/$PASTA/lider_depois.txt"
  fi
  # Logs dos nos: eleicao e termo no etcd; ressincronizacao ("Full resync", "Flushing old data") no Redis
  for NO in n1 n2 n3; do docker logs "$NO" > "gerador/$PASTA/log_$NO.txt" 2>&1; done
  # Escritas perdidas e linha do tempo (com o tempo de failover e a taxa de erros)
  docker exec gerador python convergencia.py "$SISTEMA" "$PASTA"
  docker exec gerador python linha_tempo.py "$PASTA"
done
