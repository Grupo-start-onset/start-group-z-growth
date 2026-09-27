# ==================================================================
# transformar_destaque.py
# Acrescenta ao dados_vendor.json o bloco OFERTA EM DESTAQUE (Buy Box), vindo do Data Kiosk.
#
# Le, de cada conta, os arquivos gerados pelo capturar_data_kiosk.py:
#   START_Vendor_Analytics/<conta>/raw/dk_traffic_<ini>_a_<fim>.json
# e escreve em CONTAS[<conta>].ofertaDestaque:
#
#   {
#     "semanas": [ {"id":"2026-09-13","ini":"2026-09-13","fim":"2026-09-19"}, ... ],  # antiga -> nova
#     "porAsin": { "<asin>": { "<id da semana>": [glanceViews, lostFeaturedOffer], ... } },
#     "totais":  { "<id da semana>": [glanceViews, lostFeaturedOffer] }
#   }
#
#   glanceViews        visualizacoes em que a Amazon GANHA a oferta em destaque (int ou null)
#   lostFeaturedOffer  fracao 0 a 1 das visualizacoes em que a oferta em destaque NAO e da Amazon
#                      (float ou null). Visualizacoes totais = glanceViews / (1 - lostFeaturedOffer);
#                      com lostFeaturedOffer = 1 o total nao e calculavel (glanceViews = 0).
#   O id da semana e o domingo (mesmo id do bloco porAsinSem, que traz receita e visitas do ARA).
#
# Segue o padrao do transformar_semanas.py: roda DEPOIS do transformar_vendor.py, le o
# dados_vendor.json e reescreve o mesmo arquivo. Idempotente.
# Ordem no rodar_tudo: ... transformar_vendor -> transformar_semanas -> transformar_brand ->
# transformar_destaque -> publicar_github
# ==================================================================

import json, glob, os

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
ARQUIVO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_vendor.json'))
MAX_SEMANAS = 8

CONTAS_CONFIG = {
    'alfa_jf':   'alfa_jf/raw',
    'blidshop':  'blidshop/raw',
    'conta3':    'petclean/raw',
    'ozitp':     'ozitp/raw',
    'jolitex':   'jolitex/raw',
    'balboa':    'balboa/raw',
    'riomaster': 'riomaster/raw',
}


def par(traf):
    """{'glanceViews':..,'lostFeaturedOffer':..} -> [gv, lost] (None onde nao ha dado)."""
    traf = traf or {}
    gv, lost = traf.get('glanceViews'), traf.get('lostFeaturedOffer')
    gv = int(gv) if isinstance(gv, (int, float)) else None
    lost = float(lost) if isinstance(lost, (int, float)) else None
    if lost is not None:
        lost = min(1.0, max(0.0, lost))
    return [gv, lost]


def processar_destaque(pasta_raw):
    """Devolve o bloco ofertaDestaque, ou None se nao ha arquivos dk_traffic_*.json."""
    arqs = sorted(glob.glob(f'{pasta_raw}/dk_traffic_*.json'))[-MAX_SEMANAS:]
    semanas, por_asin, totais = [], {}, {}
    for arq in arqs:
        try:
            d = json.load(open(arq, encoding='utf-8'))
        except Exception as e:
            print(f'  [aviso] nao consegui ler {arq}: {e}')
            continue
        if not d.get('ini'):
            continue
        sid = d['ini']
        semanas.append({'id': sid, 'ini': d['ini'], 'fim': d.get('fim')})
        totais[sid] = par((d.get('totals') or {}).get('traffic'))
        for m in d.get('metrics') or []:
            asin = ((m.get('groupByKey') or {}).get('asin'))
            if not asin:
                continue
            por_asin.setdefault(asin, {})[sid] = par(((m.get('metrics') or {}).get('traffic')))
    if not semanas:
        return None
    return {'semanas': semanas, 'porAsin': por_asin, 'totais': totais}


def main():
    assert os.path.exists(ARQUIVO), (
        f'{ARQUIVO} nao encontrado na pasta atual -- rode o transformar_vendor.py primeiro, na mesma sessao.')
    with open(ARQUIVO, encoding='utf-8') as f:
        contas = json.load(f)

    for chave, pasta in CONTAS_CONFIG.items():
        if chave not in contas:
            continue
        bloco = processar_destaque(os.path.join(BASE_DRIVE, pasta))
        if not bloco:
            contas[chave].pop('ofertaDestaque', None)
            print(f'[{chave}] sem arquivos dk_traffic_*.json (sem acesso a Data Kiosk ou ainda nao capturado) -- bloco removido')
            continue
        contas[chave]['ofertaDestaque'] = bloco
        ult = bloco['semanas'][-1]['id']
        tot = bloco['totais'].get(ult) or [None, None]
        com_dado = sum(1 for v in bloco['porAsin'].values() if (v.get(ult) or [None, None])[1] is not None)
        print(f"[{chave}] {len(bloco['semanas'])} semanas | ultima {ult}: total {tot[0]} visualizacoes, "
              f"{'sem dado' if tot[1] is None else f'{tot[1]*100:.1f}% perdidas'} | {com_dado} ASINs com dado")

    with open(ARQUIVO, 'w', encoding='utf-8') as f:
        json.dump(contas, f, ensure_ascii=False, separators=(',', ':'))
    print(f'\nSalvo: {ARQUIVO} ({os.path.getsize(ARQUIVO):,} bytes)')


if __name__ == '__main__':
    main()
