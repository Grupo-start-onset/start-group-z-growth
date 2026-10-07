# ==================================================================
# diagnosticar_listing.py
# Primeira etapa do agente de qualidade de conteudo (skill
# listing-optimizer): aponta violacoes OBJETIVAS de titulo/bullets/
# descricao -- sem reescrever nada, sem IA. So compara o listing atual
# contra o schema oficial da categoria (limite de caracteres, campos
# obrigatorios) e a lista de termos proibidos do skill.
#
# Uso:
#   python scripts/diagnosticar_listing.py jolitex                 # todo o catalogo da conta
#   python scripts/diagnosticar_listing.py jolitex B0F68K5MHC ...  # so os ASINs informados
# ==================================================================

import sys, os, json, time, re, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from colab_shim import userdata
from sp_api.api import ListingsItems, ProductTypeDefinitions
from sp_api.base import Marketplaces

MARKETPLACE_ID = 'A2Q3Y263D00KWC'

SELLER_IDS = {
    'alfa_jf':   '76I78',
    'blidshop':  'UM8O1',
    'conta3':    'A470C',
    'ozitp':     'OZITV',
    'jolitex':   'R88OM',
    'balboa':    '6R8TT',
    'riomaster': 'RD8QP',
    'plastpet':  'SY933',
    'wiwu':      '4E8ND',
    'petiko':    'YM9CK',
    'new_pet':   '8E8RI',
}
SECRETS = {
    'alfa_jf':   'SP_API_REFRESH_TOKEN_ALFAJF',
    'blidshop':  'SP_API_REFRESH_TOKEN_BLIDSHOP',
    'conta3':    'SP_API_REFRESH_TOKEN_PETCLEAN',
    'ozitp':     'SP_API_REFRESH_TOKEN_OZITP',
    'jolitex':   'SP_API_REFRESH_TOKEN_JOLITEX',
    'balboa':    'SP_API_REFRESH_TOKEN_BALBOA',
    'riomaster': 'SP_API_REFRESH_TOKEN_RIOMASTER',
    'plastpet':  'SP_API_REFRESH_TOKEN_PLASTPET',
    'wiwu':      'SP_API_REFRESH_TOKEN_WIWU',
    'petiko':    'SP_API_REFRESH_TOKEN_PETIKO',
    'new_pet':   'SP_API_REFRESH_TOKEN_NEWPET',
}
CONTAS_APP2 = {'new_pet'}  # usam o segundo app LWA (limite de 10 contas no app principal)

TERMOS_PROMOCIONAIS = [
    'frete gratis', 'frete grátis', '100% garantido', 'melhor preco',
    'melhor preço', 'oferta', 'desconto', 'promocao', 'promoção',
    'imperdivel', 'imperdível', 'mais vendido', 'numero 1', 'número 1',
    'aprovado por', 'cura', 'trata', 'previne doenca', 'previne doença',
]
CARACTERES_PROIBIDOS = ['!', '$', '?', '_', '{', '}', '^', '¬', '¦']


def get_api_clients(conta):
    secret = SECRETS[conta]
    if conta in CONTAS_APP2:
        lwa_app_id = userdata.get('SP_API_LWA_CLIENT_ID_APP2')
        lwa_client_secret = userdata.get('SP_API_LWA_CLIENT_SECRET_APP2')
    else:
        lwa_app_id = userdata.get('SP_API_LWA_CLIENT_ID')
        lwa_client_secret = userdata.get('SP_API_LWA_CLIENT_SECRET')
    creds = dict(
        refresh_token=userdata.get(secret),
        lwa_app_id=lwa_app_id,
        lwa_client_secret=lwa_client_secret,
    )
    return (
        ListingsItems(credentials=creds, marketplace=Marketplaces.BR),
        ProductTypeDefinitions(credentials=creds, marketplace=Marketplaces.BR),
    )


_schema_cache = {}


def get_schema_limits(api_pt, product_type):
    if product_type in _schema_cache:
        return _schema_cache[product_type]
    try:
        r = api_pt.get_definitions_product_type(
            productType=product_type, marketplaceIds=[MARKETPLACE_ID], requirements='LISTING'
        )
        url = r.payload['schema']['link']['resource']
        schema = json.loads(urllib.request.urlopen(url).read())
        props = schema.get('properties', {})

        titulo_max = (
            props.get('item_name', {}).get('items', {}).get('properties', {})
            .get('value', {}).get('maxLength')
        )
        bp = props.get('bullet_point', {})
        bullet_max_len = (
            bp.get('items', {}).get('properties', {}).get('value', {}).get('maxLength')
        )
        bullet_max_qtd = bp.get('maxUniqueItems')

        # varios product types tem mais de um campo com "descri" no nome
        # (ex.: SHAMPOO tem age_range_description, rtip_product_description,
        # short_product_description) -- prioriza o campo de descricao
        # principal do produto, nao um campo auxiliar tipo faixa etaria/garantia.
        candidatos_desc = [k for k in props if 'descri' in k.lower()]
        desc_key = (
            next((k for k in candidatos_desc if k == 'rtip_product_description'), None)
            or next((k for k in candidatos_desc if 'product_description' in k and 'age_range' not in k and 'warranty' not in k), None)
            or next((k for k in candidatos_desc if 'warranty' not in k and 'age_range' not in k), None)
            or (candidatos_desc[0] if candidatos_desc else None)
        )
        desc_max = None
        if desc_key:
            desc_max = (
                props[desc_key].get('items', {}).get('properties', {})
                .get('value', {}).get('maxLength')
            )

        limites = {
            'titulo_max': titulo_max or 200,
            'bullet_max_len': bullet_max_len or 700,
            'bullet_max_qtd': bullet_max_qtd or 5,
            'desc_key': desc_key,
            'desc_max': desc_max or 2000,
        }
    except Exception as e:
        print(f'  [aviso] nao consegui schema de {product_type}, usando limites padrao: {e}')
        limites = {'titulo_max': 200, 'bullet_max_len': 700, 'bullet_max_qtd': 5, 'desc_key': None, 'desc_max': 2000}
    _schema_cache[product_type] = limites
    return limites


def checar_caixa_alta(texto):
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 6:
        return False
    maiusculas = [c for c in letras if c.isupper()]
    return len(maiusculas) / len(letras) > 0.7


def checar_termo_proibido(texto):
    t = (texto or '').lower()
    encontrados = []
    for termo in TERMOS_PROMOCIONAIS:
        padrao = r'\b' + re.escape(termo) + r'\b'
        if re.search(padrao, t):
            encontrados.append(termo)
    return encontrados


def checar_caracteres_proibidos(texto):
    return [c for c in CARACTERES_PROIBIDOS if c in (texto or '')]


def diagnosticar_item(asin, sku, product_type, attrs, limites):
    problemas = []

    titulo_list = attrs.get('item_name', [])
    titulo = titulo_list[0]['value'] if titulo_list else ''
    if not titulo:
        problemas.append('SEM_TITULO')
    else:
        if len(titulo) > limites['titulo_max']:
            problemas.append(f"TITULO_ACIMA_DO_LIMITE ({len(titulo)}/{limites['titulo_max']})")
        if checar_caixa_alta(titulo):
            problemas.append('TITULO_CAIXA_ALTA')
        termos = checar_termo_proibido(titulo)
        if termos:
            problemas.append(f'TITULO_TERMO_PROIBIDO ({", ".join(termos)})')
        chars = checar_caracteres_proibidos(titulo)
        if chars:
            problemas.append(f'TITULO_CARACTERE_PROIBIDO ({", ".join(chars)})')

    bullets = attrs.get('bullet_point', [])
    if not bullets:
        problemas.append('SEM_BULLETS')
    else:
        if len(bullets) > limites['bullet_max_qtd']:
            problemas.append(f"BULLETS_ACIMA_DA_QTD ({len(bullets)}/{limites['bullet_max_qtd']})")
        for i, b in enumerate(bullets, 1):
            val = b.get('value', '')
            if not val.strip():
                problemas.append(f'BULLET_{i}_VAZIO')
                continue
            if len(val) > limites['bullet_max_len']:
                problemas.append(f"BULLET_{i}_ACIMA_DO_LIMITE ({len(val)}/{limites['bullet_max_len']})")
            if checar_caixa_alta(val):
                problemas.append(f'BULLET_{i}_CAIXA_ALTA')
            termos = checar_termo_proibido(val)
            if termos:
                problemas.append(f'BULLET_{i}_TERMO_PROIBIDO ({", ".join(termos)})')

    desc_key = limites.get('desc_key')
    desc_val = ''
    if desc_key and attrs.get(desc_key):
        desc_val = attrs[desc_key][0].get('value', '')
    if not desc_val:
        problemas.append('SEM_DESCRICAO')
    else:
        if len(desc_val) > limites['desc_max']:
            problemas.append(f"DESCRICAO_ACIMA_DO_LIMITE ({len(desc_val)}/{limites['desc_max']})")
        termos = checar_termo_proibido(desc_val)
        if termos:
            problemas.append(f'DESCRICAO_TERMO_PROIBIDO ({", ".join(termos)})')

    return {
        'asin': asin, 'sku': sku, 'productType': product_type,
        'titulo': titulo, 'qtd_bullets': len(bullets),
        'problemas': problemas,
    }


def main():
    if len(sys.argv) < 2:
        print('Uso: python diagnosticar_listing.py <conta> [asin1 asin2 ...]')
        sys.exit(1)

    conta = sys.argv[1]
    asins_pedidos = sys.argv[2:]

    if conta not in SELLER_IDS:
        print(f'Conta desconhecida: {conta}. Opcoes: {list(SELLER_IDS)}')
        sys.exit(1)

    seller_id = SELLER_IDS[conta]
    api_listings, api_pt = get_api_clients(conta)

    alvos = []
    if asins_pedidos:
        for asin in asins_pedidos:
            resp = api_listings.search_listings_items(
                sellerId=seller_id, marketplaceIds=[MARKETPLACE_ID],
                identifiers=asin, identifiersType='ASIN',
                includedData=['attributes', 'summaries'],
            )
            items = resp.payload.get('items', [])
            if items:
                alvos.append(items[0])
            time.sleep(0.3)
    else:
        # search_listings_items trunca em 1000 resultados mesmo com pageToken.
        # Workaround: pagina por lastUpdatedDate em rodadas, usando o cursor da
        # ultima pagina de cada rodada como ponto de partida da proxima, ate
        # juntar o numberOfResults total (mesma tecnica usada no catalogo
        # completo de Jolitex/Rio Master).
        vistos = {}
        cursor_after = None
        total_geral = None
        rodada = 0
        while True:
            rodada += 1
            page_token = None
            novos_na_rodada = 0
            while True:
                kwargs = dict(sellerId=seller_id, marketplaceIds=[MARKETPLACE_ID], pageSize=20,
                               includedData=['attributes', 'summaries'],
                               sortBy='lastUpdatedDate', sortOrder='ASC')
                if cursor_after:
                    kwargs['lastUpdatedAfter'] = cursor_after
                if page_token:
                    kwargs['pageToken'] = page_token
                resp = api_listings.search_listings_items(**kwargs)
                if total_geral is None:
                    total_geral = resp.payload.get('numberOfResults')
                for item in resp.payload.get('items', []):
                    s = item.get('summaries', [{}])[0]
                    asin = s.get('asin')
                    if not asin or asin in vistos:
                        continue
                    vistos[asin] = item
                    novos_na_rodada += 1
                page_token = getattr(resp, 'next_token', None)
                if not page_token:
                    break
                time.sleep(0.3)
            print(f'  rodada {rodada}: {novos_na_rodada} novos, total {len(vistos)} / esperado {total_geral}')
            if novos_na_rodada == 0 or (total_geral is not None and len(vistos) >= total_geral):
                break
            cursor_after = max(
                item.get('summaries', [{}])[0].get('lastUpdatedDate', '')
                for item in vistos.values()
            )
        alvos = list(vistos.values())

    print(f'Diagnosticando {len(alvos)} ASINs da conta {conta}...\n')

    relatorio = []
    for item in alvos:
        sku = item['sku']
        s = item.get('summaries', [{}])[0]
        asin = s.get('asin', '?')
        product_type = s.get('productType', '?')
        attrs = item.get('attributes', {})

        limites = get_schema_limits(api_pt, product_type)
        diag = diagnosticar_item(asin, sku, product_type, attrs, limites)
        relatorio.append(diag)
        if diag['problemas']:
            print(f"{asin} ({sku}) [{product_type}]: {diag['titulo'][:50]}")
            for p in diag['problemas']:
                print(f'   - {p}')

    com_problema = [r for r in relatorio if r['problemas']]
    print(f"\nResumo: {len(com_problema)}/{len(relatorio)} ASINs com pelo menos 1 problema de conteudo.")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dados_raw', conta, 'raw')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'diagnostico_listing.json')
    json.dump(relatorio, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Relatorio salvo em: {out}')


if __name__ == '__main__':
    main()
