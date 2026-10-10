"""Diagnostico AO VIVO a partir do JSON gerado por buscar.py.

Uso: python3 scripts/listings/diagnosticar.py <atributos.json> <saida.json>
Aponta: titulo >=75, titulo/bullet em caixa alta, sem destaque, < 5 bullets,
termos proibidos, sem descricao e erros de listing. Pais de variacao nao exigem bullets/descricao.
"""
import sys, json, re
from collections import Counter

TERMOS = ['frete gratis', 'frete grátis', '100% garantido', 'melhor preco', 'melhor preço', 'oferta',
          'desconto', 'promocao', 'promoção', 'imperdivel', 'imperdível', 'mais vendido', 'numero 1',
          'número 1', 'aprovado por', 'cura', 'trata', 'previne doenca', 'previne doença', 'presentes de natal']


def caps(t):
    l = [c for c in t if c.isalpha()]
    return len(l) >= 6 and sum(c.isupper() for c in l) / len(l) > 0.7


def termo(t):
    t = (t or '').lower()
    return [x for x in TERMOS if re.search(r'\b' + re.escape(x) + r'\b', t)]


def main():
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    res = []
    for sku, v in d.items():
        if v.get('erro'):
            res.append({'sku': sku, 'problemas': ['ERRO_BUSCA']}); continue
        a, s = v.get('attributes', {}), v['summaries'][0]
        tit = (a.get('item_name') or [{}])[0].get('value', '')
        bul = [b.get('value', '') for b in a.get('bullet_point', [])]
        desc = next((a[k][0].get('value', '') for k in a if 'descri' in k and 'warranty' not in k and 'age_range' not in k), '')
        par = (a.get('parentage_level') or [{}])[0].get('value')
        p = []
        if len(tit) >= 75: p.append('TITULO_75+')
        if caps(tit): p.append('TITULO_CAIXA_ALTA')
        if not a.get('title_differentiation'): p.append('SEM_DESTAQUE')
        if par != 'parent' and len(bul) < 5: p.append(f'BULLETS_{len(bul)}')
        if any(caps(b) for b in bul): p.append('BULLET_CAIXA_ALTA')
        if termo(tit) or any(termo(b) for b in bul): p.append('TERMO_PROIBIDO_TIT_BUL')
        if termo(desc): p.append('TERMO_PROIBIDO_DESC')
        if par != 'parent' and not desc: p.append('SEM_DESCRICAO')
        if any(i.get('severity') == 'ERROR' for i in v.get('issues', [])): p.append('ERRO_LISTING')
        res.append({'sku': sku, 'asin': s.get('asin'), 'pt': s.get('productType'), 'parentage': par,
                    'titulo': tit, 'len': len(tit), 'n_bullets': len(bul), 'problemas': p})
    json.dump(res, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('total', len(res), '| sem problema', sum(1 for r in res if not r['problemas']))
    print(Counter(x for r in res for x in r['problemas']).most_common())


if __name__ == '__main__':
    main()
