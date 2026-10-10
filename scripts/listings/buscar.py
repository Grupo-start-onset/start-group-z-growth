"""Busca atributos AO VIVO de listings, com retomada.

Uso (da raiz do repo):
  python3 scripts/listings/buscar.py <conta> <saida.json> [--skus arquivo.txt]
Sem --skus, usa todos os SKUs de dados_raw/<pasta>/raw/diagnostico_listing.json.
Grava a cada 20 itens (escrita atomica) e pula o que ja foi buscado; rode de novo ate 'FIM'.
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contas import listings_api, CONTAS, MARKETPLACE_ID

PASTA = {'petclean': 'petclean', 'new_pet': 'new_pet'}


def main():
    conta, saida = sys.argv[1], sys.argv[2]
    if '--skus' in sys.argv:
        skus = [l.strip() for l in open(sys.argv[sys.argv.index('--skus') + 1], encoding='utf-8') if l.strip()]
    else:
        diag = json.load(open(f'dados_raw/{PASTA.get(conta, conta)}/raw/diagnostico_listing.json', encoding='utf-8'))
        skus = [x['sku'] for x in diag]
    api = listings_api(conta)
    out = {}
    if os.path.exists(saida):
        try:
            out = json.load(open(saida, encoding='utf-8'))
        except json.JSONDecodeError:
            out = {}

    def salvar():
        json.dump(out, open(saida + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(saida + '.tmp', saida)

    print(f'total {len(skus)} | ja {len(out)}', flush=True)
    t0 = time.time()
    limite = 95 if '--curto' in sys.argv else 10 ** 9
    for i, s in enumerate(skus):
        if s in out and not out[s].get('erro'):
            continue
        if time.time() - t0 > limite:
            salvar(); print('pausa', flush=True); return
        for t in range(5):
            try:
                out[s] = api.get_listings_item(CONTAS[conta]['id'], s, marketplaceIds=[MARKETPLACE_ID],
                                               includedData=['attributes', 'summaries', 'issues']).payload
                break
            except Exception:
                time.sleep(3 * (t + 1))
        else:
            out[s] = {'erro': True}
        if i % 20 == 0:
            salvar(); print(i, len(out), flush=True)
        time.sleep(0.2)
    salvar()
    print('FIM', len(out), flush=True)


if __name__ == '__main__':
    main()
