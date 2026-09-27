# ==================================================================
# transformar_brand.py
# Preenche CONTAS[<conta>].extras (Brand Analytics) no dados_vendor.json.
#
# Le, de cada conta, os arquivos gerados pelo capturar_brand_analytics.py:
#   START_Vendor_Analytics/<conta>/raw/brand_cesta_compras_<ini>_a_<fim>.json
#                                      brand_termos_busca_<ini>_a_<fim>.json
#                                      brand_recompra_<ini>_a_<fim>.json
# (usa a semana MAIS RECENTE de cada tipo) e escreve:
#
#   extras = {
#     "cestaCompras": [ {"asin","com","rank","pct"} ],   # comprado junto com (ate 5 por ASIN)
#     "termosBusca":  [ {"termo","depto","freq","asin","cliqueRank","click","conv"} ],
#                      # freq = ranking de frequencia de busca (1 = mais buscado); click e conv
#                      # = parcela de cliques e de conversao do ASIN nesse termo (fracao 0 a 1)
#     "recompra":     [ {"asin","pedidos","clientes","pctRec","receitaRec","pctReceitaRec"} ],
#     "semanaBrand":  {"cestaCompras":"2026-09-13 a 2026-09-19", ...}   # semana usada em cada tipo
#   }
#
# Formatos esperados (Amazon Brand Analytics; leitura defensiva de campos e de escala):
#   market basket:   dataByAsin[] UMA LINHA POR PAR {asin, purchasedWithAsin, purchasedWithRank,
#                    combinationPct} (formato plano, confirmado com dado real em 25/09/2026)
#   search terms:    linhas {departmentName, searchTerm, searchFrequencyRank, clickedAsin, clickedItemName,
#                            clickShareRank, clickShare, conversionShare}  (fracoes 0 a 1)
#   repeat purchase: dataByAsin[] {asin, orders, uniqueCustomers, repeatCustomersPctTotal,
#                                  repeatPurchaseRevenue{amount}, repeatPurchaseRevenuePctTotal}
#                    (varios ASINs vem com campos null: sem dado na semana)
# Percentuais: se algum valor de um campo passar de 1, o campo inteiro vem em pontos
# percentuais (12,5 = 12,5%) e e dividido por 100; assim o dashboard sempre recebe fracao.
#
# Segue o padrao do transformar_semanas.py: roda DEPOIS do transformar_vendor.py, le o
# dados_vendor.json e reescreve o mesmo arquivo. Idempotente.
# Ordem no rodar_tudo: ... transformar_vendor -> transformar_semanas -> transformar_brand -> publicar
# ==================================================================

import json, glob, os

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
ARQUIVO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_vendor.json'))

CONTAS_CONFIG = {
    'alfa_jf':   'alfa_jf/raw',
    'blidshop':  'blidshop/raw',
    'conta3':    'petclean/raw',
    'ozitp':     'ozitp/raw',
    'jolitex':   'jolitex/raw',
    'balboa':    'balboa/raw',
    'riomaster': 'riomaster/raw',
}

MAX_COMPRADO_JUNTO = 5      # por ASIN
MAX_TERMOS = 1000           # por conta (os mais buscados)


def amount(v):
    if isinstance(v, dict):
        return v.get('amount', 0) or 0
    return v or 0


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def para_fracao(linhas, campos):
    """Se algum valor de um campo passar de 1, o campo inteiro esta em pontos percentuais: divide por 100."""
    for c in campos:
        vals = [l[c] for l in linhas if isinstance(l.get(c), (int, float))]
        if vals and max(vals) > 1.0:
            for l in linhas:
                if isinstance(l.get(c), (int, float)):
                    l[c] = l[c] / 100.0
    return linhas


def arquivo_mais_recente(pasta_raw, nome):
    """(caminho, 'ini a fim') do arquivo brand_<nome>_*.json com a semana mais nova, ou (None, None)."""
    arqs = sorted(glob.glob(f'{pasta_raw}/brand_{nome}_*.json'))
    if not arqs:
        return None, None
    a = arqs[-1]
    base = os.path.basename(a)[len(f'brand_{nome}_'):-len('.json')]      # 2026-09-13_a_2026-09-19
    return a, base.replace('_a_', ' a ')


def ler(caminho):
    try:
        return json.load(open(caminho, encoding='utf-8'))
    except Exception as e:
        print(f'  [aviso] nao consegui ler {caminho}: {e}')
        return None


def montar_cesta(dados):
    """Cesta de compras. Formato REAL confirmado em 25/09/2026: cada linha de dataByAsin ja e um par
    {asin, purchasedWithAsin, purchasedWithRank, combinationPct} (plano). Tambem aceita o formato
    aninhado (purchasedWith: [...]) por seguranca."""
    por_asin = {}
    for r in dados.get('dataByAsin', []):
        asin = r.get('asin')
        if not asin:
            continue
        pares = []
        if r.get('purchasedWithAsin'):                                   # plano (formato real)
            pares.append(r)
        for c in (r.get('purchasedWith') or []):                          # aninhado (alternativo)
            if c.get('purchasedWithAsin'):
                pares.append(c)
        for c in pares:
            por_asin.setdefault(asin, []).append(c)
    linhas = []
    for asin, pares in por_asin.items():
        pares.sort(key=lambda x: x.get('purchasedWithRank') or 9999)
        for c in pares[:MAX_COMPRADO_JUNTO]:
            linhas.append({'asin': asin, 'com': c['purchasedWithAsin'],
                           'rank': c.get('purchasedWithRank'), 'pct': num(c.get('combinationPct'))})
    return para_fracao(linhas, ['pct'])


def montar_termos(dados):
    linhas = []
    for r in dados.get('linhas', []):
        if not r.get('searchTerm'):
            continue
        linhas.append({'termo': r['searchTerm'], 'depto': r.get('departmentName'),
                       'freq': r.get('searchFrequencyRank'), 'asin': r.get('clickedAsin'),
                       'cliqueRank': r.get('clickShareRank'),
                       'click': num(r.get('clickShare')), 'conv': num(r.get('conversionShare'))})
    linhas.sort(key=lambda x: (x['freq'] if x['freq'] is not None else 10**12))
    return para_fracao(linhas[:MAX_TERMOS], ['click', 'conv'])


def montar_recompra(dados):
    linhas = []
    for r in dados.get('dataByAsin', []):
        if not r.get('asin'):
            continue
        linhas.append({'asin': r['asin'], 'pedidos': r.get('orders'), 'clientes': r.get('uniqueCustomers'),
                       'pctRec': num(r.get('repeatCustomersPctTotal')),
                       'receitaRec': num(amount(r.get('repeatPurchaseRevenue'))),
                       'pctReceitaRec': num(r.get('repeatPurchaseRevenuePctTotal'))})
    return para_fracao(linhas, ['pctRec', 'pctReceitaRec'])


def processar_conta(pasta_raw):
    """Devolve o bloco extras, ou None se nao ha nenhum arquivo brand_*.json."""
    extras = {'cestaCompras': [], 'termosBusca': [], 'recompra': [], 'semanaBrand': {}}
    achou = False
    for nome, chave, montar in (('cesta_compras', 'cestaCompras', montar_cesta),
                                ('termos_busca', 'termosBusca', montar_termos),
                                ('recompra', 'recompra', montar_recompra)):
        arq, semana = arquivo_mais_recente(pasta_raw, nome)
        if not arq:
            continue
        dados = ler(arq)
        if not isinstance(dados, dict):
            continue
        extras[chave] = montar(dados)
        extras['semanaBrand'][chave] = semana
        achou = True
    return extras if achou else None


def main():
    assert os.path.exists(ARQUIVO), (
        f'{ARQUIVO} nao encontrado na pasta atual -- rode o transformar_vendor.py primeiro, na mesma sessao.')
    with open(ARQUIVO, encoding='utf-8') as f:
        contas = json.load(f)

    for chave, pasta in CONTAS_CONFIG.items():
        if chave not in contas:
            continue
        extras = processar_conta(os.path.join(BASE_DRIVE, pasta))
        if extras is None:
            print(f'[{chave}] sem arquivos brand_*.json (rode capturar_brand_analytics.py) -- extras mantido como estava')
            continue
        contas[chave]['extras'] = extras
        print(f"[{chave}] cesta: {len(extras['cestaCompras'])} | termos: {len(extras['termosBusca'])} | "
              f"recompra: {len(extras['recompra'])} ASINs | semanas: {extras['semanaBrand']}")

    with open(ARQUIVO, 'w', encoding='utf-8') as f:
        json.dump(contas, f, ensure_ascii=False, separators=(',', ':'))
    print(f'\nSalvo: {ARQUIVO} ({os.path.getsize(ARQUIVO):,} bytes)')


if __name__ == '__main__':
    main()
