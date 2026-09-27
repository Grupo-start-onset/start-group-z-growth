# ==================================================================
# transformar_semanas.py
# Acrescenta ao dados_vendor.json o bloco SEMANAL (mes em andamento).
#
# Le, de cada conta, os arquivos gerados pelo capturar_semanal.py:
#   START_Vendor_Analytics/<conta>/raw/vendas_sem_*.json
#                                     estoque_sem_*.json
#                                     trafego_sem_*.json
#                                     margem_sem_*.json
# e escreve em CONTAS[<conta>] tres blocos novos (o resto nao e tocado):
#
#   semanas:    [ {"id":"2026-08-30","ini":"2026-08-30","fim":"2026-09-05","num":36}, ... ]
#               (semanas fechadas, domingo a sabado, da mais antiga para a mais nova)
#   aggSem:     { "<id>": { orderedRevenue, orderedUnits, shippedRevenue, shippedUnits,
#                           shippedCogs, customerReturns, glanceViews, npm,
#                           sellableUnits, sellableCost, unhealthyCost, oosRate, sellThrough } }
#   porAsinSem: { "<asin>": { "<id>": { "r": receita pedida, "u": unidades pedidas,
#                                        "v": visitas, "e": estoque vendavel (un) } } }
#               (so ASINs com venda ou visita na semana)
#
# POR QUE E SEPARADO DO transformar_vendor.py
#   Segue o padrao do enriquecer_qualidade_cdq.py: roda DEPOIS do
#   transformar_vendor.py, le o dados_vendor.json ja gerado e reescreve o
#   mesmo arquivo. Assim o transformar_vendor.py (grande, validado) nao muda.
#   E idempotente: pode rodar quantas vezes quiser.
#
# ATENCAO (dupla contagem): a semana que cruza a virada do mes (ex.: sem 36 =
# 30/08 a 05/09) inclui dias que tambem estao no mes anterior (30 e 31/08).
# Por isso o dashboard mostra as semanas SEPARADAS dos totais mensais.
#
# Ordem no rodar_tudo: ... capturar_semanal -> transformar_vendor ->
# transformar_semanas -> publicar_github
# ==================================================================

import json, glob, os
from datetime import datetime, timedelta

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
ARQUIVO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_vendor.json'))
MAX_SEMANAS = 8                    # quantas semanas mais recentes manter no dados_vendor.json

# mesma convencao de chave/pasta do transformar_vendor.py
CONTAS_CONFIG = {
    'alfa_jf':   'alfa_jf/raw',
    'blidshop':  'blidshop/raw',
    'conta3':    'petclean/raw',     # pasta fisica e petclean/raw; a chave e conta3
    'ozitp':     'ozitp/raw',
    'jolitex':   'jolitex/raw',
    'balboa':    'balboa/raw',
    'riomaster': 'riomaster/raw',
}


def amount(v):
    """Extrai .amount de campos monetarios {"amount":X,"currencyCode":"BRL"}."""
    if isinstance(v, dict):
        return v.get('amount', 0) or 0
    return v or 0


def n(v):
    return 0 if v is None else v


def numero_semana(domingo):
    """Semana 1 = a que contem 1o de janeiro (domingo a sabado); a semana de virada
    de ano e a semana 1 do ano novo (usa o ano do sabado)."""
    ano = (domingo + timedelta(days=6)).year
    j1 = datetime(ano, 1, 1)
    ini = j1 - timedelta(days=(j1.weekday() + 1) % 7)
    return (domingo - ini).days // 7 + 1


def _lista(pasta_raw, prefixo):
    """Le todos os arquivos <prefixo>_*.json e devolve os dicts validos."""
    for arq in sorted(glob.glob(f'{pasta_raw}/{prefixo}_*.json')):
        try:
            d = json.load(open(arq, encoding='utf-8'))
        except Exception as e:
            print(f'  [aviso] {os.path.basename(arq)} ilegivel ({e}) -- ignorado')
            continue
        if isinstance(d, dict):
            yield d
        else:
            print(f'  [aviso] {os.path.basename(arq)} nao e um relatorio -- ignorado')


def processar_semanas(pasta_raw, max_semanas=MAX_SEMANAS):
    """Devolve {'semanas':[...], 'aggSem':{...}, 'porAsinSem':{...}} ou None se nao houver semana."""
    agg, asin_sem, limites = {}, {}, {}

    def marca(r):
        ini = (r.get('startDate') or '')[:10]
        if ini:
            limites[ini] = (r.get('endDate') or '')[:10]
        return ini

    def ganchar(asin, sid, **campos):
        e = asin_sem.setdefault(asin, {}).setdefault(sid, {})
        e.update(campos)

    for d in _lista(pasta_raw, 'vendas_sem'):
        for r in d.get('salesAggregate', []) or []:
            sid = marca(r)
            if not sid:
                continue
            agg.setdefault(sid, {}).update({
                'orderedRevenue': amount(r.get('orderedRevenue')), 'orderedUnits': n(r.get('orderedUnits')),
                'shippedRevenue': amount(r.get('shippedRevenue')), 'shippedUnits': n(r.get('shippedUnits')),
                'shippedCogs': amount(r.get('shippedCogs')), 'customerReturns': n(r.get('customerReturns')),
            })
        for r in d.get('salesByAsin', []) or []:
            sid = marca(r)
            if sid and r.get('asin'):
                ganchar(r['asin'], sid, r=amount(r.get('orderedRevenue')), u=n(r.get('orderedUnits')))

    for d in _lista(pasta_raw, 'trafego_sem'):
        for r in d.get('trafficAggregate', []) or []:
            sid = marca(r)
            if sid:
                agg.setdefault(sid, {})['glanceViews'] = n(r.get('glanceViews'))
        for r in d.get('trafficByAsin', []) or []:
            sid = marca(r)
            if sid and r.get('asin'):
                ganchar(r['asin'], sid, v=n(r.get('glanceViews')))

    for d in _lista(pasta_raw, 'margem_sem'):
        for r in d.get('netPureProductMarginAggregate', []) or []:
            sid = marca(r)
            if sid:
                agg.setdefault(sid, {})['npm'] = r.get('netPureProductMargin')

    for d in _lista(pasta_raw, 'estoque_sem'):
        for r in d.get('inventoryAggregate', []) or []:
            sid = marca(r)
            if sid:
                agg.setdefault(sid, {}).update({
                    'sellableUnits': n(r.get('sellableOnHandInventoryUnits')),
                    'sellableCost': amount(r.get('sellableOnHandInventoryCost')),
                    'unhealthyCost': amount(r.get('unhealthyInventoryCost')),
                    'oosRate': n(r.get('procurableProductOutOfStockRate')),
                    'sellThrough': n(r.get('sellThroughRate')),
                })
        for r in d.get('inventoryByAsin', []) or []:
            sid = marca(r)
            if sid and r.get('asin'):
                ganchar(r['asin'], sid, e=n(r.get('sellableOnHandInventoryUnits')))

    if not agg:
        return None

    ids = sorted(agg)[-max_semanas:]
    semanas = []
    for sid in ids:
        ini = datetime.strptime(sid, '%Y-%m-%d')
        fim = limites.get(sid) or (ini + timedelta(days=6)).strftime('%Y-%m-%d')
        semanas.append({'id': sid, 'ini': sid, 'fim': fim, 'num': numero_semana(ini)})

    por_asin = {}
    for asin, ss in asin_sem.items():
        for sid, v in ss.items():
            if sid in ids and (v.get('r') or v.get('u') or v.get('v')):   # so ASIN com venda ou visita
                por_asin.setdefault(asin, {})[sid] = v
    return {'semanas': semanas, 'aggSem': {sid: agg[sid] for sid in ids}, 'porAsinSem': por_asin}


def main():
    assert os.path.exists(ARQUIVO), (
        f'{ARQUIVO} nao encontrado na pasta atual -- rode o transformar_vendor.py primeiro, na mesma sessao.')
    with open(ARQUIVO, encoding='utf-8') as f:
        contas = json.load(f)

    for chave, pasta in CONTAS_CONFIG.items():
        if chave not in contas:
            continue
        pasta_raw = os.path.join(BASE_DRIVE, pasta)
        bloco = processar_semanas(pasta_raw)
        if not bloco:
            for k in ('semanas', 'aggSem', 'porAsinSem'):
                contas[chave].pop(k, None)
            print(f'[{chave}] sem arquivos semanais em {pasta_raw} (rode capturar_semanal.py) -- bloco removido')
            continue
        contas[chave].update(bloco)
        s = bloco['semanas']
        rec = sum(bloco['aggSem'][x['id']].get('orderedRevenue', 0) for x in s)
        print(f"[{chave}] {len(s)} semanas ({', '.join('S' + str(x['num']) for x in s)}) | "
              f"receita pedida somada R$ {rec:,.0f} | {len(bloco['porAsinSem'])} ASINs com venda/visita")

    with open(ARQUIVO, 'w', encoding='utf-8') as f:
        json.dump(contas, f, ensure_ascii=False, separators=(',', ':'))
    print(f'\nSalvo: {ARQUIVO} ({os.path.getsize(ARQUIVO):,} bytes)')


if __name__ == '__main__':
    main()
