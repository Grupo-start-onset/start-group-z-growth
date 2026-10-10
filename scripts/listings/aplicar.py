"""Aplica patches de um plano JSON, com preview, retomada e log.

Plano: lista de {"sku": ..., "pt": <productType>, "patches": [<patch SP-API>, ...]}
  - package_level=unit e incluido automaticamente se nao estiver no plano.
  - Para titulo + destaque, coloque os dois no MESMO item (mesma requisicao).
Uso (da raiz do repo):
  python3 scripts/listings/aplicar.py <conta> <plano.json> --preview [--curto] [SKU ...]
  python3 scripts/listings/aplicar.py <conta> <plano.json> [--curto]
Log: <plano>.<preview|apply>.log.jsonl  — itens ACCEPTED/VALID/INVALID sao pulados ao reiniciar.
Para lotes grandes rode em segundo plano com um wrapper que repete ate a ultima linha ser 'FIM'.
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contas import listings_api, CONTAS, MARKETPLACE_ID


def main():
    conta, plano_path = sys.argv[1], sys.argv[2]
    preview = '--preview' in sys.argv
    limite = 95 if '--curto' in sys.argv else 10 ** 9
    only = [a for a in sys.argv[3:] if not a.startswith('--')]
    log_path = f'{plano_path}.{"preview" if preview else "apply"}.log.jsonl'
    api = listings_api(conta)
    plano = json.load(open(plano_path, encoding='utf-8'))
    if only:
        plano = [p for p in plano if p['sku'] in only]
    feito = set()
    if os.path.exists(log_path) and not only:
        for l in open(log_path, encoding='utf-8'):
            x = json.loads(l)
            if x['status'] in ('ACCEPTED', 'VALID', 'INVALID'):
                feito.add(x['sku'])
    kw = {'mode': 'VALIDATION_PREVIEW'} if preview else {}
    print(f'total {len(plano)} | ja feitos {len(feito)} | preview={preview}', flush=True)
    t0 = time.time()
    with open(log_path, 'a', encoding='utf-8') as log:
        for p in plano:
            if p['sku'] in feito:
                continue
            if time.time() - t0 > limite:
                print('pausa', flush=True); return
            patches = list(p['patches'])
            if not any(x['path'].endswith('/package_level') for x in patches):
                patches.append({'op': 'replace', 'path': '/attributes/package_level',
                                'value': [{'value': 'unit', 'marketplace_id': MARKETPLACE_ID}]})
            st, iss = 'ERRO', []
            for t in range(5):
                try:
                    r = api.patch_listings_item(CONTAS[conta]['id'], p['sku'], marketplaceIds=[MARKETPLACE_ID],
                                                body={'productType': p['pt'], 'patches': patches},
                                                issueLocale='pt_BR', **kw).payload or {}
                    st, iss = r.get('status', '?'), r.get('issues', [])
                    break
                except Exception as e:
                    iss = [{'message': str(e)[:300]}]
                    time.sleep(3 * (t + 1))
            if st not in ('ACCEPTED', 'VALID'):
                print(st, p['sku'], [i['message'][:200] for i in iss if i.get('severity') == 'ERROR'][:2], flush=True)
            log.write(json.dumps({'sku': p['sku'], 'pt': p['pt'], 'status': st, 'issues': iss}, ensure_ascii=False) + '\n')
            log.flush()
            time.sleep(0.3)
    print('FIM', flush=True)


if __name__ == '__main__':
    main()
