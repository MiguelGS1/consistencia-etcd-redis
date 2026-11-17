# Consistência, latência e vazão em armazenamento replicado

etcd (consistência forte, Raft) × Redis (consistência eventual, 1 primário + 2 réplicas
assíncronas), cada um com 3 nós em Docker Compose. Trabalho T2 de Sistemas Distribuídos,
Miguel Gheno, Pedro Nunes e Max Breuel.

## Requisitos

- Docker com Compose v2 (testado no Docker Desktop para Mac, Apple Silicon).
- Bash no host para os scripts. Todo o Python roda dentro do contêiner `gerador`.

## Estrutura

- `etcd.yml`, `redis.yml`: cluster de 3 nós (n1, n2, n3) e o contêiner `gerador`.
- `scripts/`: ambiente limpo, carga, um script por experimento (E1 a E6) e os scripts de
  latência, partição e RTT.
- `gerador/`: gerador de carga, adaptadores, coordenador do E3 e análise. Os resultados ficam
  em `gerador/resultados/`, uma pasta por execução, com data e hora.

## Como rodar

Todos os comandos são executados na raiz do repositório. Cada execução parte de um ambiente
limpo (`down -v` e `up -d`), espera o cluster ficar saudável e grava as 10.000 chaves iniciais.
Para execuções longas, use `caffeinate -i` para o Mac não dormir.

```bash
./scripts/e1_saturacao.sh etcd                # E1: N = 1 a 512, 2 min por ponto, 3 repetições
./scripts/e1_saturacao.sh redis
docker exec gerador python grafico_e1.py      # curva p99 × vazão, N ótimo e vazão máxima

./scripts/e2_baseline.sh etcd N               # E2: N ótimo do E1, 3 min
./scripts/e3_stale.sh etcd                    # E3: 10.000 pares, sem e com latência
./scripts/e4_latencia.sh etcd N               # E4: RTT de 100 ms entre os nós
./scripts/e5_particao.sh etcd N               # E5: n1 isolado por 60 s
./scripts/e6_failover.sh etcd N lider         # E6: docker kill do líder (ou: seguidor)
docker exec gerador python tabelas.py         # tabelas do E2 × E4 e do E3
```

Os mesmos comandos valem com `redis` no lugar de `etcd`. O número de repetições é o último
argumento opcional de cada script. O N ótimo que encontramos no E1 foi 4 no etcd e 8 no
Redis. Por exemplo, o E2 ao vivo na apresentação, com uma execução só:

```bash
./scripts/e2_baseline.sh etcd 4 1
```
