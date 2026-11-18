#!/usr/bin/env bash
# Uso: ./scripts/ambiente.sh etcd|redis
# Parte de um ambiente limpo: derruba os dois clusters (down -v apaga os dados), sobe o
# escolhido, espera ficar saudavel e grava as 10.000 chaves iniciais.
# Todos os experimentos chamam este script antes de cada execucao (o enunciado pede
# partir de um ambiente limpo, com down -v + up -d, e esperar o cluster ficar saudavel).
# set -e: para no primeiro erro; -u: erro se usar variavel nao definida;
# -o pipefail: um erro no meio de um "a | b" tambem conta como erro.
set -euo pipefail
SISTEMA="$1"
# Vai para a raiz do projeto (a pasta acima de scripts/), onde estao os arquivos compose
cd "$(dirname "$0")/.."

# Os dois compose usam os mesmos nomes de conteiner e de rede: so um cluster por vez.
# down -v remove os conteineres, as redes e os volumes (os dados dos nos).
docker compose -f etcd.yml down -v 2>/dev/null
docker compose -f redis.yml down -v 2>/dev/null
# Sobe n1, n2, n3 e o gerador em segundo plano (-d)
docker compose -f "$SISTEMA.yml" up -d

# Espera o cluster ficar saudavel.
# "until ...; do sleep 1; done" repete o teste a cada 1 s ate ele dar certo.
if [ "$SISTEMA" = "etcd" ]; then
  # os tres membros respondem e o cluster tem lider (quorum)
  until docker exec n1 etcdctl --endpoints=http://172.21.0.11:2379,http://172.21.0.12:2379,http://172.21.0.13:2379 \
        endpoint health >/dev/null 2>&1; do sleep 1; done
else
  # as duas replicas terminaram a sincronizacao inicial com o primario
  # (o "info replication" do primario lista cada replica com state=online quando ela esta em dia)
  until [ "$(docker exec n1 redis-cli info replication | grep -c 'state=online')" = "2" ]; do sleep 1; done
fi
echo "cluster $SISTEMA saudavel"

# Grava k0 ... k9999 antes da medicao (gerador/carga_inicial.py, dentro do conteiner gerador)
docker exec gerador python carga_inicial.py "$SISTEMA"
