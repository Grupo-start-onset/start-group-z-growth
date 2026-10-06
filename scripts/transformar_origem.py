# ==================================================================
# transformar_origem.py
# Acrescenta ao dados_vendor.json o bloco ORIGEM X FABRICACAO (card
# "Venda propria x outros distribuidores" do dashboard).
#
# A Amazon tem duas visoes oficiais pra relatorio de vendas de vendor:
#   MANUFACTURING (ja capturado em vendas_mes_*.json) = soma TODOS os
#     distribuidores cadastrados na mesma marca/fabricante, nao so a
#     conta do cliente.
#   SOURCING (novo, capturado em vendas_mes_origem_*.json pelo
#     capturar_mensal.py) = so o que foi efetivamente abastecido pela
#     conta do cliente.
# A diferenca (Fabricacao - Origem) e vendido por OUTROS distribuidores/
# marketplace que nao passaram pela conta do cliente.
#
# Le, de cada conta, os ultimos MAX_MESES meses FECHADOS presentes em
# ambos os conjuntos de arquivo e escreve em CONTAS[<conta>].origemFabricacao:
#
#   {
#     "meses": [ {"id":"2026-04","fabricacao":912345.0,"origem":882345.0}, ... ],
#     "totais": {
#        "fabricacao": soma dos ultimos MAX_MESES meses,
#        "origem": soma dos ultimos MAX_MESES meses,
#        "outrosDistribuidores": max(0, fabricacao - origem),
#        "outrosDistribuidoresPct": outrosDistribuidores / fabricacao (fracao)
#     }
#   }
#
# Usa shippedRevenue (presente nas duas visoes; a visao SOURCING da Amazon
# nao traz orderedRevenue). Mes sem arquivo em uma das duas visoes fica de
# fora (a Amazon so fecha SOURCING com alguns dias de atraso, igual MANUFACTURING).
#
# Segue o padrao do transformar_semanas.py: roda DEPOIS do transformar_vendor.py,
# le o dados_vendor.json ja gerado e reescreve o mesmo arquivo. Idempotente.
# Ordem no rodar_tudo: ... transformar_brand -> transformar_origem -> publicar_github
# ==================================================================

import json, glob, os, re

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))
ARQUIVO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_vendor.json'))
MAX_MESES = 6                      # ultimos N meses fechados, igual o painel de referencia

CONTAS_CONFIG = {
    'alfa_jf':   'alfa_jf/raw',
    'blidshop':  'blidshop/raw',
    'conta3':    'petclean/raw',
    'ozitp':     'ozitp/raw',
    'jolitex':   'jolitex/raw',
    'balboa':    'balboa/raw',
    'riomaster': 'riomaster/raw',
    'plastpet':  'plastpet/raw',
    'wiwu':      'wiwu/raw',
    'petiko':    'petiko/raw',
}


def amount(v):
    if isinstance(v, dict):
        return v.get('amount', 0) or 0
    return v or 0


def ler_receita(pasta_raw, prefixo):
    """{'2026-04': receita, ...} a partir dos arquivos <prefixo>_<ini>_a_<fim>.json
    (so considera arquivos cujo nome comeca direto com uma data, pra nao confundir
    vendas_mes_ com vendas_mes_origem_)."""
    out = {}
    for arq in glob.glob(f'{pasta_raw}/{prefixo}_[0-9]*.json'):
        m = re.search(r'_(\d{4}-\d{2})-\d{2}_a_', os.path.basename(arq))
        if not m:
            continue
        try:
            d = json.load(open(arq, encoding='utf-8'))
        except Exception as e:
            print(f'  [aviso] nao consegui ler {arq}: {e}')
            continue
        agg = d.get('salesAggregate') or []
        if not agg:
            continue
        out[m.group(1)] = amount(agg[0].get('shippedRevenue'))
    return out


def processar_conta(pasta_raw):
    fabricacao = ler_receita(pasta_raw, 'vendas_mes')
    origem = ler_receita(pasta_raw, 'vendas_mes_origem')
    comuns = sorted(set(fabricacao) & set(origem))[-MAX_MESES:]
    if not comuns:
        return None

    meses = [{'id': mid, 'fabricacao': fabricacao[mid], 'origem': origem[mid]} for mid in comuns]
    tot_fab = sum(m['fabricacao'] for m in meses)
    tot_ori = sum(m['origem'] for m in meses)
    outros = max(0.0, tot_fab - tot_ori)
    return {
        'meses': meses,
        'totais': {
            'fabricacao': tot_fab,
            'origem': tot_ori,
            'outrosDistribuidores': outros,
            'outrosDistribuidoresPct': (outros / tot_fab) if tot_fab else None,
        },
    }


def main():
    assert os.path.exists(ARQUIVO), (
        f'{ARQUIVO} nao encontrado na pasta atual -- rode o transformar_vendor.py primeiro, na mesma sessao.')
    with open(ARQUIVO, encoding='utf-8') as f:
        contas = json.load(f)

    for chave, pasta in CONTAS_CONFIG.items():
        if chave not in contas:
            continue
        bloco = processar_conta(os.path.join(BASE_DRIVE, pasta))
        if not bloco:
            contas[chave].pop('origemFabricacao', None)
            print(f'[{chave}] sem vendas_mes_origem_*.json (rode capturar_mensal.py) -- bloco removido')
            continue
        contas[chave]['origemFabricacao'] = bloco
        t = bloco['totais']
        print(f"[{chave}] {len(bloco['meses'])} meses | fabricacao R$ {t['fabricacao']:,.0f} | "
              f"origem R$ {t['origem']:,.0f} | outros distribuidores R$ {t['outrosDistribuidores']:,.0f} "
              f"({(t['outrosDistribuidoresPct'] or 0)*100:.1f}%)")

    with open(ARQUIVO, 'w', encoding='utf-8') as f:
        json.dump(contas, f, ensure_ascii=False, separators=(',', ':'))
    print(f'\nSalvo: {ARQUIVO} ({os.path.getsize(ARQUIVO):,} bytes)')


if __name__ == '__main__':
    main()
