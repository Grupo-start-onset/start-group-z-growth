# ==================================================================
# capturar_previsao.py
# PREVISAO DE DEMANDA (GET_VENDOR_FORECASTING_REPORT), para as 7 contas.
#
# POR QUE EXISTE
#   A pagina "Previsao" do dashboard le o bloco `previsao` / `previsaoMes`, que o
#   transformar_vendor.py monta a partir de <conta>/raw/previsao_60dias.json. Esse
#   arquivo so tinha sido baixado UMA vez (8 a 10/09/2026) para ALFA JF, Blid Shop e
#   OZITP, e nenhum passo da rotina o atualizava: Petclean, Jolitex, Balboa e Rio
#   Master ficavam com a pagina vazia.
#
# COMO FUNCIONA
#   - O relatorio NAO aceita datas (dataStartTime/dataEndTime dao erro); so
#     reportOptions={"sellingProgram": "RETAIL"}. A Amazon devolve a previsao semanal
#     dos proximos ~60 dias por ASIN (media, p70, p80, p90).
#   - 7 contas em paralelo (uma thread por conta; a cota de relatorios e por conta).
#   - Cache: arquivo baixado ha menos de REFRESH_DIAS (6) dias e pulado. A previsao
#     da Amazon muda pouco de um dia para o outro.
#   - Escreve em <conta>/raw/previsao_60dias.json (mesmo nome de antes). Se a Amazon
#     falhar (FATAL, timeout), o arquivo anterior e MANTIDO e a falha vai para
#     <conta>/raw/previsao_falhas.json (so e repetida apos 24h).
#   - Se a Amazon devolver FATAL com documento de erro, o motivo aparece no log
#     ("| motivo: ..."). Uma conta pode nao ter previsao gerada pela Amazon (ex.: sem
#     historico suficiente); nesse caso a pagina continua vazia para ela.
#
# Ordem no rodar_tudo: ... capturar_semanal -> capturar_previsao -> ... -> transformar_vendor
# ==================================================================

import os, json, time, threading
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

ARQUIVO = 'previsao_60dias.json'
ARQUIVO_FALHAS = 'previsao_falhas.json'
REFRESH_DIAS = 6          # baixa de novo se o arquivo tem mais de 6 dias
REPETIR_FALHA_HORAS = 24  # falha recente nao e repetida
TIMEOUT_MIN = 20
MAX_TENTATIVAS_COTA = 4
_TRAVA_LOG = threading.Lock()


def _ler_falhas(pasta_raw):
    try:
        return json.load(open(f'{pasta_raw}/{ARQUIVO_FALHAS}', encoding='utf-8'))
    except Exception:
        return {}


def _gravar_falha(pasta_raw, motivo):
    with open(f'{pasta_raw}/{ARQUIVO_FALHAS}', 'w', encoding='utf-8') as f:
        json.dump({'quando': datetime.now().isoformat(timespec='seconds'), 'motivo': motivo}, f, ensure_ascii=False)


def _limpar_falha(pasta_raw):
    try:
        os.remove(f'{pasta_raw}/{ARQUIVO_FALHAS}')
    except OSError:
        pass


def _resumo_documento_erro(reports_api, payload):
    """Se a Amazon devolveu FATAL com um documento de erro, devolve um trecho dele."""
    doc_id = payload.get('reportDocumentId')
    if not doc_id:
        return ''
    try:
        dr = reports_api.get_report_document(doc_id, download=True)
        return ' | motivo: ' + str(dr.payload.get('document', ''))[:300].replace('\n', ' ')
    except Exception:
        return ''


def processar_conta(chave, cfg):
    """Baixa a previsao de UMA conta (roda numa thread). Devolve (nome, status, linhas_de_log)."""
    linhas = []
    log = linhas.append
    nome = cfg['nome']
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    os.makedirs(pasta_raw, exist_ok=True)
    alvo = f'{pasta_raw}/{ARQUIVO}'

    if os.path.exists(alvo):
        idade = datetime.now() - datetime.fromtimestamp(os.path.getmtime(alvo))
        if idade < timedelta(days=REFRESH_DIAS):
            log(f'[{nome}] [em cache] previsao baixada ha {idade.days} dia(s)')
            return nome, 'cache', linhas

    falha = _ler_falhas(pasta_raw)
    if falha.get('quando'):
        try:
            if datetime.now() - datetime.fromisoformat(falha['quando']) < timedelta(hours=REPETIR_FALHA_HORAS):
                log(f"[{nome}] [pulado] falhou ha menos de {REPETIR_FALHA_HORAS}h ({falha.get('motivo')})")
                return nome, 'pulado', linhas
        except ValueError:
            pass

    reports_api = Reports(credentials=dict(
        refresh_token=userdata.get(cfg['secret']),
        lwa_app_id=LWA_CLIENT_ID,
        lwa_client_secret=LWA_CLIENT_SECRET,
    ), marketplace=MARKETPLACE)

    rid = None
    for tentativa in range(1, MAX_TENTATIVAS_COTA + 1):
        try:
            resp = reports_api.create_report(
                reportType=ReportType.GET_VENDOR_FORECASTING_REPORT,
                marketplaceIds=[MARKETPLACE.marketplace_id],
                reportOptions={'sellingProgram': 'RETAIL'},      # sem datas: a Amazon rejeita dataStartTime
            )
            rid = resp.payload['reportId']
            break
        except Exception as e:
            if ('QuotaExceeded' in str(e) or '429' in str(e)) and tentativa < MAX_TENTATIVAS_COTA:
                espera = 30 * tentativa
                log(f'[{nome}] [cota excedida] aguardando {espera}s (tentativa {tentativa}/{MAX_TENTATIVAS_COTA})')
                time.sleep(espera)
                continue
            motivo = f'erro ao solicitar: {type(e).__name__}: {str(e)[:200]}'
            log(f'[{nome}] [ERRO] {motivo}')
            _gravar_falha(pasta_raw, motivo)
            return nome, 'falha', linhas

    t0, doc_id = time.time(), None
    while True:
        try:
            sr = reports_api.get_report(rid)
            st = sr.payload.get('processingStatus')
        except Exception:
            time.sleep(20)
            continue
        if st == 'DONE':
            doc_id = sr.payload['reportDocumentId']
            break
        if st in ('CANCELLED', 'FATAL'):
            motivo = f'{st} (reportId {rid})' + _resumo_documento_erro(reports_api, sr.payload)
            log(f'[{nome}] [FALHOU] {motivo}')
            _gravar_falha(pasta_raw, motivo)
            return nome, 'falha', linhas
        if time.time() - t0 > TIMEOUT_MIN * 60:
            motivo = f'timeout de {TIMEOUT_MIN} min (reportId {rid})'
            log(f'[{nome}] [TIMEOUT] {motivo}')
            _gravar_falha(pasta_raw, motivo)
            return nome, 'falha', linhas
        time.sleep(20)

    try:
        dr = reports_api.get_report_document(doc_id, download=True)
        doc = dr.payload['document']
        dados = json.loads(doc) if isinstance(doc, str) else doc
        n = len(dados.get('forecastByAsin', []) or [])
        if n == 0:
            motivo = 'relatorio veio sem forecastByAsin (a Amazon nao gerou previsao para esta conta)'
            log(f'[{nome}] [SEM DADO] {motivo}')
            _gravar_falha(pasta_raw, motivo)
            return nome, 'falha', linhas
        with open(alvo, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False)
        _limpar_falha(pasta_raw)
        asins = len({r.get('asin') for r in dados['forecastByAsin']})
        gerada = (dados['forecastByAsin'][0].get('forecastGenerationDate') or '?')
        log(f'[{nome}] [OK] {n} linhas, {asins} ASINs, previsao gerada em {gerada}')
        return nome, 'ok', linhas
    except Exception as e:
        motivo = f'erro ao baixar/ler: {type(e).__name__}: {str(e)[:200]}'
        log(f'[{nome}] [ERRO] {motivo}')
        _gravar_falha(pasta_raw, motivo)
        return nome, 'falha', linhas


def main():
    print(f"Previsao de demanda | contas em paralelo: {len(CONTAS_CONFIG)} | inicio: {datetime.now().strftime('%H:%M:%S')}\n")
    resumo = {}

    def trabalho(item):
        chave, cfg = item
        try:
            nome, status, linhas = processar_conta(chave, cfg)
        except Exception as e:                     # uma conta com problema nao derruba as outras
            nome, status, linhas = cfg['nome'], 'falha', [f"[{cfg['nome']}] [ERRO] {type(e).__name__}: {str(e)[:200]}"]
        with _TRAVA_LOG:
            print('\n'.join(linhas))
        return nome, status

    with ThreadPoolExecutor(max_workers=len(CONTAS_CONFIG)) as pool:
        for nome, status in pool.map(trabalho, list(CONTAS_CONFIG.items())):
            resumo[nome] = status

    print(f"\n{'='*60}\n=== RESUMO PREVISAO ===\n{'='*60}")
    for nome, status in resumo.items():
        print(f'{nome}: {status}')
    print('\nFalhas ficam em <conta>/raw/previsao_falhas.json e so sao repetidas apos 24h; o arquivo anterior e mantido.')
    print('Depois rode o transformar_vendor.py para a pagina Previsao mostrar os dados novos.')


main()
