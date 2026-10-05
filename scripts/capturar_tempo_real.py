# ==================================================================
# capturar_tempo_real.py
# CAPTURA EM TEMPO REAL (hora a hora) -- Vendas, Trafego e Estoque
# Celula unica, para as 7 contas do projeto START Vendor Analytics.
#
# Relatorios (Vendor Retail Analytics, SP-API):
#   GET_VENDOR_REAL_TIME_SALES_REPORT      -> orderedUnits, orderedRevenue
#   GET_VENDOR_REAL_TIME_TRAFFIC_REPORT    -> glanceViews
#   GET_VENDOR_REAL_TIME_INVENTORY_REPORT  -> highlyAvailableInventory
# Todos: uma linha por ASIN por hora cheia (startTime/endTime em UTC).
# Sem permissao nova: usa as mesmas autorizacoes do app "START Vendor
# Analytics" e os mesmos secrets dos outros scripts.
#
# COMO USAR
#   Colab: cole esta celula (ou salve em START_Vendor_Analytics/scripts/
#   e rode com exec) e rode. E INDEPENDENTE do rodar_tudo: tem cadencia
#   propria (sugerido 3 a 4 vezes por dia) e nao mexe no dados_vendor.json.
#   Teste rapido (1 conta, ultimas 3 horas, nao grava nada):
#       sys.argv = [ "x", "--teste", "alfa_jf"]; main()
#
# ONDE GRAVA
#   Drive (historico persistente, janela deslizante de 72h):
#     START_Vendor_Analytics/tempo_real/<conta>.json   (1 arquivo por conta)
#     START_Vendor_Analytics/tempo_real/index.json     (resumo + falhas)
#   GitHub Pages (se PUBLICAR = True): pasta tempo_real/ do repositorio
#   Grupo-start-onset/STARTZ, commit so dessa pasta -- o dashboard le de la.
#
# FORMATO de tempo_real/<conta>.json
#   {
#     "conta": "alfa_jf", "atualizado_em": "...Z", "moeda": "BRL", "fuso": "UTC",
#     "ultima_hora": "2026-09-25T17:00:00Z",          # ultima hora cheia capturada
#     "horas": [ {"h":"...Z","asin":"B0..","u":3,"r":89.7,"v":41}, ... ],
#        # u = unidades pedidas, r = receita pedida, v = visitas (glance views);
#        # so as chaves que existem (um ASIN pode ter venda sem visita e vice-versa)
#     "estoque": {"h":"...Z","itens":{"B0..":12, ...},"por_asin_h":{"B0..":"...Z"}},
#        # foto atual por ASIN, carregada para a frente (o relatorio de estoque e esparso);
#        # por_asin_h = hora da ultima informacao da Amazon para cada ASIN
#     "estoque_total": {"...Z": 1234, ...},               # soma por hora
#     "falhas": ["trafego"]        # relatorios que falharam nesta rodada
#   }
#
# REGRAS DE TEMPO (doc oficial da Amazon)
#   - so horas completas; o fim do periodo deve ser >= 60 min antes do pedido
#     (por isso fim = hora cheia atual - ATRASO_HORAS, com ATRASO_HORAS = 1);
#   - estoque: janela maxima de 24 h por chamada e ate 168 h para tras;
#     por seguranca todos os relatorios usam janelas de 24 h (e reduzem para
#     6 h e 1 h se a Amazon recusar).
#
# AVISOS
#   - Dado em tempo real muda: a Amazon pode descontar cancelamentos horas ou
#     dias depois, e as metricas por hora NAO batem com as diarias do ARA.
#   - Cada rodada recaptura as ultimas HORAS_JANELA horas e SUBSTITUI o que
#     havia nessa janela (correcoes da Amazon entram; linhas que sumiram saem).
#   - Se um relatorio de uma conta falhar, o dado anterior dela e mantido e o
#     nome do relatorio vai para "falhas" -- as outras contas seguem normais.
#   - O trafego termina 4h antes do pedido (ATRASO_HORAS_TIPO); com menos folga a
#     Amazon devolve FATAL. Entao a ultima hora de visitas fica ~3h atras de vendas.
#   - Quando um relatorio vem FATAL, o motivo (documento de erro da Amazon)
#     aparece no log, apos "motivo:".
#   - Publicacao: se o GITHUB_TOKEN nao puder ser lido (ja aconteceu uma vez em
#     25/09/2026), usa a copia do repositorio em /content/STARTZ, que o
#     publicar_github.py deixa autenticada. O log nunca mostra o token.
# ==================================================================

import os, sys, json, time
from datetime import datetime, timedelta, timezone

try:
    from google.colab import drive, userdata
    EM_COLAB = True
except ImportError:          # rodando fora do Colab (ex.: GitHub Actions)
    EM_COLAB = False
    # Fora do Colab, carrega o .env local (override=True: o .env sempre
    # vence sobre variavel de ambiente antiga/residual do shell -- mesma
    # logica de config.py/colab_shim.py, para nunca divergirem).
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

try:
    from sp_api.api import Reports
    from sp_api.base import Marketplaces
    from sp_api.base.exceptions import SellingApiException
except ImportError:
    os.system("pip install python-amazon-sp-api -q")
    from sp_api.api import Reports
    from sp_api.base import Marketplaces
    from sp_api.base.exceptions import SellingApiException

# ------------------------------------------------------------------
# CONFIGURACAO
# ------------------------------------------------------------------

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
MARKETPLACE = Marketplaces.BR
MARKETPLACE_ID = 'A2Q3Y263D00KWC'
MOEDA = 'BRL'

# mesma convencao de chave/pasta/secret de capturar_mensal.py e capturar_pedidos.py
# (a Petclean e a chave 'conta3', como no dados_vendor.json e no dashboard)
CONTAS_CONFIG = {
    'alfa_jf':   {'nome': 'ALFA JF',         'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'nome': 'Blid Shop',       'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'conta3':    {'nome': 'Petclean BR',     'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'nome': 'OZITP',           'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'nome': 'Jolitex',         'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'nome': 'Balboa',          'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'nome': 'BR - Rio Master', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
    'plastpet':  {'nome': 'Pet Factory Brazil Industria Ltda', 'secret': 'SP_API_REFRESH_TOKEN_PLASTPET'},
    'wiwu':      {'nome': 'WIWU', 'secret': 'SP_API_REFRESH_TOKEN_WIWU'},
}

# tipo interno -> (reportType da Amazon, campo da linha -> chave curta no arquivo)
RELATORIOS = {
    'vendas':  ('GET_VENDOR_REAL_TIME_SALES_REPORT',     {'orderedUnits': 'u', 'orderedRevenue': 'r'}),
    'trafego': ('GET_VENDOR_REAL_TIME_TRAFFIC_REPORT',   {'glanceViews': 'v'}),
    'estoque': ('GET_VENDOR_REAL_TIME_INVENTORY_REPORT', {'highlyAvailableInventory': 'e'}),
}
TIPOS_LINHA = ('vendas', 'trafego')     # entram em "horas"; estoque tem tratamento proprio

HORAS_JANELA = 48          # quanto tempo para tras recapturar a cada rodada (max 168)
HORAS_MANTER = 72          # historico mantido nos arquivos
ATRASO_HORAS = 1           # fim = hora cheia atual - ATRASO_HORAS (regra dos 60 min)
CHUNKS_HORAS = [24, 6, 1]  # tenta janelas grandes; se a Amazon recusar, reduz
# O relatorio de TRAFEGO da Amazon vem FATAL se o fim da janela for recente demais
# (testado: fim 1,4h atras = FATAL; fim 4h atras = OK). Por isso ele termina mais cedo.
ATRASO_HORAS_TIPO = {'trafego': 4}   # demais tipos usam ATRASO_HORAS

POLL_SEGUNDOS = 15
POLL_MAX_TENTATIVAS = 40   # ~10 min por relatorio
MAX_TENTATIVAS_COTA = 4
ESPERA_ENTRE_RELATORIOS = 4
ESPERA_ENTRE_CONTAS = 5

PUBLICAR = True            # False = so grava no Drive (sem GitHub)
GITHUB_USUARIO = 'Grupo-start-onset'
GITHUB_REPO = 'start-group-z-growth'
# Já rodamos de dentro do próprio checkout do repositório -- PASTA_REPO é
# a raiz do repositório, calculada a partir da localização deste arquivo.
PASTA_REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))


# ------------------------------------------------------------------
# CREDENCIAIS
# ------------------------------------------------------------------

def get_secret(nome):
    """Le dos Secrets do Colab ou de variaveis de ambiente."""
    if EM_COLAB:
        try:
            v = userdata.get(nome)
            if v:
                return v
        except Exception as e:
            print(f'  [aviso] nao consegui ler o secret {nome}: {type(e).__name__}')   # so o tipo do erro, nunca o valor
    return os.environ.get(nome)


def credenciais(chave):
    refresh = get_secret(CONTAS_CONFIG[chave]['secret'])
    cid = get_secret('SP_API_LWA_CLIENT_ID')
    csec = get_secret('SP_API_LWA_CLIENT_SECRET')
    if not (refresh and cid and csec):
        return None
    return dict(refresh_token=refresh, lwa_app_id=cid, lwa_client_secret=csec)


# ------------------------------------------------------------------
# TEMPO E NORMALIZACAO (funcoes puras)
# ------------------------------------------------------------------

def iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def hora_cheia_utc(dt=None):
    dt = dt or datetime.now(timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


def parse_hora(s):
    """ISO 8601 da API -> ISO padrao 'YYYY-MM-DDTHH:00:00Z' em UTC (ou None).
    Padroniza a chave para a mescla e a comparacao de texto serem seguras,
    seja qual for o formato devolvido (Z, +00:00, milissegundos)."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return iso(dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0))


def janela_tipo(agora, tipo, horas):
    """(ini, fim) da captura de um tipo. O inicio e o mesmo para todos; o fim e a hora cheia
    atual menos o atraso do tipo (o trafego exige mais folga que vendas e estoque)."""
    base = hora_cheia_utc(agora) - timedelta(hours=ATRASO_HORAS)
    fim = hora_cheia_utc(agora) - timedelta(hours=ATRASO_HORAS_TIPO.get(tipo, ATRASO_HORAS))
    return base - timedelta(hours=horas), fim      # mesmo inicio para todos; so o fim do trafego e mais cedo


def numero(v):
    """Numero de um campo da API. A receita do relatorio de vendas vem como
    numero simples; se um dia vier como {"amount":..}, tambem funciona."""
    if isinstance(v, dict):
        v = v.get('amount', 0)
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def normalizar(tipo, linhas):
    """Linhas cruas da API -> [{'h','asin', <chaves curtas>}], sem linhas invalidas."""
    campos = RELATORIOS[tipo][1]
    saida = []
    for l in linhas or []:
        h, asin = parse_hora(l.get('startTime')), l.get('asin')
        if not h or not asin:
            continue
        x = {'h': h, 'asin': asin}
        for campo, curto in campos.items():
            v = numero(l.get(campo))
            x[curto] = round(v, 2) if curto == 'r' else int(v)
        saida.append(x)
    return saida


def aplicar_janela(linhas, novas, curtos, ini, fim, limite):
    """Atualiza 'linhas' (lista de {'h','asin',...}) com 'novas' de UM relatorio.
    - remove, na janela [ini, fim), so as chaves 'curtos' desse relatorio
      (assim vendas e trafego se atualizam de forma independente);
    - junta as novas por (h, asin);
    - descarta o que ficou mais antigo que 'limite' e linhas ficaram vazias."""
    idx = {(x['h'], x['asin']): dict(x) for x in linhas}
    for x in idx.values():
        if ini <= x['h'] < fim:
            for c in curtos:
                x.pop(c, None)
    for n in novas:
        x = idx.setdefault((n['h'], n['asin']), {'h': n['h'], 'asin': n['asin']})
        for c in curtos:
            if c in n:
                x[c] = n[c]
    saida = [x for x in idx.values() if x['h'] >= limite and any(c in x for c in ('u', 'r', 'v'))]
    return sorted(saida, key=lambda x: (x['h'], x['asin']))


def montar_estoque(novas, estoque_total_antigo, estoque_antigo, limite, ini=None, fim=None):
    """Do relatorio de estoque: foto atual por ASIN + soma por hora.
    O relatorio de estoque em tempo real vem ESPARSO (poucas linhas por hora, so
    ASINs que a Amazon informou naquela hora). Por isso o estado de cada ASIN e
    CARREGADO para a frente: vale a ultima quantidade informada, mesmo de rodadas
    anteriores (o estado inicial e a foto da rodada anterior). Assim a foto nao
    perde os ASINs que nao apareceram na ultima hora, e a serie por hora soma o
    estado de todos os ASINs conhecidos, hora a hora.
    ini/fim (ISO, fim exclusivo) definem as horas recalculadas na serie."""
    estado = dict((estoque_antigo or {}).get('itens') or {})
    vistos = dict((estoque_antigo or {}).get('por_asin_h') or {})
    total = dict(estoque_total_antigo or {})
    if not novas:
        return estoque_antigo, {h: u for h, u in total.items() if h >= limite}
    por_hora = {}
    for n in novas:
        por_hora.setdefault(n['h'], {})[n['asin']] = max(0, n.get('e', 0))
    horas_serie = sorted(por_hora)
    if ini and fim:                                   # todas as horas da janela, mesmo sem linhas
        t, t_fim = parse_hora(ini), parse_hora(fim)
        horas_serie, cur = [], datetime.fromisoformat(t.replace('Z', '+00:00'))
        fim_dt = datetime.fromisoformat(t_fim.replace('Z', '+00:00'))
        while cur < fim_dt:
            horas_serie.append(iso(cur))
            cur += timedelta(hours=1)
        horas_serie = sorted(set(horas_serie) | set(por_hora))
    for h in horas_serie:
        for asin, q in por_hora.get(h, {}).items():
            estado[asin] = q
            vistos[asin] = h
        total[h] = sum(estado.values())
    ultima = horas_serie[-1] if horas_serie else max(por_hora)
    foto = {'h': ultima, 'itens': estado, 'por_asin_h': vistos}
    return foto, {h: u for h, u in sorted(total.items()) if h >= limite}


# ------------------------------------------------------------------
# CAPTURA (chamadas a API)
# ------------------------------------------------------------------

def baixar_relatorio(api, report_type, inicio, fim, opts):
    """Cria o relatorio, espera ficar pronto e devolve a lista reportData.
    Levanta excecao em falha (o chamador tenta janela menor)."""
    r = None
    for tentativa in range(1, MAX_TENTATIVAS_COTA + 1):
        try:
            pedido = dict(
                reportType=report_type,
                dataStartTime=iso(inicio),
                dataEndTime=iso(fim),
                marketplaceIds=[MARKETPLACE_ID],
            )
            if opts:                      # so o relatorio de vendas tem reportOptions (currencyCode)
                pedido['reportOptions'] = opts
            r = api.create_report(**pedido)
            break
        except SellingApiException as e:
            if ('QuotaExceeded' in str(e) or '429' in str(e)) and tentativa < MAX_TENTATIVAS_COTA:
                espera = 30 * tentativa
                print(f'    [cota excedida] aguardando {espera}s (tentativa {tentativa}/{MAX_TENTATIVAS_COTA})...')
                time.sleep(espera)
                continue
            raise
    report_id = r.payload['reportId']

    for _ in range(POLL_MAX_TENTATIVAS):
        time.sleep(POLL_SEGUNDOS)
        try:
            st = api.get_report(report_id).payload
        except Exception:
            continue                      # erro transitorio de rede/cota: tenta de novo
        status = st.get('processingStatus')
        if status == 'DONE':
            doc = api.get_report_document(st['reportDocumentId'], download=True)
            conteudo = doc.payload.get('document')
            if isinstance(conteudo, (bytes, bytearray)):
                conteudo = conteudo.decode('utf-8')
            data = json.loads(conteudo) if isinstance(conteudo, str) else (conteudo or {})
            if isinstance(data, dict) and data.get('errorDetails'):
                raise RuntimeError(data['errorDetails'])
            return (data.get('reportData') or []) if isinstance(data, dict) else []
        if status in ('FATAL', 'CANCELLED'):
            detalhe = ''
            if st.get('reportDocumentId'):    # a Amazon costuma explicar o motivo no documento do relatorio
                try:
                    d = api.get_report_document(st['reportDocumentId'], download=True).payload.get('document')
                    if isinstance(d, (bytes, bytearray)):
                        d = d.decode('utf-8', 'replace')
                    detalhe = ' | motivo: ' + str(d)[:300].replace('\n', ' ')
                except Exception as e2:
                    detalhe = f' | (nao consegui ler o documento de erro: {e2})'
            raise RuntimeError(f'relatorio {status} ({iso(inicio)} a {iso(fim)}){detalhe}')
    raise TimeoutError('relatorio nao ficou pronto a tempo')


def capturar_tipo(api, chave, tipo, inicio, fim):
    """Captura um tipo de relatorio de uma conta, em janelas. None = falhou."""
    report_type = RELATORIOS[tipo][0]
    opts = {'currencyCode': MOEDA} if tipo == 'vendas' else {}
    for horas in CHUNKS_HORAS:
        linhas, cursor, ok = [], inicio, True
        while cursor < fim:
            prox = min(cursor + timedelta(hours=horas), fim)
            try:
                linhas += baixar_relatorio(api, report_type, cursor, prox, opts)
            except Exception as e:
                print(f'  [{chave}] {tipo}: janela de {horas}h falhou ({e})')
                ok = False
                break
            cursor = prox
            time.sleep(ESPERA_ENTRE_RELATORIOS)
        if ok:
            return linhas
    print(f'  [{chave}] {tipo}: nao foi possivel capturar')
    return None


# ------------------------------------------------------------------
# ARQUIVOS
# ------------------------------------------------------------------

def carregar_conta(pasta, chave):
    alvo = os.path.join(pasta, f'{chave}.json')
    if os.path.exists(alvo):
        try:
            with open(alvo, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                return d
        except Exception:
            print(f'  [{chave}] arquivo anterior ilegivel, comecando do zero')
    return {}


def gravar_json(caminho, obj):
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))


def atualizar_conta(anterior, chave, capturas, janelas, limite, agora):
    """capturas: {tipo: linhas_normalizadas ou None}; janelas: {tipo: (ini, fim)}.
    Devolve o dict da conta."""
    horas = list(anterior.get('horas', []))
    falhas = []
    for tipo in TIPOS_LINHA:
        novas = capturas.get(tipo)
        if novas is None:
            falhas.append(tipo)
            continue
        curtos = list(RELATORIOS[tipo][1].values())
        ini_t, fim_t = janelas[tipo]
        horas = aplicar_janela(horas, novas, curtos, iso(ini_t), iso(fim_t), limite)
    novas_est = capturas.get('estoque')
    if novas_est is None:
        falhas.append('estoque')
        estoque, total = anterior.get('estoque'), {h: u for h, u in (anterior.get('estoque_total') or {}).items() if h >= limite}
    else:
        ini_e, fim_e = janelas['estoque']
        estoque, total = montar_estoque(novas_est, anterior.get('estoque_total'), anterior.get('estoque'), limite, iso(ini_e), iso(fim_e))
    ultima = max([x['h'] for x in horas] + list(total.keys()) + [(estoque or {}).get('h', '')] or [''])
    return {
        'conta': chave, 'atualizado_em': iso(agora), 'moeda': MOEDA, 'fuso': 'UTC',
        'ultima_hora': ultima or None,
        'horas': horas, 'estoque': estoque, 'estoque_total': total, 'falhas': falhas,
    }


# ------------------------------------------------------------------
# PUBLICACAO (so a pasta tempo_real/ do repositorio)
# ------------------------------------------------------------------

def rodar(cmd):
    import subprocess
    import re
    r = subprocess.run(cmd, capture_output=True, text=True)
    oculta = lambda t: re.sub(r'https://[^@\s]+@', 'https://***@', t)      # nunca imprime token
    if r.stdout.strip():
        print(oculta(r.stdout.strip()))
    if r.returncode != 0:
        print(oculta(r.stderr.strip()))
    return r


def publicar(pasta_origem):
    import shutil
    # Já rodamos dentro do próprio checkout do repositório: sem clone,
    # sem token embutido -- só atualiza o checkout local e publica.
    rodar(['git', '-C', PASTA_REPO, 'pull', '--rebase'])
    destino = os.path.join(PASTA_REPO, 'tempo_real')
    os.makedirs(destino, exist_ok=True)
    for arq in os.listdir(pasta_origem):
        if arq.endswith('.json'):
            shutil.copy(os.path.join(pasta_origem, arq), os.path.join(destino, arq))
    rodar(['git', '-C', PASTA_REPO, 'config', 'user.email', 'pipeline@startgrupo.com'])
    rodar(['git', '-C', PASTA_REPO, 'config', 'user.name', 'START Vendor Analytics (pipeline)'])
    rodar(['git', '-C', PASTA_REPO, 'add', '-A', 'tempo_real'])
    msg = f'Atualiza tempo_real — {datetime.now().strftime("%Y-%m-%d %H:%M")}'
    r = rodar(['git', '-C', PASTA_REPO, 'commit', '-m', msg])
    if 'nothing to commit' in (r.stdout + r.stderr):
        print('Nada mudou desde a ultima publicacao.')
        return
    rodar(['git', '-C', PASTA_REPO, 'pull', '--rebase'])
    rodar(['git', '-C', PASTA_REPO, 'push'])
    print(f'Publicado! https://{GITHUB_USUARIO.lower()}.github.io/{GITHUB_REPO}/dashboard_base.html#/tempo-real')


# ------------------------------------------------------------------
# EXECUCAO
# ------------------------------------------------------------------

def main():
    if EM_COLAB and not os.path.isdir('/content/drive/MyDrive'):
        drive.mount('/content/drive', force_remount=True)

    agora = datetime.now(timezone.utc)
    fim = hora_cheia_utc(agora) - timedelta(hours=ATRASO_HORAS)

    # ---------------- modo teste ----------------
    if '--teste' in sys.argv:
        chave = sys.argv[sys.argv.index('--teste') + 1]
        if chave not in CONTAS_CONFIG:
            print(f'Conta "{chave}" invalida. Use uma destas: {", ".join(CONTAS_CONFIG)}')
            return
        cred = credenciais(chave)
        if not cred:
            print(f'[{chave}] sem credenciais (secrets do Colab).')
            return
        api = Reports(credentials=cred, marketplace=MARKETPLACE)
        print(f'TESTE {CONTAS_CONFIG[chave]["nome"]}: ultimas 3 horas de cada relatorio (nada sera gravado)')
        for tipo in RELATORIOS:
            ini_t, fim_t = janela_tipo(agora, tipo, 3)
            ini_t = fim_t - timedelta(hours=3)      # 3h de dados terminando no fim proprio do tipo
            print(f'\n[{tipo}] janela {iso(ini_t)} a {iso(fim_t)}')
            linhas = capturar_tipo(api, chave, tipo, ini_t, fim_t)
            print(f'\n[{tipo}] ' + ('FALHOU' if linhas is None else f'{len(linhas)} linhas'))
            for l in (linhas or [])[:5]:
                print('  cru:', l)
            if linhas:
                print('  normalizado:', normalizar(tipo, linhas)[:2])
        return

    # ---------------- rodada normal ----------------
    horas_jan = min(HORAS_JANELA, 168)
    limite = iso(fim - timedelta(hours=HORAS_MANTER))
    pasta = os.path.join(BASE_DRIVE, 'tempo_real')
    os.makedirs(pasta, exist_ok=True)
    janelas = {t: janela_tipo(agora, t, horas_jan) for t in RELATORIOS}
    for t, (i_t, f_t) in janelas.items():
        print(f'Janela {t}: {iso(i_t)} a {iso(f_t)} (UTC)')
    print(f'Historico mantido: {HORAS_MANTER}h\n')

    resumo, indice = {}, {}
    for chave, cfg in CONTAS_CONFIG.items():
        print(f'{"#"*60}\n# CONTA: {cfg["nome"]}\n{"#"*60}')
        cred = credenciais(chave)
        if not cred:
            print(f'  [{chave}] sem credenciais, pulando')
            resumo[cfg['nome']] = 'sem credenciais'
            continue
        api = Reports(credentials=cred, marketplace=MARKETPLACE)
        capturas = {}
        for tipo in RELATORIOS:
            bruto = capturar_tipo(api, chave, tipo, *janelas[tipo])
            capturas[tipo] = None if bruto is None else normalizar(tipo, bruto)
            print(f'  [{chave}] {tipo}: ' + ('FALHOU' if bruto is None else f'{len(bruto)} linhas'))
        anterior = carregar_conta(pasta, chave)
        conta = atualizar_conta(anterior, chave, capturas, janelas, limite, agora)
        gravar_json(os.path.join(pasta, f'{chave}.json'), conta)
        indice[chave] = {'nome': cfg['nome'], 'ultima_hora': conta['ultima_hora'],
                         'linhas': len(conta['horas']), 'falhas': conta['falhas']}
        resumo[cfg['nome']] = f'{len(conta["horas"])} linhas' + (f' | FALHAS: {", ".join(conta["falhas"])}' if conta['falhas'] else '')
        time.sleep(ESPERA_ENTRE_CONTAS)

    gravar_json(os.path.join(pasta, 'index.json'),
                {'atualizado_em': iso(agora), 'fuso': 'UTC', 'moeda': MOEDA, 'contas': indice})

    print(f'\n{"="*60}\n=== RESUMO ===\n{"="*60}')
    for nome, r in resumo.items():
        print(f'{nome}: {r}')
    print('\nSe algum relatorio aparecer em FALHAS, rode de novo mais tarde --')
    print('o dado anterior daquela conta foi mantido.')

    if PUBLICAR and '--sem-publicar' not in sys.argv:
        print('\nPublicando no GitHub...')
        publicar(pasta)


if __name__ == '__main__':
    main()
