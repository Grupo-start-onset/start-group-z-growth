# ==================================================================
# publicar_github.py
# Publica o dados_vendor.json (gerado pela celula transformar_vendor.py)
# no repositorio GitHub Pages Grupo-start-onset/STARTZ.
#
# Pre-requisito: secret GITHUB_TOKEN configurado no Colab (Personal
# Access Token do GitHub, Settings -> Developer settings -> Tokens).
#
# Rodar SEMPRE por ultimo, depois de transformar_vendor.py ter gerado
# o dados_vendor.json na pasta atual do Colab.
#
# O que este script publica, num commit so:
#   1. dados_vendor.json           (geral, todas as contas — mantido igual)
#   2. dados/index.json            (NOVO — lista de contas + meses, ~poucos KB)
#      dados/<conta_id>.json       (NOVO — uma conta por arquivo)
#      O dashboard geral passou a carregar so a conta escolhida a partir
#      de dados/, em vez de baixar o dados_vendor.json inteiro (~8 MB).
#      Se dados/index.json nao existir, o dashboard cai automaticamente
#      para o dados_vendor.json (por isso ele continua sendo publicado).
#   3. clientes/<conta_id>/dados_vendor.json  (copia isolada, so daquela
#      conta, para cada conta que ja tenha a pasta clientes/<conta_id>/
#      no repositorio — dashboards individuais enviados a clientes).
#      Para isolar uma nova conta, basta criar a pasta clientes/<conta_id>/
#      no repo (com dashboard_base.html, styles.css e app.js dentro) uma
#      unica vez — a partir da proxima publicacao o dados_vendor.json
#      dessa pasta passa a ser mantido automaticamente por este script.
#
# ATENCAO: use SEMPRE esta versao. Se um dia o dados_vendor.json for
# publicado por uma versao antiga do script, dados/ fica desatualizado e
# o dashboard geral mostra dados velhos (a data em "Dados de ..." no
# rodape do menu lateral denuncia isso).
# ==================================================================

import os, json, subprocess, shutil
from datetime import datetime, timezone

GITHUB_USUARIO = 'Grupo-start-onset'
GITHUB_REPO = 'start-group-z-growth'
# Este script já roda de dentro do próprio checkout do repositório
# (não precisa mais clonar com token embutido na URL): PASTA_REPO é a
# raiz do repositório, calculada a partir da localização deste arquivo.
PASTA_REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))


def rodar(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
    return r


# --- INICIO gerar_dados_por_conta (funcao pura de arquivos; testada a parte) ---
def meta_conta(c):
    """Resumo leve de uma conta para o dados/index.json: nome e as listas de
    meses que o dashboard usa para montar filtros SEM precisar baixar a conta."""
    pedidos = sorted({(p.get('data') or '')[:7] for p in (c.get('pedidos') or []) if p.get('data')})
    return {
        'nome': c.get('nome'),
        'meses': sorted((c.get('aggVendas') or {}).keys()),
        'futuros': sorted((c.get('previsaoMes') or {}).keys()),
        'sellin': sorted(set((c.get('sellinMes') or {}).keys()) | set((c.get('sellinRecebidoMes') or {}).keys())),
        'pedidos': pedidos,
    }


def gerar_dados_por_conta(contas, pasta_repo, git_status):
    """Escreve <pasta_repo>/dados/<conta>.json (uma conta por arquivo, objeto da
    conta direto, sem envolver em {conta: ...}) e <pasta_repo>/dados/index.json.
    Remove arquivos de contas que sairam do JSON. 'geradoEm' so muda quando algum
    arquivo de conta mudou (git_status() -> saida de 'git status --porcelain -- dados'),
    para que uma republicacao sem mudanca continue sem gerar commit.
    Retorna a lista de contas escritas."""
    pasta = os.path.join(pasta_repo, 'dados')
    os.makedirs(pasta, exist_ok=True)

    for conta_id, c in contas.items():
        with open(os.path.join(pasta, f'{conta_id}.json'), 'w', encoding='utf-8') as f:
            json.dump(c, f, ensure_ascii=False, separators=(',', ':'))

    for arq in os.listdir(pasta):
        if arq.endswith('.json') and arq != 'index.json' and arq[:-5] not in contas:
            os.remove(os.path.join(pasta, arq))
            print(f'Removido dados/{arq} (conta nao esta mais no JSON)')

    caminho_indice = os.path.join(pasta, 'index.json')
    gerado_em = None
    if not git_status().strip() and os.path.exists(caminho_indice):
        try:
            gerado_em = json.load(open(caminho_indice, encoding='utf-8')).get('geradoEm')
        except Exception:
            gerado_em = None
    if not gerado_em:
        gerado_em = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    indice = {'geradoEm': gerado_em, 'contas': {k: meta_conta(c) for k, c in contas.items()}}
    with open(caminho_indice, 'w', encoding='utf-8') as f:
        json.dump(indice, f, ensure_ascii=False, separators=(',', ':'))
    return list(contas.keys())
# --- FIM gerar_dados_por_conta ---


# 1. Atualiza o checkout local (sem clone/token: já rodamos dentro do repo)
rodar(['git', '-C', PASTA_REPO, 'pull'])

# 2. dados_vendor.json já é escrito direto na raiz do repo pelo
# transformar_vendor.py (SAIDA aponta pra cá) -- nada a copiar.
destino = os.path.join(PASTA_REPO, 'dados_vendor.json')
assert os.path.exists(destino), (
    f'{destino} não encontrado -- rode transformar_vendor.py primeiro, '
    'antes deste script.'
)
print(f'Usando: {destino} ({os.path.getsize(destino):,} bytes)')

# 3. Configura identidade do git (necessario para o commit)
rodar(['git', '-C', PASTA_REPO, 'config', 'user.email', 'pipeline@startgrupo.com'])
rodar(['git', '-C', PASTA_REPO, 'config', 'user.name', 'START Vendor Analytics (pipeline)'])

with open(destino, encoding='utf-8') as f:
    CONTAS = json.load(f)

# 4. NOVO — divide o JSON por conta em dados/ (carregamento sob demanda no dashboard geral)
contas_divididas = gerar_dados_por_conta(
    CONTAS, PASTA_REPO,
    git_status=lambda: subprocess.run(
        ['git', '-C', PASTA_REPO, 'status', '--porcelain', '--', 'dados'],
        capture_output=True, text=True).stdout)
tamanho_dados = sum(os.path.getsize(f'{PASTA_REPO}/dados/{c}.json') for c in contas_divididas)
print(f'dados/: index.json + {len(contas_divididas)} contas ({tamanho_dados:,} bytes no total; '
      f'o dashboard baixa so a conta escolhida)')

# 5. Gera uma copia isolada do JSON para cada conta que ja tenha
#    uma pasta clientes/<conta_id>/ publicada no repo (dashboard individual)
pasta_clientes = f'{PASTA_REPO}/clientes'
contas_isoladas = []
if os.path.isdir(pasta_clientes):
    for conta_id in sorted(CONTAS.keys()):
        pasta_conta = os.path.join(pasta_clientes, conta_id)
        if os.path.isdir(pasta_conta):
            destino_conta = os.path.join(pasta_conta, 'dados_vendor.json')
            with open(destino_conta, 'w', encoding='utf-8') as f:
                json.dump({conta_id: CONTAS[conta_id]}, f, ensure_ascii=False)
            contas_isoladas.append(conta_id)
            print(f'Copia isolada atualizada: clientes/{conta_id}/dados_vendor.json '
                  f'({os.path.getsize(destino_conta):,} bytes)')

if not contas_isoladas:
    print('Nenhuma pasta clientes/<conta>/ encontrada no repo — nada a isolar desta vez.')

# 6. Adiciona tudo (geral + dados/ + isoladas) e publica num commit so
rodar(['git', '-C', PASTA_REPO, 'add', 'dados_vendor.json'])
rodar(['git', '-C', PASTA_REPO, 'add', '-A', 'dados'])
for conta_id in contas_isoladas:
    rodar(['git', '-C', PASTA_REPO, 'add', f'clientes/{conta_id}/dados_vendor.json'])

if contas_isoladas:
    msg = (f'Atualiza dados (geral + dados/ por conta + isolados: {", ".join(contas_isoladas)}) '
           f'— {datetime.now().strftime("%Y-%m-%d %H:%M")}')
else:
    msg = f'Atualiza dados (geral + dados/ por conta) — {datetime.now().strftime("%Y-%m-%d %H:%M")}'

r = subprocess.run(['git', '-C', PASTA_REPO, 'commit', '-m', msg], capture_output=True, text=True)
if 'nothing to commit' in (r.stdout + r.stderr):
    print('Nada mudou desde a ultima publicacao -- nada a enviar.')
else:
    print(r.stdout)
    rodar(['git', '-C', PASTA_REPO, 'push'])
    print(f'\nPublicado! Em 1-2 minutos os links devem refletir os dados novos:')
    print(f'https://{GITHUB_USUARIO.lower()}.github.io/{GITHUB_REPO}/dashboard_base.html')
    for conta_id in contas_isoladas:
        print(f'https://{GITHUB_USUARIO.lower()}.github.io/{GITHUB_REPO}/clientes/{conta_id}/dashboard_base.html')
