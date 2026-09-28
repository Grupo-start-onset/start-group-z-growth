# Scripts de coleta de dados (Amazon SP-API) — sem Colab

Pipeline completa portada do Colab, adaptada para rodar aqui (chat/CLI
ou automação), sem depender do Google Drive nem do notebook.

## Arquivos

| Arquivo | Papel |
|---|---|
| `config.py` | Lê e valida os secrets (`.env` local ou Secrets do GitHub Actions) |
| `sp_api_auth.py` | Troca o refresh token por um access token da SP-API |
| `colab_shim.py` | Substitui `google.colab.drive`/`userdata` nos scripts originais |
| `test_conexao.py` | Valida secrets + autenticação, sem baixar dados |
| `capturar_mensal.py` | Vendas, estoque, tráfego, margem — meses fechados |
| `capturar_pedidos.py` | Sell-in (purchase orders) |
| `capturar_semanal.py` | Mês em andamento, por semanas fechadas |
| `capturar_previsao.py` | Previsão de demanda (Amazon) |
| `capturar_data_kiosk.py` | Oferta em destaque / Buy Box (Data Kiosk) |
| `capturar_brand_analytics.py` | Cesta de compras, termos de busca, recompra |
| `capturar_marcas.py` | Marca por ASIN (filtro "Marca" do dashboard) |
| `capturar_qualidade_listings.py` | Status/issues de listing por ASIN (opcional) |
| `capturar_tempo_real.py` | Vendas/tráfego/estoque por hora, últimas 72h |
| `transformar_vendor.py` | Gera `dados_vendor.json` consolidado |
| `transformar_semanas.py` | Acrescenta o bloco semanal |
| `transformar_brand.py` | Preenche extras de Brand Analytics |
| `transformar_destaque.py` | Bloco de oferta em destaque (Buy Box) |
| `publicar_github.py` | Publica no GitHub Pages deste repositório |

## O que mudou em relação ao Colab

- `google.colab.drive`/`userdata` → `colab_shim.py` (mount vira no-op, `userdata.get` lê variável de ambiente).
- `BASE_DRIVE` (antes `/content/drive/MyDrive/START_Vendor_Analytics`) → pasta local `dados_raw/` na raiz deste repositório. Substitui o Google Drive como cache bruto da API; é commitado no git, então persiste entre sessões.
- `publicar_github.py` e a publicação de `capturar_tempo_real.py` não clonam mais o repositório com token embutido na URL — já rodam de dentro do próprio checkout, só fazem `git pull`/`add`/`commit`/`push`.
- Os arquivos finais (`dados_vendor.json`, `dados/*.json`, `tempo_real/*.json`) são escritos direto na raiz do repositório, não mais copiados de `/content/`.

## Configuração dos secrets

Veja `.env.example` na raiz do repo para a lista completa. Resumo:

```bash
pip install -r requirements.txt
cp .env.example .env      # preencha com os valores reais
python scripts/test_conexao.py
```

## Como rodar a atualização de rotina

Forma recomendada — roda tudo, sempre na ordem certa, e publica no final:

```bash
python scripts/rodar_tudo.py
```

Também aceita `--sem-captura` (só transforma + publica, usa o que já está em
`dados_raw/`) e `--sem-publicar` (roda tudo, não publica).

**Atenção**: `transformar_vendor.py` reconstrói `dados_vendor.json` do zero a
partir de `dados_raw/`; `transformar_semanas.py`, `transformar_destaque.py` e
`transformar_brand.py` são complementos que *leem* esse arquivo e acrescentam
informação. Rodar `transformar_vendor.py` sozinho, sem rodar os três
complementos logo em seguida, apaga do arquivo publicado o que eles tinham
adicionado (mês em andamento por semana, oferta em destaque, extras de Brand
Analytics) — use sempre `rodar_tudo.py`, ou, se for rodar manualmente,
sempre na mesma ordem abaixo:

```bash
python scripts/capturar_mensal.py
python scripts/capturar_pedidos.py
python scripts/capturar_semanal.py
python scripts/capturar_previsao.py
python scripts/capturar_brand_analytics.py
python scripts/capturar_data_kiosk.py
python scripts/capturar_marcas.py
# opcional: python scripts/capturar_qualidade_listings.py
python scripts/transformar_vendor.py
python scripts/transformar_semanas.py
python scripts/transformar_brand.py
python scripts/transformar_destaque.py
python scripts/publicar_github.py

# tempo real, independente, cadência própria
python scripts/capturar_tempo_real.py
```

Cada script mantém seu próprio cache (arquivo já baixado = pula), então
rodar de novo é seguro — só busca o que falta ou está desatualizado.
