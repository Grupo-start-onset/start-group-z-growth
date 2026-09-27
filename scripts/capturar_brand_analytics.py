# ==================================================================
# capturar_brand_analytics.py
# CAPTURA DE BRAND ANALYTICS (cesta de compras, termos de busca, recompra)
# para as 7 contas do projeto START Vendor Analytics.
#
# Relatorios (SP-API, reportPeriod = WEEK, semana FECHADA domingo a sabado):
#   GET_BRAND_ANALYTICS_MARKET_BASKET_REPORT   -> comprado junto com (por ASIN)
#   GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT    -> termos de busca (marketplace inteiro!)
#   GET_BRAND_ANALYTICS_REPEAT_PURCHASE_REPORT -> recompra (por ASIN)
#
# Testado em 25/09/2026 (ALFA JF, semana 13-19/09): os 3 relatorios voltaram DONE.
# (Em 10/09 tinham voltado FATAL; a autorizacao da role Brand Analytics mudou.)
#
# ATENCAO -- TERMOS DE BUSCA: o relatorio traz os termos do marketplace INTEIRO
# (cada linha = termo + um dos 3 ASINs mais clicados), pode ter centenas de MB.
# Por isso ele e lido em STREAMING (ijson) direto do link de download, sem
# carregar tudo na memoria, e so ficam as linhas cujo ASIN clicado pertence a
# conta (ASINs de vendas_mes_*.json + asins_catalogo_completo.json).
#
# ONDE GRAVA (por conta), em START_Vendor_Analytics/<conta>/raw/:
#   brand_cesta_compras_<ini>_a_<fim>.json     relatorio bruto (sem o cabecalho)
#   brand_recompra_<ini>_a_<fim>.json          relatorio bruto (sem o cabecalho)
#   brand_termos_busca_<ini>_a_<fim>.json      {"ini","fim","totalLinhas","linhas":[...so da conta]}
#   brand_falhas.json                          falhas recentes (evita repetir a espera)
# O transformar_brand.py le esses arquivos e preenche CONTAS[conta].extras.
#
# CACHE: semana ja capturada = pula. Se um relatorio falhar, nao e gravado como
# "resultado"; a falha fica em brand_falhas.json e o mesmo relatorio/semana so e
# tentado de novo depois de FALHA_ESPERA_HORAS (evita esperar tudo de novo a cada rodada).
#
# Contas em paralelo (MAX_PARALELO); dentro da conta, os 3 relatorios em sequencia.
# Rodar depois do capturar_semanal e antes do transformar_vendor / transformar_brand.
# ==================================================================

import os, json, time, glob, gzip
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from colab_shim import drive, userdata

try:
    from sp_api.api import Reports
    from sp_api.base import Marketplaces
except ImportError:
    os.system("pip install python-amazon-sp-api -q")
    from sp_api.api import Reports
    from sp_api.base import Marketplaces

try:
    import ijson
except ImportError:
    os.system("pip install ijson -q")
    import ijson

import requests

drive.mount('/content/drive', force_remount=True)

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
LWA_CLIENT_ID = userdata.get('SP_API_LWA_CLIENT_ID')
LWA_CLIENT_SECRET = userdata.get('SP_API_LWA_CLIENT_SECRET')
MARKETPLACE = Marketplaces.BR
MARKETPLACE_ID = 'A2Q3Y263D00KWC'

CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',         'pasta': 'alfa_jf/raw',   'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'nome': 'Blid Shop',       'pasta': 'blidshop/raw',  'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'conta3':    {'nome': 'Petclean BR',     'pasta': 'petclean/raw',  'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'nome': 'OZITP',           'pasta': 'ozitp/raw',     'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'nome': 'Jolitex',         'pasta': 'jolitex/raw',   'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'nome': 'Balboa',          'pasta': 'balboa/raw',    'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'nome': 'BR - Rio Master', 'pasta': 'riomaster/raw', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
}

# nome do arquivo -> (reportType, chave da lista no relatorio)
RELATORIOS = {
    'cesta_compras': ('GET_BRAND_ANALYTICS_MARKET_BASKET_REPORT',   'dataByAsin'),
    'termos_busca':  ('GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT',    'dataByDepartmentAndSearchTerm'),
    'recompra':      ('GET_BRAND_ANALYTICS_REPEAT_PURCHASE_REPORT', 'dataByAsin'),
}

N_SEMANAS = 1              # quantas semanas fechadas capturar (o dashboard usa a mais recente)
ATRASO_DIAS = 2            # o sabado da semana precisa ter passado ha >= 2 dias
MAX_PARALELO = 7           # contas em paralelo
POLL_SEGUNDOS = 20
TIMEOUT_MIN = 45           # espera maxima por relatorio (o de termos de busca e o mais lento)
FALHA_ESPERA_HORAS = 24    # depois de uma falha, so tenta o mesmo relatorio/semana apos isso
MAX_LINHAS_TERMOS = 20000  # teto de seguranca de linhas guardadas por conta/semana


# ------------------------------------------------------------------
# Funcoes puras
# ------------------------------------------------------------------

def semanas_fechadas(hoje, n=N_SEMANAS, atraso=ATRASO_DIAS):
    """[(domingo, sabado)] das ultimas n semanas fechadas, da mais antiga para a mais nova.
    Sabado <= hoje - atraso."""
    d = hoje.date() - timedelta(days=atraso)
    sab = d - timedelta(days=(d.weekday() - 5) % 7)          # sabado mais recente <= d
    return [(sab - timedelta(days=6 + 7 * i), sab - timedelta(days=7 * i)) for i in reversed(range(n))]


def asins_da_conta(pasta_raw):
    """ASINs da conta: vendas_mes_*.json (salesByAsin) + asins_catalogo_completo.json + catalogo.json."""
    asins = set()
    for arq in glob.glob(f'{pasta_raw}/vendas_mes_*.json'):
        try:
            d = json.load(open(arq, encoding='utf-8'))
        except Exception:
            continue
        for r in d.get('salesByAsin', []):
            if r.get('asin'):
                asins.add(r['asin'])
    for nome in ('asins_catalogo_completo.json', 'catalogo.json'):
        caminho = f'{pasta_raw}/{nome}'
        if os.path.exists(caminho):
            try:
                d = json.load(open(caminho, encoding='utf-8'))
                asins |= set(d if isinstance(d, list) else d.keys())
            except Exception:
                pass
    return asins


def caminho_brand(pasta_raw, nome, ini, fim):
    return f"{pasta_raw}/brand_{nome}_{ini:%Y-%m-%d}_a_{fim:%Y-%m-%d}.json"


def carregar_falhas(pasta_raw):
    try:
        return json.load(open(f'{pasta_raw}/brand_falhas.json', encoding='utf-8'))
    except Exception:
        return {}


def gravar_falhas(pasta_raw, falhas):
    with open(f'{pasta_raw}/brand_falhas.json', 'w', encoding='utf-8') as f:
        json.dump(falhas, f, ensure_ascii=False, indent=1)


def falha_recente(falhas, chave, agora=None):
    """True se este relatorio/semana falhou ha menos de FALHA_ESPERA_HORAS horas."""
    f = falhas.get(chave)
    if not f:
        return False
    try:
        t = datetime.fromisoformat(f['quando'])
    except Exception:
        return False
    return ((agora or datetime.now()) - t) < timedelta(hours=FALHA_ESPERA_HORAS)


def gravar_atomico(alvo, obj):
    tmp = alvo + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, alvo)


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------

def esperar_relatorio(api, tipo, ini, fim, tag):
    """Cria o relatorio e espera. Devolve o reportDocumentId ou levanta RuntimeError."""
    r = api.create_report(
        reportType=tipo, marketplaceIds=[MARKETPLACE_ID],
        dataStartTime=f'{ini:%Y-%m-%d}T00:00:00Z', dataEndTime=f'{fim:%Y-%m-%d}T23:59:59Z',
        reportOptions={'reportPeriod': 'WEEK'})
    rid = r.payload['reportId']
    t0, st = time.time(), {}
    while True:
        time.sleep(POLL_SEGUNDOS)
        try:
            st = api.get_report(rid).payload
        except Exception:
            st = {}
        status = st.get('processingStatus')
        if status == 'DONE':
            return st['reportDocumentId']
        if status in ('FATAL', 'CANCELLED'):
            raise RuntimeError(f'{status} (reportId {rid})')
        if time.time() - t0 > TIMEOUT_MIN * 60:
            raise RuntimeError(f'TIMEOUT apos {TIMEOUT_MIN} min (reportId {rid})')


def abrir_documento(api, doc_id):
    """Abre o documento do relatorio como fluxo de bytes (descomprime GZIP se preciso)."""
    doc = api.get_report_document(doc_id, download=False).payload
    resp = requests.get(doc['url'], stream=True, timeout=600)
    resp.raise_for_status()
    fluxo = resp.raw
    if (doc.get('compressionAlgorithm') or '').upper() == 'GZIP':
        fluxo = gzip.GzipFile(fileobj=resp.raw)
    return fluxo, resp


def ler_e_salvar(api, doc_id, nome, chave_lista, alvo, asins, ini, fim):
    """Le o documento e grava. Devolve o numero de linhas guardadas."""
    fluxo, resp = abrir_documento(api, doc_id)
    try:
        if nome == 'termos_busca':
            linhas, total = [], 0
            for item in ijson.items(fluxo, f'{chave_lista}.item', use_float=True):
                total += 1
                if item.get('clickedAsin') in asins and len(linhas) < MAX_LINHAS_TERMOS:
                    linhas.append(item)
            gravar_atomico(alvo, {'ini': f'{ini:%Y-%m-%d}', 'fim': f'{fim:%Y-%m-%d}',
                                  'totalLinhas': total, 'linhas': linhas})
            return len(linhas)
        dados = json.load(fluxo)
        dados.pop('reportSpecification', None)
        gravar_atomico(alvo, dados)
        return len(dados.get(chave_lista, []))
    finally:
        resp.close()


# ------------------------------------------------------------------
# Uma conta
# ------------------------------------------------------------------

def capturar_conta(chave, cfg, semanas):
    nome_conta = cfg['nome']
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    os.makedirs(pasta_raw, exist_ok=True)
    tag = f'[{chave}]'
    api = Reports(credentials=dict(refresh_token=userdata.get(cfg['secret']),
                                   lwa_app_id=LWA_CLIENT_ID, lwa_client_secret=LWA_CLIENT_SECRET),
                  marketplace=MARKETPLACE)
    asins = None            # so le quando precisar (termos de busca)
    falhas = carregar_falhas(pasta_raw)
    res = {'ok': 0, 'cache': 0, 'falhas': 0, 'pulados': 0}

    for ini, fim in semanas:
        for nome, (tipo, chave_lista) in RELATORIOS.items():
            alvo = caminho_brand(pasta_raw, nome, ini, fim)
            if os.path.exists(alvo):
                print(f'{tag} [em cache] {nome} {ini} a {fim}')
                res['cache'] += 1
                continue
            fchave = f'{nome}_{ini:%Y-%m-%d}'
            if falha_recente(falhas, fchave):
                print(f'{tag} [pulado] {nome} {ini}: falhou ha menos de {FALHA_ESPERA_HORAS}h ({falhas[fchave]["erro"][:60]})')
                res['pulados'] += 1
                continue
            try:
                if nome == 'termos_busca':
                    if asins is None:
                        asins = asins_da_conta(pasta_raw)
                    if not asins:
                        print(f'{tag} [aviso] sem ASINs da conta (vendas_mes_*.json): termos de busca pulado')
                        res['pulados'] += 1
                        continue
                t0 = time.time()
                doc_id = esperar_relatorio(api, tipo, ini, fim, tag)
                n = ler_e_salvar(api, doc_id, nome, chave_lista, alvo, asins, ini, fim)
                print(f'{tag} [OK] {nome} {ini} a {fim}: {n} linhas ({time.time() - t0:.0f}s)')
                res['ok'] += 1
                falhas.pop(fchave, None)
            except Exception as e:
                print(f'{tag} [FALHOU] {nome} {ini} a {fim}: {str(e)[:200]}')
                falhas[fchave] = {'quando': datetime.now().isoformat(timespec='seconds'), 'erro': str(e)[:300]}
                res['falhas'] += 1
            gravar_falhas(pasta_raw, falhas)
    return nome_conta, res


# ------------------------------------------------------------------
# Execucao
# ------------------------------------------------------------------

semanas = semanas_fechadas(datetime.today())
print(f'Semanas: {", ".join(f"{i:%d/%m} a {f:%d/%m}" for i, f in semanas)} | contas em paralelo: {MAX_PARALELO}\n')

resumo = {}
with ThreadPoolExecutor(max_workers=MAX_PARALELO) as pool:
    futuros = {pool.submit(capturar_conta, chave, cfg, semanas): cfg['nome'] for chave, cfg in CONTAS_CONFIG.items()}
    for fut in as_completed(futuros):
        nome_conta = futuros[fut]
        try:
            _, res = fut.result()
            resumo[nome_conta] = res
        except Exception as e:
            print(f'[{nome_conta}] ERRO inesperado: {type(e).__name__}: {e}')
            resumo[nome_conta] = {'erro': str(e)[:150]}

print(f'\n{"="*60}\n=== RESUMO BRAND ANALYTICS ===\n{"="*60}')
for nome_conta in [c['nome'] for c in CONTAS_CONFIG.values()]:
    r = resumo.get(nome_conta, {})
    print(f'{nome_conta}: ' + (r['erro'] if 'erro' in r else
          f"{r['ok']} baixados, {r['cache']} em cache, {r['pulados']} pulados, {r['falhas']} falhas"))
print('\nFalhas ficam registradas em <conta>/raw/brand_falhas.json e so sao repetidas apos 24h.')
