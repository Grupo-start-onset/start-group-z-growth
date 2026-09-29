# ==================================================================
# capturar_data_kiosk.py
# OFERTA EM DESTAQUE (Buy Box) via Data Kiosk, dataset Vendor Analytics
# (Analytics_vendorAnalytics_2024_09_30), visao manufacturingView, por SEMANA.
#
# Por produto (ASIN) e semana fechada (domingo a sabado):
#   glanceViews        visualizacoes em que a Amazon (Retail) GANHA a oferta em destaque
#                      (sao as mesmas do relatorio de trafego do ARA; conferido em 25/09/2026)
#   lostFeaturedOffer  fracao (0 a 1) das visualizacoes em que a oferta em destaque NAO e da
#                      Amazon. Total de visualizacoes = glanceViews / (1 - lostFeaturedOffer).
#
# Testado em 25/09/2026 (ALFA JF, semana 13-19/09): a API aceitou (202) e a consulta levou
# cerca de 17 MINUTOS para concluir. Por isso as 7 contas rodam em PARALELO: todas as consultas
# sao criadas de uma vez e o tempo total e o da mais lenta, e nao a soma.
#
# ONDE GRAVA (por conta), em START_Vendor_Analytics/<conta>/raw/:
#   dk_traffic_<ini>_a_<fim>.json   {"ini","fim","marketplaceId","totals","metrics":[...]}  (1 por semana)
#   dk_falhas.json                  falhas recentes (nao repete a espera antes de FALHA_ESPERA_HORAS)
#
# CACHE: semana ja capturada = pula, exceto semanas fechadas ha menos de REFRESH_DIAS dias, que
# sao pedidas de novo (a Amazon pode ajustar os numeros no comeco). Uma unica consulta cobre as
# semanas pendentes de uma conta.
#
# Rodar depois do capturar_semanal e antes do transformar_vendor / transformar_destaque.
# Contas sem permissao ou sem dado voltam erro/FATAL: ficam em dk_falhas.json, sem travar as outras.
# ==================================================================

import os, json, time, gzip
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from colab_shim import drive, userdata
import requests

drive.mount('/content/drive', force_remount=True)

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
LWA_CLIENT_ID = userdata.get('SP_API_LWA_CLIENT_ID')
LWA_CLIENT_SECRET = userdata.get('SP_API_LWA_CLIENT_SECRET')
ENDPOINT = 'https://sellingpartnerapi-na.amazon.com'
LWA_URL = 'https://api.amazon.com/auth/o2/token'

CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',         'pasta': 'alfa_jf/raw',   'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'nome': 'Blid Shop',       'pasta': 'blidshop/raw',  'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'conta3':    {'nome': 'Petclean BR',     'pasta': 'petclean/raw',  'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'nome': 'OZITP',           'pasta': 'ozitp/raw',     'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'nome': 'Jolitex',         'pasta': 'jolitex/raw',   'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'nome': 'Balboa',          'pasta': 'balboa/raw',    'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'nome': 'BR - Rio Master', 'pasta': 'riomaster/raw', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
    'plastpet':  {'nome': 'Pet Factory Brazil Industria Ltda', 'pasta': 'plastpet/raw', 'secret': 'SP_API_REFRESH_TOKEN_PLASTPET'},
}

N_SEMANAS = 4              # quantas semanas fechadas manter (tendencia semana a semana)
ATRASO_DIAS = 2            # o sabado da semana precisa ter passado ha >= 2 dias
REFRESH_DIAS = 10          # semanas fechadas ha menos que isso sao pedidas de novo
MAX_PARALELO = 7           # contas em paralelo
POLL_SEGUNDOS = 30
TIMEOUT_MIN = 60           # espera maxima por consulta
FALHA_ESPERA_HORAS = 24
MAX_TENTATIVAS_HTTP = 5    # retry em 429/5xx


# ------------------------------------------------------------------
# Funcoes puras
# ------------------------------------------------------------------

def semanas_fechadas(hoje, n=N_SEMANAS, atraso=ATRASO_DIAS):
    """[(domingo, sabado)] das ultimas n semanas fechadas, da mais antiga para a mais nova."""
    d = hoje.date() - timedelta(days=atraso)
    sab = d - timedelta(days=(d.weekday() - 5) % 7)
    return [(sab - timedelta(days=6 + 7 * i), sab - timedelta(days=7 * i)) for i in reversed(range(n))]


def caminho_dk(pasta_raw, ini, fim):
    return f"{pasta_raw}/dk_traffic_{ini:%Y-%m-%d}_a_{fim:%Y-%m-%d}.json"


def semanas_pendentes(pasta_raw, semanas, hoje=None):
    """Semanas sem arquivo, ou fechadas ha menos de REFRESH_DIAS dias (dado ainda pode mudar)."""
    hoje = hoje or datetime.today()
    pend = []
    for ini, fim in semanas:
        if not os.path.exists(caminho_dk(pasta_raw, ini, fim)) or (hoje.date() - fim).days < REFRESH_DIAS:
            pend.append((ini, fim))
    return pend


def montar_query(ini, fim):
    return ('query { analytics_vendorAnalytics_2024_09_30 { manufacturingView('
            f'aggregateBy: WEEK, startDate: "{ini:%Y-%m-%d}", endDate: "{fim:%Y-%m-%d}") {{ '
            'startDate endDate marketplaceId '
            'totals { traffic { glanceViews lostFeaturedOffer } } '
            'metrics { groupByKey { asin } metrics { traffic { glanceViews lostFeaturedOffer } } } '
            '} } }')


def interpretar_documento(bruto):
    """Bytes do documento (JSON Lines, possivelmente gzip) -> lista de registros (um por semana)."""
    if bruto[:2] == b'\x1f\x8b':
        bruto = gzip.decompress(bruto)
    registros = []
    for linha in bruto.decode('utf-8').splitlines():
        linha = linha.strip()
        if not linha:
            continue
        obj = json.loads(linha)
        if isinstance(obj, dict) and 'data' in obj and isinstance(obj['data'], dict) and 'startDate' not in obj:
            obj = obj['data']
        if isinstance(obj, dict) and obj.get('startDate') and obj.get('endDate'):
            registros.append(obj)
    return registros


def carregar_falhas(pasta_raw):
    try:
        return json.load(open(f'{pasta_raw}/dk_falhas.json', encoding='utf-8'))
    except Exception:
        return {}


def gravar_falhas(pasta_raw, falhas):
    with open(f'{pasta_raw}/dk_falhas.json', 'w', encoding='utf-8') as f:
        json.dump(falhas, f, ensure_ascii=False, indent=1)


def falha_recente(falhas, chave, agora=None):
    f = falhas.get(chave)
    if not f:
        return False
    try:
        return ((agora or datetime.now()) - datetime.fromisoformat(f['quando'])) < timedelta(hours=FALHA_ESPERA_HORAS)
    except Exception:
        return False


def gravar_atomico(alvo, obj):
    tmp = alvo + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, alvo)


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------

class Sessao:
    """Access token do LWA por conta, renovado antes de expirar (validade de 1 hora)."""
    def __init__(self, refresh_token):
        self.refresh = refresh_token
        self.token, self.t0 = None, 0

    def headers(self):
        if not self.token or time.time() - self.t0 > 45 * 60:
            r = requests.post(LWA_URL, data={'grant_type': 'refresh_token', 'refresh_token': self.refresh,
                                             'client_id': LWA_CLIENT_ID, 'client_secret': LWA_CLIENT_SECRET}, timeout=60)
            r.raise_for_status()
            self.token, self.t0 = r.json()['access_token'], time.time()
        return {'x-amz-access-token': self.token, 'content-type': 'application/json'}


def chamar(sessao, metodo, url, **kw):
    """HTTP com retry/backoff em 429 e 5xx. Levanta RuntimeError com o corpo da resposta se falhar."""
    for tentativa in range(1, MAX_TENTATIVAS_HTTP + 1):
        r = requests.request(metodo, url, headers=sessao.headers(), timeout=120, **kw)
        if r.status_code in (429, 500, 502, 503, 504) and tentativa < MAX_TENTATIVAS_HTTP:
            time.sleep(15 * tentativa)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f'HTTP {r.status_code}: {r.text[:300]}')
        return r.json()


def consultar(sessao, query, tag):
    """Cria a consulta, espera concluir e devolve os registros do documento."""
    qid = chamar(sessao, 'POST', f'{ENDPOINT}/dataKiosk/2023-11-15/queries', json={'query': query})['queryId']
    t0 = time.time()
    print(f'{tag} consulta {qid} criada')
    while True:
        time.sleep(POLL_SEGUNDOS)
        st = chamar(sessao, 'GET', f'{ENDPOINT}/dataKiosk/2023-11-15/queries/{qid}')
        estado = st.get('processingStatus')
        if estado == 'DONE':
            break
        if estado in ('FATAL', 'CANCELLED'):
            raise RuntimeError(f'{estado} (queryId {qid})')
        if time.time() - t0 > TIMEOUT_MIN * 60:
            raise RuntimeError(f'TIMEOUT apos {TIMEOUT_MIN} min (queryId {qid})')
    doc_id = st.get('dataDocumentId')
    if not doc_id:      # DONE sem documento = consulta sem resultado
        return [], time.time() - t0
    d = chamar(sessao, 'GET', f'{ENDPOINT}/dataKiosk/2023-11-15/documents/{doc_id}')
    bruto = requests.get(d['documentUrl'], timeout=300).content
    return interpretar_documento(bruto), time.time() - t0


# ------------------------------------------------------------------
# Uma conta
# ------------------------------------------------------------------

def capturar_conta(chave, cfg, semanas):
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    os.makedirs(pasta_raw, exist_ok=True)
    tag = f'[{chave}]'
    pend = semanas_pendentes(pasta_raw, semanas)
    if not pend:
        print(f'{tag} [em cache] {len(semanas)} semanas')
        return cfg['nome'], {'ok': 0, 'cache': len(semanas), 'falha': 0, 'pulado': 0}

    falhas = carregar_falhas(pasta_raw)
    fchave = f'traffic_{pend[0][0]:%Y-%m-%d}'
    if falha_recente(falhas, fchave):
        print(f'{tag} [pulado] falhou ha menos de {FALHA_ESPERA_HORAS}h ({falhas[fchave]["erro"][:70]})')
        return cfg['nome'], {'ok': 0, 'cache': len(semanas) - len(pend), 'falha': 0, 'pulado': 1}

    try:
        sessao = Sessao(userdata.get(cfg['secret']))
        registros, seg = consultar(sessao, montar_query(pend[0][0], pend[-1][1]), tag)
        pedidas = {(i.strftime('%Y-%m-%d'), f.strftime('%Y-%m-%d')) for i, f in pend}
        gravadas = 0
        for r in registros:
            if (r['startDate'], r['endDate']) not in pedidas:
                continue
            alvo = f"{pasta_raw}/dk_traffic_{r['startDate']}_a_{r['endDate']}.json"
            gravar_atomico(alvo, {'ini': r['startDate'], 'fim': r['endDate'], 'marketplaceId': r.get('marketplaceId'),
                                  'totals': r.get('totals'), 'metrics': r.get('metrics') or []})
            gravadas += 1
        print(f'{tag} [OK] {gravadas} semanas gravadas ({seg / 60:.0f} min)')
        falhas.pop(fchave, None)
        gravar_falhas(pasta_raw, falhas)
        return cfg['nome'], {'ok': gravadas, 'cache': len(semanas) - len(pend), 'falha': 0, 'pulado': 0}
    except Exception as e:
        print(f'{tag} [FALHOU] {str(e)[:250]}')
        falhas[fchave] = {'quando': datetime.now().isoformat(timespec='seconds'), 'erro': str(e)[:300]}
        gravar_falhas(pasta_raw, falhas)
        return cfg['nome'], {'ok': 0, 'cache': len(semanas) - len(pend), 'falha': 1, 'pulado': 0}


# ------------------------------------------------------------------
# Execucao
# ------------------------------------------------------------------

semanas = semanas_fechadas(datetime.today())
print(f'Semanas: {", ".join(f"{i:%d/%m} a {f:%d/%m}" for i, f in semanas)} | contas em paralelo: {MAX_PARALELO}')
print('(cada consulta da Data Kiosk leva cerca de 15 a 20 minutos; as contas esperam ao mesmo tempo)\n')

resumo = {}
with ThreadPoolExecutor(max_workers=MAX_PARALELO) as pool:
    futuros = {pool.submit(capturar_conta, k, c, semanas): c['nome'] for k, c in CONTAS_CONFIG.items()}
    for fut in as_completed(futuros):
        try:
            nome, res = fut.result()
            resumo[nome] = res
        except Exception as e:
            resumo[futuros[fut]] = {'erro': f'{type(e).__name__}: {e}'[:150]}

print(f'\n{"="*60}\n=== RESUMO DATA KIOSK (oferta em destaque) ===\n{"="*60}')
for c in CONTAS_CONFIG.values():
    r = resumo.get(c['nome'], {})
    print(f"{c['nome']}: " + (r['erro'] if 'erro' in r else
          f"{r['ok']} semanas baixadas, {r['cache']} em cache, {r['pulado']} pulada, {r['falha']} falha"))
print('\nFalhas ficam em <conta>/raw/dk_falhas.json e so sao repetidas apos 24h.')
