"""
Adaptadores finos: a única parte do código que muda entre os dois sistemas.

O enunciado pede a mesma lógica de carga para os dois sistemas, com um adaptador
fino por sistema. Por isso o gerador, o coordenador e a verificação nunca falam
direto com o etcd ou com o Redis: eles chamam sempre as mesmas operações,
e cada adaptador traduz para o protocolo do seu sistema.

Cada adaptador fala com UM nó e oferece as mesmas operações:
  put(chave, valor)  grava; levanta exceção em caso de erro ou timeout
  get(chave)         devolve o valor (texto) ou None se a chave não existe
  get_local(chave)   lê o estado local do nó (usado só para verificar convergência)
e informa qual nó atende cada operação (no_put e no_get), para a amostra registrar.
"""
import base64

import redis      # cliente oficial do Redis para Python (protocolo RESP, porta 6379)
import requests   # cliente HTTP, usado para a API HTTP/JSON do etcd (porta 2379)

TIMEOUT = 2.0  # segundos por requisição (enunciado: "ex.: 2 s")

# IPs dos nós na rede de clientes (lab_clientes), iguais nos dois arquivos compose.
# O gerador só está nessa rede, que nunca recebe atraso nem partição; o tráfego entre
# os nós (replicação, Raft) passa pela outra rede, lab_cluster (172.20.0.x).
IPS = {"n1": "172.21.0.11", "n2": "172.21.0.12", "n3": "172.21.0.13"}


def b64(texto):
    """A API HTTP do etcd recebe chaves e valores em base64."""
    # A API HTTP do etcd é uma tradução automática da API gRPC, em que chave e valor são
    # bytes. No JSON, bytes viram texto em base64. Por isso codificamos aqui e decodificamos no get.
    return base64.b64encode(texto.encode()).decode()


class Etcd:
    """etcd (Raft) pela API HTTP/JSON, porta 2379.
    Escrita: só volta com sucesso depois de gravada (com fsync) na maioria dos nós.
    Leitura: linearizável, que é o padrão do /v3/kv/range."""

    def __init__(self, no):
        # Os dois atributos abaixo dizem qual nó atende cada operação. Vão para a amostra
        # (coluna "no") e permitem separar os lados no E5 e o nó morto no E6.
        self.no_put = no   # qualquer nó aceita a escrita; um seguidor repassa ao líder
        self.no_get = no
        self.url = f"http://{IPS[no]}:2379/v3/kv"
        self.sessao = requests.Session()  # reaproveita a conexão TCP entre requisições

    def put(self, chave, valor):
        # POST /v3/kv/put: o nó só responde depois que a escrita foi gravada na maioria
        # (líder + pelo menos 1 seguidor), confirmada (commit) pelo Raft e aplicada.
        # O timeout de 2 s vale para conectar e para esperar a resposta.
        r = self.sessao.post(self.url + "/put", json={"key": b64(chave), "value": b64(valor)},
                             timeout=TIMEOUT)
        r.raise_for_status()  # resposta de erro do etcd (ex.: sem líder) vira exceção

    def get(self, chave, serializable=False):
        # POST /v3/kv/range com uma chave só. Sem "serializable", a leitura é linearizável:
        # o nó confirma com o líder e a maioria (ReadIndex) antes de responder, então
        # nunca devolve um valor mais antigo que uma escrita já confirmada.
        corpo = {"key": b64(chave)}
        if serializable:
            corpo["serializable"] = True  # lê só o estado local do nó, sem consultar a maioria
        r = self.sessao.post(self.url + "/range", json=corpo, timeout=TIMEOUT)
        r.raise_for_status()
        # A resposta traz a lista "kvs" com os pares encontrados. Se a chave não existe,
        # o campo nem aparece no JSON.
        kvs = r.json().get("kvs")
        if not kvs:
            return None
        return base64.b64decode(kvs[0]["value"]).decode()

    def get_local(self, chave):
        # Uma leitura linearizável passaria pelo líder e esconderia diferenças entre os nós
        return self.get(chave, serializable=True)


class Redis:
    """Redis com 1 primário (n1) e 2 réplicas assíncronas (n2, n3).
    Escrita: só no primário; volta com sucesso sem esperar as réplicas.
    Leitura: no nó do cliente, que pode ser uma réplica atrasada."""

    def __init__(self, no):
        self.no_put = "n1"   # as réplicas recusam escrita (READONLY)
        self.no_get = no
        # Duas conexões: uma com o primário, para os PUTs, e uma com o nó da thread, para os GETs.
        # socket_timeout limita a espera pela resposta; socket_connect_timeout limita a
        # conexão (ex.: nó morto no E6). Os dois usam o mesmo timeout de 2 s do etcd.
        self.primario = redis.Redis(host=IPS["n1"], socket_timeout=TIMEOUT,
                                    socket_connect_timeout=TIMEOUT)
        self.local = redis.Redis(host=IPS[no], socket_timeout=TIMEOUT,
                                 socket_connect_timeout=TIMEOUT)

    def put(self, chave, valor):
        # SET no primário. Ele responde OK assim que aplica a escrita na própria memória;
        # a cópia para as réplicas acontece depois, em segundo plano (replicação assíncrona).
        self.primario.set(chave, valor)

    def get(self, chave):
        # GET no nó da thread. Numa réplica, devolve o que ela tiver recebido até agora,
        # que pode ser um valor antigo. O cliente devolve bytes, então convertemos para texto.
        valor = self.local.get(chave)
        return None if valor is None else valor.decode()

    def get_local(self, chave):
        return self.get(chave)  # no Redis cada nó já responde com o próprio estado


def criar(sistema, no):
    """Cria o adaptador do sistema escolhido, ligado ao nó indicado."""
    # É o único ponto em que o resto do código escolhe o sistema.
    if sistema == "etcd":
        return Etcd(no)
    if sistema == "redis":
        return Redis(no)
    raise ValueError("sistema deve ser etcd ou redis")
