# ==================================================================
# capturar_semanal.py
# CAPTURA SEMANAL -- Vendas, Estoque, Trafego, Margem (reportPeriod=WEEK)
# Celula unica, para as 7 contas do projeto START Vendor Analytics.
#
# POR QUE EXISTE
#   O capturar_mensal.py pede o relatorio MONTH. A Amazon exige o mes
#   INTEIRO (data final = ultimo dia do mes), entao o mes em andamento
#   (ex.: setembro, ate hoje) falha com FATAL e o dashboard para no mes
#   anterior. Este script cobre o mes em andamento por SEMANAS FECHADAS,
#   do mesmo jeito que o painel Analise de Varejo (ARA) mostra.
#
# REGRAS DA AMAZON (schema oficial dos relatorios)
#   - reportPeriod=WEEK: dataStartTime tem de ser DOMINGO e dataEndTime
#     SABADO (semana de domingo a sabado, como no ARA).
#   - so semanas FECHADAS trazem dado; por seguranca so pedimos semanas
#     cujo sabado ja passou ha pelo menos ATRASO_DIAS dias (D-2 do ARA).
#   - Semana 36/2026 = 30/08 a 05/09; 37 = 06/09 a 12/09; 38 = 13/09 a 19/09.
#     (numeracao: semana 1 = a que contem 1o de janeiro, domingo a sabado.)
#
# COMO FUNCIONA (mesmo padrao do capturar_mensal.py / capturar_pedidos.py)
#   - Monta o Drive, cache por arquivo (semana ja baixada e "velha" = pula),
#     roda de novo sem medo; so busca o que falta.
#   - Uma semana fechada ha menos de 7 dias e rebaixada a cada rodada, porque
#     o ARA ainda ajusta os numeros nos primeiros dias.
#   - Salva em START_Vendor_Analytics/<conta>/raw/:
#       vendas_sem_<ini>_a_<fim>.json     estoque_sem_...   trafego_sem_...   margem_sem_...
#     Depois rode o transformar_vendor.py (bloco `semanas` do dashboard).
#
# VELOCIDADE (v3, 25/09/2026)
#   A Amazon leva ~1 min para gerar cada relatorio. Pedidos em sequencia para
#   7 contas x 4 relatorios x 6 semanas = ~4 h. Agora as CONTAS rodam em
#   paralelo (uma thread por conta; a cota de relatorios e por conta/vendedor)
#   e sao 4 semanas (35 a 38 hoje: as 3 do mes + a anterior, para a variacao).
#   Dentro de cada conta continua um relatorio por vez. O log de cada conta
#   sai inteiro quando ela termina (nao intercalado).
#
# Rodar DEPOIS do capturar_pedidos.py e ANTES do transformar_vendor.py.
# ==================================================================

import os, time, threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
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

# mesma convencao de chave/pasta/secret usada em capturar_mensal.py e capturar_pedidos.py
CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',         'pasta': 'alfa_jf/raw',   'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'nome': 'Blid Shop',       'pasta': 'blidshop/raw',  'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'conta3':    {'nome': 'Petclean BR',     'pasta': 'petclean/raw',  'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'nome': 'OZITP',           'pasta': 'ozitp/raw',     'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'nome': 'Jolitex',         'pasta': 'jolitex/raw',   'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'nome': 'Balboa',          'pasta': 'balboa/raw',    'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'nome': 'BR - Rio Master', 'pasta': 'riomaster/raw', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
    'plastpet':  {'nome': 'Pet Factory Brazil Industria Ltda', 'pasta': 'plastpet/raw', 'secret': 'SP_API_REFRESH_TOKEN_PLASTPET'},
    'wiwu':      {'nome': 'WIWU', 'pasta': 'wiwu/raw', 'secret': 'SP_API_REFRESH_TOKEN_WIWU'},
    'petiko':    {'nome': 'PETIKO', 'pasta': 'petiko/raw', 'secret': 'SP_API_REFRESH_TOKEN_PETIKO'},
}

N_SEMANAS = 4        # semanas fechadas a capturar (as 3 do mes em andamento + a anterior, p/ variacao)
ATRASO_DIAS = 2      # so pede semana cujo sabado passou ha >= 2 dias
REBAIXAR_DIAS = 7    # semana fechada ha menos de 7 dias e rebaixada (ARA ajusta no inicio)
MAX_PARALELO = 7     # contas em paralelo (1 = sequencial, como antes)
MAX_TENTATIVAS_COTA = 4

DATA_HOJE = datetime.today()
_TRAVA_LOG = threading.Lock()


# ------------------------------------------------------------------
# Funcoes auxiliares
# ------------------------------------------------------------------

def domingo_da_semana(d):
    """Domingo da semana (domingo a sabado) que contem a data d."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def semanas_fechadas(hoje, n, atraso_dias):
    """Ultimas n semanas FECHADAS (domingo, sabado), da mais antiga para a mais nova.
    Fechada = sabado com pelo menos `atraso_dias` dias de folga ate hoje."""
    hoje = hoje.replace(hour=0, minute=0, second=0, microsecond=0)
    dom = domingo_da_semana(hoje)                      # domingo da semana atual (em andamento)
    while dom + timedelta(days=6) > hoje - timedelta(days=atraso_dias):
        dom -= timedelta(days=7)                       # recua ate a semana fechada mais recente
    return [(dom - timedelta(days=7 * i), dom - timedelta(days=7 * i) + timedelta(days=6))
            for i in range(n - 1, -1, -1)]


def numero_semana(domingo):
    """Numero da semana (semana 1 = a que contem 1o de janeiro, domingo a sabado)."""
    ano = (domingo + timedelta(days=6)).year          # ano do sabado: a semana de virada e a semana 1 do ano novo
    j1 = datetime(ano, 1, 1)
    ini = j1 - timedelta(days=(j1.weekday() + 1) % 7)
    return (domingo - ini).days // 7 + 1


def caminho(pasta_raw, prefixo, ini, fim):
    return f"{pasta_raw}/{prefixo}_{ini.strftime('%Y-%m-%d')}_a_{fim.strftime('%Y-%m-%d')}.json"


def cache_valido(alvo, fim_semana):
    """Arquivo existe e foi baixado depois de a semana estar 'assentada' (>= REBAIXAR_DIAS
    depois do sabado). Antes disso, rebaixa para pegar os ajustes do ARA."""
    if not os.path.exists(alvo):
        return False
    baixado_em = datetime.fromtimestamp(os.path.getmtime(alvo))
    return baixado_em >= fim_semana + timedelta(days=REBAIXAR_DIAS)


def baixar_relatorio(reports_api, pasta_raw, report_type, ini, fim, opts, prefixo, log, timeout_min=15):
    alvo = caminho(pasta_raw, prefixo, ini, fim)
    if cache_valido(alvo, fim):
        log(f"  [em cache] {prefixo} {ini.date()} a {fim.date()}")
        return "cache"
    rid = None
    for tentativa in range(1, MAX_TENTATIVAS_COTA + 1):
        try:
            resp = reports_api.create_report(
                reportType=report_type,
                marketplaceIds=[MARKETPLACE.marketplace_id],
                dataStartTime=f"{ini.strftime('%Y-%m-%d')}T00:00:00Z",
                dataEndTime=f"{fim.strftime('%Y-%m-%d')}T23:59:59Z",
                reportOptions=opts,
            )
            rid = resp.payload["reportId"]
            break
        except Exception as e:
            if ('QuotaExceeded' in str(e) or '429' in str(e)) and tentativa < MAX_TENTATIVAS_COTA:
                espera = 30 * tentativa
                log(f"    [cota excedida] {prefixo} aguardando {espera}s (tentativa {tentativa}/{MAX_TENTATIVAS_COTA})")
                time.sleep(espera)
                continue
            log(f"  [ERRO solicitar] {prefixo} {ini.date()}: {e}")
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
            log(f"  [FALHOU {st}] {prefixo} {ini.date()} a {fim.date()}")
            return None
        if time.time() - t0 > timeout_min * 60:
            log(f"  [TIMEOUT] {prefixo} {ini.date()}")
            return None
        time.sleep(20)

    try:
        dr = reports_api.get_report_document(doc_id, download=True)
        with open(alvo, "w", encoding="utf-8") as f:
            f.write(dr.payload["document"])
        log(f"  [OK] {prefixo} {ini.date()} a {fim.date()}")
        return "ok"
    except Exception as e:
        log(f"  [ERRO baixar] {prefixo} {ini.date()}: {e}")
        return None


def opts_completo(p):
    return {"reportPeriod": p, "distributorView": "MANUFACTURING", "sellingProgram": "RETAIL"}


def opts_simples(p):
    return {"reportPeriod": p}


def tarefas_semanais():
    return [
        ("VENDAS semanal",  ReportType.GET_VENDOR_SALES_REPORT,                   "vendas_sem",  opts_completo("WEEK")),
        ("ESTOQUE semanal", ReportType.GET_VENDOR_INVENTORY_REPORT,               "estoque_sem", opts_completo("WEEK")),
        ("TRAFEGO semanal", ReportType.GET_VENDOR_TRAFFIC_REPORT,                 "trafego_sem", opts_simples("WEEK")),
        ("MARGEM semanal",  ReportType.GET_VENDOR_NET_PURE_PRODUCT_MARGIN_REPORT, "margem_sem",  opts_simples("WEEK")),
    ]


def processar_conta(chave, cfg, semanas):
    """Captura as semanas de UMA conta (roda numa thread). Devolve (nome, resumo, linhas_de_log)."""
    linhas = []
    log = linhas.append
    nome = cfg['nome']
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    os.makedirs(pasta_raw, exist_ok=True)
    log(f"\n{'#'*60}\n# CONTA: {nome}\n{'#'*60}")

    credentials = dict(
        refresh_token=userdata.get(cfg['secret']),
        lwa_app_id=LWA_CLIENT_ID,
        lwa_client_secret=LWA_CLIENT_SECRET,
    )
    reports_api = Reports(credentials=credentials, marketplace=MARKETPLACE)

    resumo = {}
    for rotulo, tipo, prefixo, opts in tarefas_semanais():
        log(f'\n=== {rotulo} ({len(semanas)} semanas) ===')
        ok, falhas, pulados = 0, 0, 0
        for ini, fim in semanas:
            resultado = baixar_relatorio(reports_api, pasta_raw, tipo, ini, fim, opts, prefixo, log)
            if resultado == "ok":
                ok += 1
            elif resultado == "cache":
                pulados += 1
            else:
                falhas += 1
            if resultado != "cache":
                time.sleep(5)   # pausa curta entre relatorios da MESMA conta
        resumo[rotulo] = f"{ok} baixados, {pulados} ja em cache, {falhas} falhas"
    return nome, resumo, linhas


# ------------------------------------------------------------------
# Execucao
# ------------------------------------------------------------------

def main():
    semanas = semanas_fechadas(DATA_HOJE, N_SEMANAS, ATRASO_DIAS)
    for ini, fim in semanas:
        assert ini.weekday() == 6 and fim.weekday() == 5, f'semana invalida: {ini.date()} a {fim.date()}'
    print(f"Hoje: {DATA_HOJE.date()} | {len(semanas)} semanas fechadas (domingo a sabado):")
    for ini, fim in semanas:
        print(f"  semana {numero_semana(ini)}: {ini.strftime('%d/%m')} a {fim.strftime('%d/%m/%Y')}")
    print(f"Contas em paralelo: {min(MAX_PARALELO, len(CONTAS_CONFIG))} | inicio: {datetime.now().strftime('%H:%M:%S')}\n")

    resumo_geral = {}

    def trabalho(item):
        chave, cfg = item
        try:
            nome, resumo, linhas = processar_conta(chave, cfg, semanas)
        except Exception as e:                       # uma conta com problema nao derruba as outras
            nome, resumo, linhas = cfg['nome'], {'ERRO': str(e)}, [f"\n[ERRO] {cfg['nome']}: {e}"]
        with _TRAVA_LOG:                             # imprime o log da conta inteiro, sem intercalar
            print('\n'.join(linhas))
            print(f"  >>> {nome} concluida as {datetime.now().strftime('%H:%M:%S')}")
        return nome, resumo

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_PARALELO, len(CONTAS_CONFIG)))) as pool:
        for nome, resumo in pool.map(trabalho, list(CONTAS_CONFIG.items())):
            resumo_geral[nome] = resumo

    print(f"\n\n{'='*60}\n=== RESUMO GERAL ===\n{'='*60}")
    for nome, resumo in resumo_geral.items():
        print(f"\n{nome}:")
        for rotulo, status in resumo.items():
            print(f"  {rotulo}: {status}")
    print(f"\nFim: {datetime.now().strftime('%H:%M:%S')}")
    print("Se aparecer [FALHOU] ou [TIMEOUT] em algum bloco, rode a celula de novo --")
    print("os blocos que ja deram [OK] ficam em cache e nao sao pedidos de novo.")
    print("Depois rode o transformar_vendor.py para o dashboard mostrar as semanas.")


main()
