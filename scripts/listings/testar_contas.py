"""Testa as credenciais das 11 contas (todas Vendor) usando SO as variaveis do ambiente.

Uso (da raiz do repo): python3 scripts/listings/testar_contas.py
Ignora qualquer .env local de proposito: o objetivo e validar o ambiente de nuvem "Default".
Para cada conta, troca o refresh token por um access token no LWA (nao baixa dados).
"""
import os, sys, json, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['IGNORAR_DOTENV'] = '1'
from contas import CONTAS  # noqa: E402

ok, falhas = [], []
for chave, c in CONTAS.items():
    suf = '_APP2' if c.get('app2') else ''
    nomes = [c['secret'], 'SP_API_LWA_CLIENT_ID' + suf, 'SP_API_LWA_CLIENT_SECRET' + suf]
    faltam = [n for n in nomes if not os.environ.get(n)]
    if faltam:
        print(f'X {chave:10s} faltando no ambiente: {", ".join(faltam)}'); falhas.append(chave); continue
    dados = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': os.environ[nomes[0]],
                                    'client_id': os.environ[nomes[1]], 'client_secret': os.environ[nomes[2]]}).encode()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request('https://api.amazon.com/auth/o2/token', data=dados), timeout=30).read())
        print(f'OK {chave:10s} {c["nome"]}' if r.get('access_token') else f'X {chave:10s} sem access_token')
        (ok if r.get('access_token') else falhas).append(chave)
    except Exception as e:
        corpo = getattr(e, 'read', lambda: b'')().decode()[:150]
        print(f'X {chave:10s} {c["nome"]}: {e} {corpo}'); falhas.append(chave)

print(f'\n{len(ok)}/{len(CONTAS)} contas OK' + (f' | com problema: {", ".join(falhas)}' if falhas else ''))
sys.exit(1 if falhas else 0)
