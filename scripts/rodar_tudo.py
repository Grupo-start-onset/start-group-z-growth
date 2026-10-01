# ==================================================================
# rodar_tudo.py
# Roda a pipeline completa de atualizacao, sempre na ordem certa, e
# publica no final. Existe para evitar o erro de rodar so uma etapa
# (ex.: so pedidos) e esquecer os complementos -- transformar_vendor.py
# reconstroi dados_vendor.json do zero a partir do dados_raw/; quem
# acrescenta "mes em andamento por semana" (transformar_semanas.py),
# "oferta em destaque" (transformar_destaque.py) e os extras de Brand
# Analytics (transformar_brand.py) sao scripts separados que LEEM o
# arquivo ja gerado e adicionam informacao -- rodar so o
# transformar_vendor.py sem os tres de novo em seguida APAGA esses
# blocos do arquivo publicado (foi o que aconteceu em 28/09/2026).
#
# Uso:
#   python scripts/rodar_tudo.py                 # tudo, na ordem
#   python scripts/rodar_tudo.py --sem-captura    # so transforma + notifica + publica
#                                                  # (usa o que ja esta em dados_raw/)
#   python scripts/rodar_tudo.py --sem-notificar  # roda tudo, pula o email de pedido novo
#   python scripts/rodar_tudo.py --sem-publicar   # roda tudo, nao publica
# ==================================================================

import subprocess
import sys
import os

PASTA_SCRIPTS = os.path.dirname(os.path.abspath(__file__))

CAPTURA = [
    'capturar_mensal.py',
    'capturar_pedidos.py',
    'capturar_semanal.py',
    'capturar_previsao.py',
    'capturar_brand_analytics.py',
    'capturar_data_kiosk.py',
    'capturar_marcas.py',
]
TRANSFORMA = [
    'transformar_vendor.py',   # sempre primeiro dos transforma -- reconstroi do zero
    'transformar_semanas.py',  # complementos -- sempre depois do transformar_vendor.py
    'transformar_destaque.py',
    'transformar_brand.py',
]
# roda depois do transformar_vendor.py (precisa do bloco `pedidos` atualizado) e
# antes de publicar -- manda email quando aparece PO novo desde a ultima execucao.
NOTIFICA = ['notificar_pedidos.py']
PUBLICA = ['publicar_github.py']


def rodar(nome):
    caminho = os.path.join(PASTA_SCRIPTS, nome)
    print(f'\n{"=" * 60}\n=== {nome} ===\n{"=" * 60}')
    r = subprocess.run([sys.executable, caminho])
    if r.returncode != 0:
        print(f'\n[FALHOU] {nome} terminou com erro (codigo {r.returncode}). Parando aqui.')
        sys.exit(r.returncode)


def main():
    args = sys.argv[1:]
    etapas = []
    if '--sem-captura' not in args:
        etapas += CAPTURA
    etapas += TRANSFORMA
    if '--sem-notificar' not in args:
        etapas += NOTIFICA
    if '--sem-publicar' not in args:
        etapas += PUBLICA

    for nome in etapas:
        rodar(nome)

    print('\nConcluido -- todas as etapas rodaram, nesta ordem:')
    for nome in etapas:
        print(f'  - {nome}')


if __name__ == '__main__':
    main()
