#!/usr/bin/env bash
# Uso: ./scripts/ambiente.sh etcd|redis
# Parte de um ambiente limpo: derruba os dois clusters (down -v apaga os dados), sobe o
# escolhido, espera ficar saudavel e grava as 10.000 chaves iniciais.
set -euo pipefail
SISTEMA="$1"
cd "$(dirname "$0")/.."

# Os dois compose usam os mesmos nomes de conteiner e de rede: so um cluster por vez.
docker compose -f etcd.yml down -v 2>/dev/null
docker compose -f redis.yml down -v 2>/dev/null
docker compose -f "$SISTEMA.yml" up -d

# Espera o cluster ficar saudavel.
if [ "$SISTEMA" = "etcd" ]; then
  # os tres membros respondem e o cluster tem lider (quorum)
  until docker exec n1 etcdctl --endpoints=http://172.21.0.11:2379,http://172.21.0.12:2379,http://172.21.0.13:2379 \
        endpoint health >/dev/null 2>&1; do sleep 1; done
else
  # as duas replicas terminaram a sincronizacao inicial com o primario
  until [ "$(docker exec n1 redis-cli info replication | grep -c 'state=online')" = "2" ]; do sleep 1; done
fi
echo "cluster $SISTEMA saudavel"

docker exec gerador python carga_inicial.py "$SISTEMA"
