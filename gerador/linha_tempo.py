"""
E5 e E6: linha do tempo de completações e erros por segundo, com os eventos marcados.

Uso: python linha_tempo.py PASTA
Lê as amostras, execucao.txt e eventos.csv da pasta e gera PASTA/linha_tempo.png.

As amostras são separadas pelo nó que atendeu: o nó alvo dos eventos (isolado no E5,
morto no E6) e os outros nós. O script imprime as escritas e leituras de cada lado
durante a falha e, no E6, a taxa de erros e o tempo de failover.

Também conta os GETs com sucesso que não acharam a chave. Como a carga inicial grava
todas as 10.000 chaves, um GET sem valor significa dado perdido (ex.: primário do
Redis que reinicia vazio e apaga as réplicas).

Tempo de failover (a mesma definição nos dois sistemas): a maior pausa sem nenhum PUT
confirmado, começando entre o kill e o docker start. É o tempo em que o sistema ficou
sem aceitar escritas (ex.: eleição de um novo líder no etcd).
Também é impressa a última escrita com erro depois da falha: mostra quando o último
cliente se recuperou, incluindo o timeout de 2 s e a troca de nó (reconfiguração).
"""
import csv
import os
import sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")  # gera o PNG sem abrir janela
import matplotlib.pyplot as plt

from metricas import ler_amostras, ler_execucao

CORES = {"alvo": "#2a78d6", "outros": "#eb6834"}  # azul e laranja da paleta categórica
TEXTO = "#52514e"


def ler_eventos(pasta):
    """Linhas 'instante,evento', ex.: '1794705111.73,kill n2'."""
    with open(os.path.join(pasta, "eventos.csv"), newline="") as f:
        return [(float(t), nome) for t, nome in csv.reader(f)]


def main():
    pasta = sys.argv[1]
    inicio, _ = ler_execucao(pasta)
    eventos = ler_eventos(pasta)
    alvo = eventos[0][1].split()[-1]  # ex.: "kill n2" -> n2
    inicio_falha, fim_falha = eventos[0][0], eventos[1][0]

    por_segundo = Counter()   # (segundo, operação, lado, sucesso) -> quantidade
    na_falha = Counter()      # (operação, lado, sucesso) -> quantidade, entre os dois eventos
    sem_valor = Counter()     # segundo -> GETs com sucesso que não acharam a chave
    fins_put_ok = []          # instantes de fim dos PUTs confirmados (para achar a pausa)
    ultima_escrita_com_erro = None
    for a in ler_amostras(pasta):
        lado = "alvo" if a["no"] == alvo else "outros"
        chave = (a["operacao"], lado, a["sucesso"])
        segundo = int(a["fim"] - inicio)  # pelo instante de fim (completação)
        por_segundo[(segundo,) + chave] += 1
        if inicio_falha <= a["fim"] < fim_falha:
            na_falha[chave] += 1
        if a["operacao"] == "GET" and a["sucesso"] and a["valor"] == "":
            sem_valor[segundo] += 1
        if a["operacao"] == "PUT" and a["sucesso"]:
            fins_put_ok.append(a["fim"])
        if a["operacao"] == "PUT" and not a["sucesso"] and a["fim"] >= inicio_falha:
            ultima_escrita_com_erro = max(a["fim"], ultima_escrita_com_erro or 0)

    # maior pausa sem nenhum PUT confirmado, começando entre a falha e a volta do nó
    fins_put_ok.sort()
    pausa = 0.0
    for antes, depois in zip(fins_put_ok, fins_put_ok[1:]):
        comeco = max(antes, inicio_falha)
        if depois > inicio_falha and comeco < fim_falha:
            pausa = max(pausa, depois - comeco)

    # gráfico: completações com sucesso, erros e GETs sem valor, um painel cada
    segundos = list(range(max(s for s, *_ in por_segundo) + 1))
    fig, (ax_ok, ax_erro, ax_vazio) = plt.subplots(3, 1, figsize=(10, 8), sharex=True,
                                                   gridspec_kw={"height_ratios": [3, 3, 2]})
    for lado in ["alvo", "outros"]:
        for op, estilo in [("PUT", "-"), ("GET", "--")]:
            rotulo = f"{op} no {alvo}" if lado == "alvo" else f"{op} nos outros nós"
            for ax, sucesso in [(ax_ok, True), (ax_erro, False)]:
                ax.plot(segundos, [por_segundo[(s, op, lado, sucesso)] for s in segundos], estilo,
                        color=CORES[lado], linewidth=1.6, label=rotulo)
    ax_vazio.plot(segundos, [sem_valor[s] for s in segundos], color=TEXTO, linewidth=1.6)
    for t, nome in eventos:
        for ax in (ax_ok, ax_erro, ax_vazio):
            ax.axvline(t - inicio, color=TEXTO, linewidth=1, linestyle=":")
        ax_ok.annotate(nome, (t - inicio, 1), xycoords=("data", "axes fraction"), xytext=(3, -12),
                       textcoords="offset points", fontsize=8, color=TEXTO)
    ax_ok.set_ylabel("completações com sucesso / s")
    ax_erro.set_ylabel("erros / s")
    ax_vazio.set_ylabel("GETs sem valor / s")
    ax_vazio.set_xlabel("tempo desde o início da carga (s)")
    ax_ok.set_title(f"Linha do tempo: {os.path.normpath(pasta)}", fontsize=11)
    for ax in (ax_ok, ax_erro, ax_vazio):
        ax.grid(True, color="#e5e4e0", linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    ax_ok.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))  # fora do gráfico
    fig.savefig(os.path.join(pasta, "linha_tempo.png"), dpi=150, bbox_inches="tight")

    # escritas e leituras de cada lado durante a falha
    linhas = [f"entre '{eventos[0][1]}' e '{eventos[1][1]}' ({fim_falha - inicio_falha:.0f} s):"]
    for lado in ["alvo", "outros"]:
        onde = f"no {alvo}" if lado == "alvo" else "nos outros nós"
        for op in ["PUT", "GET"]:
            linhas.append(f"  {op} {onde:15} {na_falha[(op, lado, True)]:9} com sucesso, "
                          f"{na_falha[(op, lado, False)]:7} com erro")
    linhas.append(f"  GETs sem valor (chave perdida) na execução inteira: {sum(sem_valor.values())}")
    linhas.append(f"  maior pausa sem nenhum PUT confirmado: {pausa:.2f} s")

    if eventos[0][1].startswith("kill"):
        total = sum(na_falha.values())
        erros = sum(v for (op, lado, sucesso), v in na_falha.items() if not sucesso)
        linhas.append(f"  taxa de erros durante a falha: {100 * erros / max(1, total):.2f}%")
        linhas.append(f"  tempo de failover (= a maior pausa sem PUT confirmado): {pausa:.2f} s")
        ultimo_erro = ultima_escrita_com_erro - inicio_falha if ultima_escrita_com_erro else 0.0
        linhas.append(f"  última escrita com erro (inclui timeout e troca de nó do cliente): "
                      f"{ultimo_erro:.2f} s depois do kill")

    print("\n".join(linhas))
    with open(os.path.join(pasta, "linha_tempo.txt"), "w") as f:
        f.write("\n".join(linhas) + "\n")
    print(f"gráfico: {os.path.join(pasta, 'linha_tempo.png')}")


if __name__ == "__main__":
    main()
