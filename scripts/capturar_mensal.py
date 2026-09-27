# ==================================================================
# CAPTURA MENSAL — Vendas, Estoque, Trafego, Margem
# Celula unica, consolidada, para as 7 contas do projeto START Vendor
# Analytics (ALFA JF, Blid Shop, Petclean BR, OZITP, Jolitex, Balboa,
# Rio Master).
#
# Baseada no padrao mais robusto ja usado (cache por mes, retry,
# blocos_mensais/baixar_relatorio da recaptura da Petclean).
#
# CORRIGIDO em 25/09/2026:
#  - O relatorio MONTH da Amazon exige o mes INTEIRO (dataEndTime = ultimo
#    dia do mes). O script pedia o mes em andamento com fim = hoje (ex.:
#    01/09 a 25/09) e a Amazon recusava com FATAL -- por isso o dashboard
#    parava sempre no mes anterior. Agora so sao pedidos MESES FECHADOS
#    (ultimo dia do mes ja passou ha pelo menos ATRASO_DIAS dias). O mes em
#    andamento e coberto por SEMANAS no capturar_semanal.py.
#  - Cobre as 7 contas (antes a lista tinha so 5: faltavam Balboa e Rio Master).
#
# DATA_FIM = hoje, sempre -- nao precisa editar nada pra "atualizar":
# so rodar de novo. O cache por arquivo pula blocos ja baixados.
#
# Rodar ANTES de transformar_vendor.py, na mesma sessao do Colab.
# ==================================================================

import os, time
from datetime import datetime, timedelta
from colab_shim import drive, userdata

try:
    from sp_api.api import Reports
    from sp_api.base import Marketplaces, ReportType
except ImportError:
    os.system("pip install python-amazon-sp-api -q")
    from sp_api.api import Reports
    from sp_api.base import Marketplaces, ReportType

drive.mount('/content/drive', force_remount=True)

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
LWA_CLIENT_ID = userdata.get('SP_API_LWA_CLIENT_ID')
LWA_CLIENT_SECRET = userdata.get('SP_API_LWA_CLIENT_SECRET')
MARKETPLACE = Marketplaces.BR

# mesma convencao de chave/pasta usada no transformar_vendor.py
CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',         'pasta': 'alfa_jf/raw',   'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'nome': 'Blid Shop',       'pasta': 'blidshop/raw',  'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'conta3':    {'nome': 'Petclean BR',     'pasta': 'petclean/raw',  'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'nome': 'OZITP',           'pasta': 'ozitp/raw',     'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'nome': 'Jolitex',         'pasta': 'jolitex/raw',   'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'nome': 'Balboa',          'pasta': 'balboa/raw',    'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'nome': 'BR - Rio Master', 'pasta': 'riomaster/raw', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
}

DATA_INICIO = datetime(2026, 1, 1)  # ajustar so se alguma conta comecou depois
DATA_FIM = datetime.today()
ATRASO_DIAS = 2                     # mes so e pedido quando o ultimo dia passou ha >= 2 dias


# ------------------------------------------------------------------
# Funcoes auxiliares (mesmo padrao ja validado na recaptura da Petclean)
# ------------------------------------------------------------------

def blocos_mensais(inicio, fim, atraso_dias=ATRASO_DIAS):
    """Blocos (1o dia, ultimo dia) de MESES FECHADOS. A Amazon exige o mes inteiro no
    relatorio MONTH, entao o mes em andamento nao entra (ver cabecalho)."""
    blocos, atual = [], inicio.replace(day=1)
    limite = fim.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=atraso_dias)
    while atual <= fim:
        if atual.month == 12:
            prox = atual.replace(year=atual.year + 1, month=1)
        else:
            prox = atual.replace(month=atual.month + 1)
        ultimo_dia = prox - timedelta(days=1)
        if ultimo_dia <= limite:
            blocos.append((atual, ultimo_dia))
        atual = prox
    return blocos


def caminho(pasta_raw, prefixo, ini, fim):
    return f"{pasta_raw}/{prefixo}_{ini.strftime('%Y-%m-%d')}_a_{fim.strftime('%Y-%m-%d')}.json"


def baixar_relatorio(reports_api, pasta_raw, report_type, ini, fim, opts, prefixo, timeout_min=15):
    alvo = caminho(pasta_raw, prefixo, ini, fim)
    if os.path.exists(alvo):
        print(f"  [em cache] {prefixo} {ini.date()} a {fim.date()}")
        return "cache"
    try:
        resp = reports_api.create_report(
            reportType=report_type,
            marketplaceIds=[MARKETPLACE.marketplace_id],
            dataStartTime=f"{ini.strftime('%Y-%m-%d')}T00:00:00Z",
            dataEndTime=f"{fim.strftime('%Y-%m-%d')}T23:59:59Z",
            reportOptions=opts,
        )
        rid = resp.payload["reportId"]
    except Exception as e:
        print(f"  [ERRO solicitar] {prefixo} {ini.date()}: {e}")
        return None

    t0, doc_id, st = time.time(), None, None
    while True:
        try:
            sr = reports_api.get_report(rid)
            st = sr.payload.get("processingStatus")
        except Exception:
            time.sleep(20)
            continue
        if st == "DONE":
            doc_id = sr.payload["reportDocumentId"]
            break
        if st in ("CANCELLED", "FATAL"):
            print(f"  [FALHOU {st}] {prefixo} {ini.date()} a {fim.date()}")
            return None
        if time.time() - t0 > timeout_min * 60:
            print(f"  [TIMEOUT] {prefixo} {ini.date()}")
            return None
        time.sleep(20)

    try:
        dr = reports_api.get_report_document(doc_id, download=True)
        with open(alvo, "w", encoding="utf-8") as f:
            f.write(dr.payload["document"])
        print(f"  [OK] {prefixo} {ini.date()} a {fim.date()}")
        return "ok"
    except Exception as e:
        print(f"  [ERRO baixar] {prefixo} {ini.date()}: {e}")
        return None


def opts_completo(p):
    return {"reportPeriod": p, "distributorView": "MANUFACTURING", "sellingProgram": "RETAIL"}


def opts_simples(p):
    return {"reportPeriod": p}


bmes = blocos_mensais(DATA_INICIO, DATA_FIM)
print(f"Periodo: {DATA_INICIO.date()} a {DATA_FIM.date()} ({len(bmes)} meses fechados)")
print("(o mes em andamento fica de fora: e coberto por semanas no capturar_semanal.py)\n")

tarefas = [
    ("VENDAS mensal",  ReportType.GET_VENDOR_SALES_REPORT,                   "vendas_mes",  opts_completo("MONTH")),
    ("ESTOQUE mensal", ReportType.GET_VENDOR_INVENTORY_REPORT,               "estoque_mes", opts_completo("MONTH")),
    ("TRAFEGO mensal", ReportType.GET_VENDOR_TRAFFIC_REPORT,                 "trafego_mes", opts_simples("MONTH")),
    ("MARGEM mensal",  ReportType.GET_VENDOR_NET_PURE_PRODUCT_MARGIN_REPORT, "margem_mes",  opts_simples("MONTH")),
]

resumo_geral = {}

for chave, cfg in CONTAS_CONFIG.items():
    nome = cfg['nome']
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    os.makedirs(pasta_raw, exist_ok=True)

    print(f"\n{'#'*60}\n# CONTA: {nome}\n{'#'*60}")

    credentials = dict(
        refresh_token=userdata.get(cfg['secret']),
        lwa_app_id=LWA_CLIENT_ID,
        lwa_client_secret=LWA_CLIENT_SECRET,
    )
    reports_api = Reports(credentials=credentials, marketplace=MARKETPLACE)

    resumo_conta = {}
    for rotulo, tipo, prefixo, opts in tarefas:
        print(f"\n=== {rotulo} ({len(bmes)} blocos) ===")
        ok, falhas, pulados = 0, 0, 0
        for ini, fim in bmes:
            resultado = baixar_relatorio(reports_api, pasta_raw, tipo, ini, fim, opts, prefixo)
            if resultado == "ok":
                ok += 1
            elif resultado == "cache":
                pulados += 1
            else:
                falhas += 1
            if resultado != "cache":
                time.sleep(15)  # pausa entre cada bloco (mesmo ritmo usado na recaptura da Petclean)
        resumo_conta[rotulo] = f"{ok} baixados, {pulados} ja em cache, {falhas} falhas"
        if ok or falhas:
            time.sleep(30)  # pausa maior entre um tipo de relatorio e o proximo (so se chamou a API)

    resumo_geral[nome] = resumo_conta

print(f"\n\n{'='*60}\n=== RESUMO GERAL ===\n{'='*60}")
for nome, resumo in resumo_geral.items():
    print(f"\n{nome}:")
    for rotulo, status in resumo.items():
        print(f"  {rotulo}: {status}")

print("\nSe aparecer [FALHOU] ou [TIMEOUT] em algum bloco, rode a celula de novo --")
print("os blocos que ja deram [OK] ficam em cache e nao sao pedidos de novo.")
