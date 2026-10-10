"""Contas Amazon do Grupo START. TODAS sao Vendor (Vendor Central).
O parametro da SP-API se chama sellerId, mas e o codigo da conta Vendor."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
from colab_shim import userdata  # noqa: E402

MARKETPLACE_ID = 'A2Q3Y263D00KWC'

CONTAS = {
    'alfa_jf':   {'nome': 'ALFA JF',            'id': '76I78', 'secret': 'SP_API_REFRESH_TOKEN_ALFAJF'},
    'blidshop':  {'nome': 'Blid Shop',          'id': 'UM8O1', 'secret': 'SP_API_REFRESH_TOKEN_BLIDSHOP'},
    'petclean':  {'nome': 'Petclean BR',        'id': 'A470C', 'secret': 'SP_API_REFRESH_TOKEN_PETCLEAN'},
    'ozitp':     {'nome': 'OZITP',              'id': 'OZITV', 'secret': 'SP_API_REFRESH_TOKEN_OZITP'},
    'jolitex':   {'nome': 'Jolitex',            'id': 'R88OM', 'secret': 'SP_API_REFRESH_TOKEN_JOLITEX'},
    'balboa':    {'nome': 'Balboa',             'id': '6R8TT', 'secret': 'SP_API_REFRESH_TOKEN_BALBOA'},
    'riomaster': {'nome': 'Rio Master',         'id': 'RD8QP', 'secret': 'SP_API_REFRESH_TOKEN_RIOMASTER'},
    'plastpet':  {'nome': 'Pet Factory Brazil', 'id': 'SY933', 'secret': 'SP_API_REFRESH_TOKEN_PLASTPET'},
    'wiwu':      {'nome': 'WIWU',               'id': '4E8ND', 'secret': 'SP_API_REFRESH_TOKEN_WIWU'},
    'petiko':    {'nome': 'Petiko',             'id': 'YM9CK', 'secret': 'SP_API_REFRESH_TOKEN_PETIKO'},
    'new_pet':   {'nome': 'New Pet',            'id': '8E8RI', 'secret': 'SP_API_REFRESH_TOKEN_NEWPET', 'app2': True},
}


def credenciais(chave):
    c = CONTAS[chave]
    sufixo = '_APP2' if c.get('app2') else ''
    return dict(refresh_token=userdata.get(c['secret']),
                lwa_app_id=userdata.get('SP_API_LWA_CLIENT_ID' + sufixo),
                lwa_client_secret=userdata.get('SP_API_LWA_CLIENT_SECRET' + sufixo))


def listings_api(chave):
    from sp_api.api import ListingsItems
    from sp_api.base import Marketplaces
    return ListingsItems(credentials=credenciais(chave), marketplace=Marketplaces.BR)


def definitions_api(chave):
    from sp_api.api import ProductTypeDefinitions
    from sp_api.base import Marketplaces
    return ProductTypeDefinitions(credentials=credenciais(chave), marketplace=Marketplaces.BR)
