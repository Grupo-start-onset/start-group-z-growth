# ==================================================================
# CAPTURA DE PEDIDOS DE COMPRA (Purchase Orders / VendorOrders API)
# Celula unica, consolidada, para as 7 contas do projeto START Vendor
# Analytics (ALFA JF, Blid Shop, Petclean BR, OZITP, Jolitex, Balboa,
# Rio Master).
#
# PARTE 1 -- get_purchase_orders: o pedido como foi feito (itens,
#   quantidade PEDIDA, custo, janela de entrega). Blocos mensais.
# PARTE 2 -- get_purchase_orders_status: o que aconteceu depois
#   (quantidade RECEBIDA/confirmada, cancelada, status de recebimento
#   por item). A Amazon exige range de no maximo 7 dias por chamada
#   nesse endpoint, entao aqui os blocos sao SEMANAIS.
#
# Mesmo padrao ja usado em capturar_mensal.py: monta o Drive, cache
# por bloco (arquivo ja existente = pula), retry/backoff em erro de
# cota. Roda de novo sem medo para "atualizar".
#
# DATA_FIM = hoje, sempre. DATA_INICIO = 12 meses atras.
#
# CORRIGIDO em 22/09/2026: os blocos SEMANAIS (Parte 2) sao ancorados em
# semana de calendario (segunda a domingo), nao em "DATA_INICIO bruto"
# (senao a janela deslizava 1 dia a cada execucao e o cache nunca dava match).
#
# MELHORADO em 25/09/2026:
#  - REFRESH: pedidos e status MUDAM depois de baixados (confirmacao do pedido,
#    recebimento, cancelamento). Antes, bloco em cache nunca era rebaixado e o
#    status ficava congelado. Agora todo bloco cujo fim esta nos ultimos
#    REFRESH_DIAS dias e rebaixado a cada execucao (se falhar, o arquivo
#    anterior e mantido). Blocos mais antigos continuam em cache.
#  - Blocos do periodo em andamento (fim = hoje) mudam de nome todo dia; depois
#    de baixar um bloco com sucesso, versoes antigas com o MESMO inicio (fim
#    menor, ja cobertas pelo novo) sao apagadas, para nao empilhar arquivos.
#  - Sem pausas fixas quando o bloco veio do cache (antes: ~22 min de sleep
#    mesmo sem chamar a API).
#
# Rodar na mesma sessao do Colab, depois de capturar_mensal.py e
# antes de transformar_vendor.py.
#
# Campos de status confirmados com resposta real da API (teste em
# 22/09/2026, conta Blid Shop). A quantidade ENTREGUE fica em:
#   itemStatus[].receivingStatus.receivedQuantity.amount
# e o status de recebimento em:
#   itemStatus[].receivingStatus.receiveStatus
#     ("NOT_RECEIVED" | "PARTIALLY_RECEIVED" | "RECEIVED")
# Quantidade cancelada fica em:
#   itemStatus[].orderedQuantity.orderedQuantityDetails[].cancelledQuantity
# ==================================================================

import os, time, glob, json
from datetime import datetime, timedelta
from colab_shim import drive, userdata

try:
    from sp_api.api import VendorOrders
    from sp_api.base import Marketplaces
    from sp_api.base.exceptions import SellingApiException
except ImportError:
    os.system("pip install python-amazon-sp-api -q")
    from sp_api.api import VendorOrders
    from sp_api.base import Marketplaces
    from sp_api.base.exceptions import SellingApiException

drive.mount('/content/drive', force_remount=True)

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
LWA_CLIENT_ID = userdata.get('SP_API_LWA_CLIENT_ID')
LWA_CLIENT_SECRET = userdata.get('SP_API_LWA_CLIENT_SECRET')
MARKETPLACE = Marketplaces.BR

# mesma convencao de chave/pasta/secret usada em capturar_mensal.py
CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',      'pasta': 'alfa_jf/raw',   'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'nome': 'Blid Shop',    'pasta': 'blidshop/raw',  'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'conta3':    {'nome': 'Petclean BR',  'pasta': 'petclean/raw',  'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'nome': 'OZITP',        'pasta': 'ozitp/raw',     'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'nome': 'Jolitex',      'pasta': 'jolitex/raw',   'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'nome': 'Balboa',       'pasta': 'balboa/raw',    'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'nome': 'BR - Rio Master', 'pasta': 'riomaster/raw', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
    'plastpet':  {'nome': 'Pet Factory Brazil Industria Ltda', 'pasta': 'plastpet/raw', 'secret': 'SP_API_REFRESH_TOKEN_PLASTPET'},
    'wiwu':      {'nome': 'WIWU', 'pasta': 'wiwu/raw', 'secret': 'SP_API_REFRESH_TOKEN_WIWU'},
}

DATA_FIM = datetime.today()
DATA_INICIO = DATA_FIM - timedelta(days=365)  # ultimos 12 meses

REFRESH_DIAS = 45          # blocos que terminam nos ultimos N dias sao rebaixados a cada execucao
MAX_TENTATIVAS = 5
ESPERA_ENTRE_CHAMADAS = 2  # segundos, entre paginas/blocos, pra respeitar a cota


# ------------------------------------------------------------------
# Funcoes auxiliares (mesmo padrao de blocos_mensais/caminho ja usado
# em capturar_mensal.py, adaptado pra paginacao em vez de report async)
# ------------------------------------------------------------------

def blocos_mensais(inicio, fim):
    blocos, atual = [], inicio.replace(day=1)
    while atual <= fim:
        if atual.month == 12:
            prox = atual.replace(year=atual.year + 1, month=1)
        else:
            prox = atual.replace(month=atual.month + 1)
        blocos.append((atual, min(prox - timedelta(days=1), fim)))
        atual = prox
    return blocos


def segunda_feira(data):
    """Volta 'data' pra segunda-feira daquela semana (ancora os blocos semanais)."""
    return data - timedelta(days=data.weekday())


def blocos_semanais(inicio, fim):
    """Blocos de ate 7 dias (segunda a domingo) -- exigencia do endpoint
    get_purchase_orders_status. Ancorado em semana de calendario."""
    blocos, atual = [], segunda_feira(inicio)
    while atual <= fim:
        prox_fim = min(atual + timedelta(days=6), fim)
        blocos.append((atual, prox_fim))
        atual += timedelta(days=7)
    return blocos


def caminho(pasta_raw, ini, fim):
    return f"{pasta_raw}/pedidos_{ini.strftime('%Y-%m-%d')}_a_{fim.strftime('%Y-%m-%d')}.json"


def caminho_status(pasta_raw, ini, fim):
    return f"{pasta_raw}/status_pedidos_{ini.strftime('%Y-%m-%d')}_a_{fim.strftime('%Y-%m-%d')}.json"


def precisa_baixar(alvo, fim_bloco, hoje=None):
    """True se o arquivo nao existe OU se o bloco terminou ha menos de REFRESH_DIAS dias
    (dado ainda pode mudar: confirmacao, recebimento, cancelamento)."""
    if not os.path.exists(alvo):
        return True
    hoje = hoje or datetime.today()
    return (hoje.date() - fim_bloco.date()).days < REFRESH_DIAS


def gravar_bloco(alvo, prefixo, ini, dados):
    """Grava com seguranca (arquivo temporario + troca) e apaga versoes antigas do
    MESMO inicio (fim diferente), que o novo arquivo ja cobre."""
    tmp = alvo + '.tmp'
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, alvo)
    pasta = os.path.dirname(alvo)
    for velho in glob.glob(f"{pasta}/{prefixo}_{ini.strftime('%Y-%m-%d')}_a_*.json"):
        if os.path.abspath(velho) != os.path.abspath(alvo):
            try:
                os.remove(velho)
            except OSError:
                pass


def chamar_com_retry(vendor_orders_api, **kwargs):
    """Chama get_purchase_orders com retry/backoff em erro de cota (429)."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            return vendor_orders_api.get_purchase_orders(**kwargs)
        except SellingApiException as e:
            texto_erro = str(e)
            if "QuotaExceeded" in texto_erro or "429" in texto_erro:
                espera = 2 ** tentativa
                print(f"    [cota excedida] aguardando {espera}s (tentativa {tentativa}/{MAX_TENTATIVAS})...")
                time.sleep(espera)
                continue
            raise
    raise RuntimeError("Numero maximo de tentativas excedido em get_purchase_orders")


def baixar_pedidos_bloco(vendor_orders_api, pasta_raw, ini, fim):
    """Baixa (com paginacao) todos os pedidos criados no bloco [ini, fim].
    Cache por arquivo, exceto blocos recentes (REFRESH_DIAS), que sao rebaixados."""
    alvo = caminho(pasta_raw, ini, fim)
    if not precisa_baixar(alvo, fim):
        print(f"  [em cache] pedidos {ini.date()} a {fim.date()}")
        return "cache", 0

    created_after = ini.strftime('%Y-%m-%dT00:00:00Z')
    created_before = fim.strftime('%Y-%m-%dT23:59:59Z')

    pedidos_do_bloco = []
    next_token = None
    try:
        while True:
            if next_token:
                kwargs = dict(nextToken=next_token)
            else:
                kwargs = dict(
                    createdAfter=created_after,
                    createdBefore=created_before,
                    limit=100,
                    includeDetails="true",
                )
            resp = chamar_com_retry(vendor_orders_api, **kwargs)
            payload = resp.payload or {}
            pedidos_do_bloco.extend(payload.get("orders", []))
            next_token = payload.get("pagination", {}).get("nextToken")
            time.sleep(ESPERA_ENTRE_CHAMADAS)
            if not next_token:
                break
    except Exception as e:
        print(f"  [ERRO] pedidos {ini.date()} a {fim.date()}: {e} (arquivo anterior mantido, se existir)")
        return None, 0

    gravar_bloco(alvo, "pedidos", ini, pedidos_do_bloco)
    print(f"  [OK] pedidos {ini.date()} a {fim.date()}: {len(pedidos_do_bloco)} pedidos")
    return "ok", len(pedidos_do_bloco)


def chamar_status_com_retry(vendor_orders_api, **kwargs):
    """Chama get_purchase_orders_status com retry/backoff em erro de cota (429)."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            return vendor_orders_api.get_purchase_orders_status(**kwargs)
        except SellingApiException as e:
            texto_erro = str(e)
            if "QuotaExceeded" in texto_erro or "429" in texto_erro:
                espera = 2 ** tentativa
                print(f"    [cota excedida] aguardando {espera}s (tentativa {tentativa}/{MAX_TENTATIVAS})...")
                time.sleep(espera)
                continue
            raise
    raise RuntimeError("Numero maximo de tentativas excedido em get_purchase_orders_status")


def baixar_status_bloco(vendor_orders_api, pasta_raw, ini, fim):
    """Baixa (com paginacao) o status de todos os pedidos criados no bloco
    [ini, fim] (max 7 dias). Traz quantidade recebida/cancelada por item.
    Cache por arquivo, exceto blocos recentes (REFRESH_DIAS), que sao rebaixados."""
    alvo = caminho_status(pasta_raw, ini, fim)
    if not precisa_baixar(alvo, fim):
        print(f"  [em cache] status {ini.date()} a {fim.date()}")
        return "cache", 0

    created_after = ini.strftime('%Y-%m-%dT00:00:00Z')
    created_before = fim.strftime('%Y-%m-%dT23:59:59Z')

    status_do_bloco = []
    next_token = None
    try:
        while True:
            if next_token:
                kwargs = dict(nextToken=next_token)
            else:
                kwargs = dict(
                    createdAfter=created_after,
                    createdBefore=created_before,
                    limit=100,
                )
            resp = chamar_status_com_retry(vendor_orders_api, **kwargs)
            payload = resp.payload or {}
            # atencao: get_purchase_orders_status usa a chave "ordersStatus",
            # diferente de get_purchase_orders que usa "orders"
            status_do_bloco.extend(payload.get("ordersStatus", []))
            next_token = payload.get("pagination", {}).get("nextToken")
            time.sleep(1)  # get_purchase_orders_status permite ate 10 req/s
            if not next_token:
                break
    except Exception as e:
        print(f"  [ERRO] status {ini.date()} a {fim.date()}: {e} (arquivo anterior mantido, se existir)")
        return None, 0

    gravar_bloco(alvo, "status_pedidos", ini, status_do_bloco)
    print(f"  [OK] status {ini.date()} a {fim.date()}: {len(status_do_bloco)} pedidos")
    return "ok", len(status_do_bloco)


def contar(resultado, qtd, cont):
    if resultado == "ok":
        cont['ok'] += 1
        cont['total'] += qtd
    elif resultado == "cache":
        cont['cache'] += 1
    else:
        cont['falhas'] += 1


def texto_resumo(cont, rotulo_total):
    return (f"{cont['ok']} blocos baixados/atualizados, {cont['cache']} em cache, "
            f"{cont['falhas']} falhas, {cont['total']} {rotulo_total}")


# ------------------------------------------------------------------
# PARTE 1 -- Execucao: todas as contas, blocos mensais (pedidos)
# ------------------------------------------------------------------

bmes = blocos_mensais(DATA_INICIO, DATA_FIM)
print(f"Periodo: {DATA_INICIO.date()} a {DATA_FIM.date()} ({len(bmes)} blocos mensais)")
print(f"(blocos que terminam nos ultimos {REFRESH_DIAS} dias sao rebaixados; os mais antigos ficam em cache)\n")

resumo_pedidos = {}
apis_por_conta = {}  # reaproveita a mesma instancia da API na Parte 2

for chave, cfg in CONTAS_CONFIG.items():
    nome = cfg['nome']
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    os.makedirs(pasta_raw, exist_ok=True)

    print(f"\n{'#'*60}\n# CONTA: {nome} -- PEDIDOS (quantidade pedida)\n{'#'*60}")

    credentials = dict(
        refresh_token=userdata.get(cfg['secret']),
        lwa_app_id=LWA_CLIENT_ID,
        lwa_client_secret=LWA_CLIENT_SECRET,
    )
    vendor_orders_api = VendorOrders(credentials=credentials, marketplace=MARKETPLACE)
    apis_por_conta[chave] = vendor_orders_api

    cont = dict(ok=0, cache=0, falhas=0, total=0)
    for ini, fim in bmes:
        resultado, qtd = baixar_pedidos_bloco(vendor_orders_api, pasta_raw, ini, fim)
        contar(resultado, qtd, cont)
        if resultado != "cache":
            time.sleep(5)  # pausa entre blocos (so quando chamou a API)

    resumo_pedidos[nome] = texto_resumo(cont, "pedidos")
    if cont['ok'] or cont['falhas']:
        time.sleep(10)  # pausa entre contas (so quando chamou a API)

# ------------------------------------------------------------------
# PARTE 2 -- Execucao: todas as contas, blocos semanais (status/recebido)
# ------------------------------------------------------------------

bsem = blocos_semanais(DATA_INICIO, DATA_FIM)
print(f"\n\nPeriodo: {DATA_INICIO.date()} a {DATA_FIM.date()} ({len(bsem)} blocos semanais)\n")

resumo_status = {}

for chave, cfg in CONTAS_CONFIG.items():
    nome = cfg['nome']
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    os.makedirs(pasta_raw, exist_ok=True)

    print(f"\n{'#'*60}\n# CONTA: {nome} -- STATUS (quantidade recebida/cancelada)\n{'#'*60}")

    vendor_orders_api = apis_por_conta[chave]

    cont = dict(ok=0, cache=0, falhas=0, total=0)
    for ini, fim in bsem:
        resultado, qtd = baixar_status_bloco(vendor_orders_api, pasta_raw, ini, fim)
        contar(resultado, qtd, cont)
        if resultado != "cache":
            time.sleep(2)  # pausa entre blocos (so quando chamou a API)

    resumo_status[nome] = texto_resumo(cont, "pedidos com status")
    if cont['ok'] or cont['falhas']:
        time.sleep(5)  # pausa entre contas (so quando chamou a API)

# ------------------------------------------------------------------
# RESUMO GERAL
# ------------------------------------------------------------------

print(f"\n\n{'='*60}\n=== RESUMO GERAL -- PEDIDOS (quantidade pedida) ===\n{'='*60}")
for nome, resumo in resumo_pedidos.items():
    print(f"{nome}: {resumo}")

print(f"\n{'='*60}\n=== RESUMO GERAL -- STATUS (quantidade recebida/cancelada) ===\n{'='*60}")
for nome, resumo in resumo_status.items():
    print(f"{nome}: {resumo}")

print("\nSe aparecer [ERRO] em algum bloco, rode a celula de novo --")
print("os blocos que ja deram [OK] e sao antigos ficam em cache; os recentes sao sempre atualizados.")
