# ==================================================================
# CAPTURA: Marca de cada produto (Listings Items API), EM LOTE
# Roda no Colab. Descobre a MARCA cadastrada na Amazon de cada ASIN
# e grava em <conta>/raw/catalogo.json (campo "marca"), que o
# transformar_vendor.py ja le. E o que alimenta o filtro "Marca" do
# dashboard (contas com 2 ou mais marcas, como OZITP e Pet Clean).
#
# Por que este script existe: a Catalog Items API (get_catalog_item)
# devolve brand = None para estas contas, entao o campo "marca" do
# catalogo.json ficou vazio em todos os ASINs. O atributo "brand" da
# Listings Items API (attributes.brand[0].value) e o cadastro do
# proprio produto.
#
# Como funciona:
#   1) Junta os ASINs da conta (catalogo, listings, vendas, estoque e
#      pedidos ja capturados em <conta>/raw/).
#   2) Marca que ja esta salva (marcas.json) ou que ja veio no
#      listings_attributes.json (captura de atributos que voce ja tem)
#      NAO gasta chamada de API.
#   3) So o que falta vai para a API, EM LOTE: search_listings_items
#      com ate TAMANHO_LOTE ASINs por chamada (padrao de 25/09/2026).
#   4) Grava marcas.json (cache) e atualiza "marca" no catalogo.json.
#      Nao mexe em nome, imagem nem BSR de quem ja esta no catalogo;
#      ASIN que ainda nao esta no catalogo entra so com a marca (e o
#      nome do anuncio, quando a API traz).
#
# Cache: roda de novo sem problema; so busca o que falta. ASIN que a
# API nao devolveu (sem anuncio ativo na conta) fica com "erro" e e
# tentado de novo na proxima rodada. Produto que existe mas nao tem
# marca cadastrada fica registrado e nao e refeito (apague marcas.json
# da conta para refazer tudo).
#
# Rodar DEPOIS de capturar_mensal/pedidos (para ter a lista de ASINs)
# e ANTES do transformar_vendor.py.
#
# Salva em: START_Vendor_Analytics/<conta>/raw/marcas.json
# Formato: { "<asin>": {"marca": "KastKing"|null, "nome":..., "fonte":...,
#                       "erro": ...(opcional)} }
# ==================================================================

import os, json, glob, time
from collections import Counter
from colab_shim import drive, userdata

try:
    from sp_api.api import ListingsItems
    from sp_api.base import Marketplaces
except ImportError:
    os.system("pip install python-amazon-sp-api -q")
    from sp_api.api import ListingsItems
    from sp_api.base import Marketplaces

drive.mount('/content/drive', force_remount=True)

BASE_DRIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dados_raw'))

CONTAS_CONFIG = {
    'alfa_jf':   {'pasta': 'alfa_jf/raw',    'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'pasta': 'blidshop/raw',   'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'conta3':    {'pasta': 'petclean/raw',   'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'pasta': 'ozitp/raw',      'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'pasta': 'jolitex/raw',    'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'pasta': 'balboa/raw',     'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'pasta': 'riomaster/raw',  'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
}

SELLER_IDS = {
    'alfa_jf':   '76I78',
    'blidshop':  'UM8O1',
    'conta3':    'A470C',   # Petclean BR
    'ozitp':     'OZITV',
    'jolitex':   'R88OM',
    'balboa':    '6R8TT',
    'riomaster': 'RD8QP',
}

# None = todas as contas. Para testar so uma: CONTAS_ALVO = ['ozitp']
CONTAS_ALVO = None

LWA_CLIENT_ID = userdata.get('SP_API_LWA_CLIENT_ID')
LWA_CLIENT_SECRET = userdata.get('SP_API_LWA_CLIENT_SECRET')
MARKETPLACE = Marketplaces.BR

TAMANHO_LOTE = 20       # ASINs por chamada (maximo da API)
INTERVALO = 1.0         # pausa entre CHAMADAS (nao entre ASINs)
MAX_TENTATIVAS = 5


def ler_json(caminho, padrao):
    if os.path.exists(caminho):
        try:
            return json.load(open(caminho, encoding='utf-8'))
        except Exception:
            pass
    return padrao


def salvar_json(caminho, dados):
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def marca_dos_atributos(attrs, marketplace_id):
    """attributes.brand = [{"value": "KastKing", "marketplace_id": "A2Q3Y263D00KWC", ...}]"""
    lista = (attrs or {}).get('brand') or []
    valores = [x for x in lista if isinstance(x, dict) and x.get('value')]
    if not valores:
        return None
    do_mercado = [x for x in valores if x.get('marketplace_id') == marketplace_id]
    marca = str((do_mercado or valores)[0]['value']).strip()
    return marca or None


def marca_do_item(item, marketplace_id):
    """Marca de um item da search_listings_items: atributo brand; se nao houver, summaries."""
    marca = marca_dos_atributos(item.get('attributes'), marketplace_id)
    if marca:
        return marca
    resumo = (item.get('summaries') or [{}])[0]
    for campo in ('brand', 'brandName'):
        if resumo.get(campo):
            return str(resumo[campo]).strip() or None
    return None


def asins_da_conta(pasta_raw):
    """Todos os ASINs conhecidos da conta nos arquivos ja capturados."""
    asins = set()
    for nome in ('catalogo.json', 'qualidade_listings.json', 'listings_attributes.json', 'marcas.json'):
        d = ler_json(f'{pasta_raw}/{nome}', {})
        if isinstance(d, dict):
            asins.update(d.keys())
    lista = ler_json(f'{pasta_raw}/asins_catalogo_completo.json', [])
    if isinstance(lista, list):
        asins.update(a for a in lista if isinstance(a, str))
    for arq in glob.glob(f'{pasta_raw}/vendas_mes_*.json'):
        for r in (ler_json(arq, {}) or {}).get('salesByAsin', []):
            asins.add(r.get('asin'))
    for arq in glob.glob(f'{pasta_raw}/estoque_mes_*.json'):
        for r in (ler_json(arq, {}) or {}).get('inventoryByAsin', []):
            asins.add(r.get('asin'))
    for arq in glob.glob(f'{pasta_raw}/status_pedidos_*.json'):
        pos = ler_json(arq, [])
        for po in (pos if isinstance(pos, list) else []):
            for it in po.get('itemStatus') or []:
                asins.add(it.get('buyerProductIdentifier'))
    return sorted(a for a in asins if isinstance(a, str) and len(a) == 10)   # ASIN tem 10 caracteres


def em_lotes(lista, tamanho):
    for i in range(0, len(lista), tamanho):
        yield lista[i:i + tamanho]


def buscar_lote_com_retry(api, seller_id, lote):
    identifiers_str = ",".join(lote)  # a API espera string separada por virgula, nao lista
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            return api.search_listings_items(
                sellerId=seller_id,
                marketplaceIds=[MARKETPLACE.marketplace_id],
                identifiers=identifiers_str,
                identifiersType="ASIN",
                pageSize=len(lote),
                includedData=["summaries", "attributes"],
            )
        except AttributeError:
            raise RuntimeError(
                "search_listings_items nao existe nesta versao da lib. "
                "Rode: !pip install --upgrade python-amazon-sp-api -q  e reinicie o runtime."
            )
        except Exception as e:
            texto_erro = str(e)
            if "QuotaExceeded" in texto_erro or "429" in texto_erro:
                espera = 2 ** tentativa
                print(f"    [cota excedida] aguardando {espera}s (tentativa {tentativa}/{MAX_TENTATIVAS})...")
                time.sleep(espera)
                continue
            raise
    raise RuntimeError("Numero maximo de tentativas excedido em search_listings_items")


def capturar_conta(chave, cfg):
    pasta_raw = os.path.join(BASE_DRIVE, cfg['pasta'])
    if not os.path.isdir(pasta_raw):
        print(f'\n[aviso] pasta nao encontrada para "{chave}": {pasta_raw} -- pulando')
        return

    print(f'\n=== {chave} ===')
    asins = asins_da_conta(pasta_raw)
    if not asins:
        print('  nenhum ASIN encontrado -- pulando')
        return
    print(f'  {len(asins)} ASINs conhecidos da conta')

    caminho_marcas = f'{pasta_raw}/marcas.json'
    marcas = ler_json(caminho_marcas, {})
    if not isinstance(marcas, dict):
        marcas = {}

    # 1) o que ja esta resolvido sem API: cache anterior e listings_attributes.json
    do_cache = sum(1 for a in asins if a in marcas and not marcas[a].get('erro'))
    listings_attrs = ler_json(f'{pasta_raw}/listings_attributes.json', {})
    aproveitados = 0
    if isinstance(listings_attrs, dict):
        for a in asins:
            if a in marcas and not marcas[a].get('erro'):
                continue
            marca = marca_dos_atributos((listings_attrs.get(a) or {}).get('attributes'), MARKETPLACE.marketplace_id)
            if marca:
                marcas[a] = {'marca': marca, 'nome': None, 'fonte': 'listings_attributes'}
                aproveitados += 1
    print(f'  {do_cache} ja em cache, {aproveitados} aproveitados do listings_attributes.json (sem chamada de API)')

    # 2) o que falta vai para a API, em lote
    faltando = [a for a in asins if a not in marcas or marcas[a].get('erro')]
    ok, sem_resultado, erros = 0, 0, 0
    amostra_sem_marca = None
    if faltando:
        seller_id = SELLER_IDS.get(chave)
        if not seller_id:
            print(f'  [aviso] SELLER_ID nao preenchido para "{chave}" -- {len(faltando)} ASINs ficam sem consulta')
        else:
            credentials = dict(
                refresh_token=userdata.get(cfg['secret']),
                lwa_app_id=LWA_CLIENT_ID,
                lwa_client_secret=LWA_CLIENT_SECRET,
            )
            api = ListingsItems(credentials=credentials, marketplace=MARKETPLACE)
            lotes = list(em_lotes(faltando, TAMANHO_LOTE))
            print(f'  {len(faltando)} a buscar agora, em {len(lotes)} lotes de ate {TAMANHO_LOTE}')
            for i, lote in enumerate(lotes, 1):
                try:
                    resp = buscar_lote_com_retry(api, seller_id, lote)
                    items = (resp.payload or {}).get("items", [])
                    encontrados = set()
                    for item in items:
                        resumo = (item.get("summaries") or [{}])[0]
                        asin_item = resumo.get("asin")
                        if not asin_item:
                            continue
                        encontrados.add(asin_item)
                        marca = marca_do_item(item, MARKETPLACE.marketplace_id)
                        marcas[asin_item] = {'marca': marca, 'nome': resumo.get('itemName'), 'fonte': 'api'}
                        if marca:
                            ok += 1
                        elif amostra_sem_marca is None:
                            amostra_sem_marca = (asin_item, sorted((item.get('attributes') or {}).keys())[:20])
                    for asin_faltante in set(lote) - encontrados:   # sem anuncio da conta / nao devolvido
                        marcas[asin_faltante] = {'marca': None, 'nome': None, 'fonte': 'api', 'erro': 'sem resultado no lote'}
                        sem_resultado += 1
                except RuntimeError as e:
                    print(f'  [ERRO FATAL] {e}')
                    break
                except Exception as e:
                    for asin_erro in lote:
                        marcas[asin_erro] = {'marca': None, 'nome': None, 'fonte': 'api', 'erro': str(e)[:200]}
                    erros += len(lote)
                    print(f'  [erro no lote {i}] {str(e)[:80]}')
                if i % 5 == 0 or i == len(lotes):
                    print(f'  [lote {i}/{len(lotes)}] com marca={ok} sem resultado={sem_resultado} erros={erros}')
                    salvar_json(caminho_marcas, marcas)
                time.sleep(INTERVALO)
    salvar_json(caminho_marcas, marcas)

    # 3) grava a marca no catalogo.json (nao mexe em nome/imagem/BSR de quem ja esta la)
    caminho_catalogo = f'{pasta_raw}/catalogo.json'
    catalogo = ler_json(caminho_catalogo, {})
    if not isinstance(catalogo, dict):
        catalogo = {}
    novos, atualizados = 0, 0
    for a in asins:
        m = marcas.get(a) or {}
        marca = m.get('marca')
        if not marca:
            continue
        item = catalogo.get(a)
        if item is None:
            catalogo[a] = {'nome': m.get('nome'), 'marca': marca, 'imagem': None, 'bsr': []}
            novos += 1
        else:
            if item.get('marca') != marca:
                item['marca'] = marca
                atualizados += 1
            if not item.get('nome') and m.get('nome'):
                item['nome'] = m['nome']
    if novos or atualizados:
        salvar_json(caminho_catalogo, catalogo)

    # 4) resumo
    contagem = Counter((marcas.get(a) or {}).get('marca') for a in asins)
    sem_marca = contagem.pop(None, 0)
    print(f'  catalogo.json: {atualizados} marcas gravadas em produtos existentes, {novos} produtos novos com marca')
    print(f'  marcas encontradas ({len(contagem)}): ' + (', '.join(f'{m} ({n})' for m, n in contagem.most_common(12)) or '(nenhuma)'))
    print(f'  ASINs sem marca: {sem_marca} de {len(asins)}')
    if amostra_sem_marca:
        print(f'  [diagnostico] o produto {amostra_sem_marca[0]} veio da API sem marca. Atributos disponiveis: {amostra_sem_marca[1]}')
        print('               (se "brand" nao aparece, me mande esta linha)')


def main():
    for chave, cfg in CONTAS_CONFIG.items():
        if CONTAS_ALVO and chave not in CONTAS_ALVO:
            continue
        capturar_conta(chave, cfg)
    print('\n\nConcluido. Rode o transformar_vendor.py (ou o rodar_tudo) e publique: o filtro "Marca" '
          'aparece nas contas com 2 ou mais marcas.')


if __name__ == '__main__':
    main()
