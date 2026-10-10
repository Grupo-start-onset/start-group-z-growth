# Grupo START — gestão de catálogo Amazon (Vendor)

Este repositório é o "projeto" do Grupo START: dashboard de vendas (GitHub Pages), coleta
de dados da SP-API e a gestão de conteúdo/catálogo dos listings na Amazon Brasil.
Toda sessão nova começa daqui — leia este arquivo e o `PENDENCIAS.md` antes de agir.

## Contas — TODAS são Vendor

**Todas as contas são Vendor (Vendor Central). Nunca falar em "Seller Central" nem em
"Suporte ao Parceiro de Vendas" ao orientar o usuário ou redigir chamados.**
A SP-API chama o identificador de `sellerId`/`seller_id` mesmo para Vendor — isso é só o
nome do parâmetro, não muda o tipo de conta.

| Chave | Conta / marcas | ID (sellerId da API) | Secret do refresh token |
|---|---|---|---|
| `alfa_jf` | ALFA JF | 76I78 | SP_API_REFRESH_TOKEN_ALFAJF |
| `blidshop` | Blid Shop | UM8O1 | SP_API_REFRESH_TOKEN_BLIDSHOP |
| `petclean` | Petclean BR (Pet Clean) | A470C | SP_API_REFRESH_TOKEN_PETCLEAN |
| `ozitp` | OZITP (KastKing, Mar Negro Fishing) | OZITV | SP_API_REFRESH_TOKEN_OZITP |
| `jolitex` | Jolitex (MEK) | R88OM | SP_API_REFRESH_TOKEN_JOLITEX |
| `balboa` | Balboa (Ligga Sports) | 6R8TT | SP_API_REFRESH_TOKEN_BALBOA |
| `riomaster` | Rio Master | RD8QP | SP_API_REFRESH_TOKEN_RIOMASTER |
| `plastpet` | Pet Factory Brazil | SY933 | SP_API_REFRESH_TOKEN_PLASTPET |
| `wiwu` | WIWU | 4E8ND | SP_API_REFRESH_TOKEN_WIWU |
| `petiko` | Petiko | YM9CK | SP_API_REFRESH_TOKEN_PETIKO |
| `new_pet` | New Pet | 8E8RI | SP_API_REFRESH_TOKEN_NEWPET (**app2**) |

- Credenciais LWA: `SP_API_LWA_CLIENT_ID` / `SP_API_LWA_CLIENT_SECRET`. A New Pet usa o
  segundo app: `SP_API_LWA_CLIENT_ID_APP2` / `SP_API_LWA_CLIENT_SECRET_APP2`.
- Marketplace BR: `A2Q3Y263D00KWC`.
- A mesma tabela está em `scripts/listings/contas.py` — use-a nos scripts.

### Credenciais (variáveis de ambiente)

As credenciais vêm das **variáveis do ambiente de nuvem "Default"** (menu do ambiente →
Editar). Um `.env` local só existe se alguém o criou naquele container — não confie nele.
Variáveis necessárias: `SP_API_LWA_CLIENT_ID`, `SP_API_LWA_CLIENT_SECRET`,
`SP_API_LWA_CLIENT_ID_APP2`, `SP_API_LWA_CLIENT_SECRET_APP2`, `SP_API_MARKETPLACE_ID`,
`SP_API_REGION` e um `SP_API_REFRESH_TOKEN_<CONTA>` por conta da tabela acima
(ALFAJF, BLIDSHOP, PETCLEAN, OZITP, JOLITEX, BALBOA, RIOMASTER, PLASTPET, WIWU, PETIKO, NEWPET).

**Se faltar a credencial de uma conta:** pare e avise o usuário qual variável falta e que ela
deve ser adicionada no ambiente "Default" (nunca pedir para colar o valor no chat). **Não
improvisar** consultando com outra conta: o resultado não representa o cadastro da conta pedida.

## Como rodar scripts

- **Sempre a partir da raiz do repositório** (`cd <raiz> && python3 scripts/...`). Os
  secrets são lidos via `scripts/colab_shim.py` (`userdata.get`) e falham se o cwd for outro.
- O comando em primeiro plano tem limite de ~110 s. Todo script que percorre muitos itens
  deve **gravar progresso incremental** (log/JSON com escrita atômica: `.tmp` + `os.replace`)
  e **retomar pulando o que já foi feito**. Para lotes grandes, rode em segundo plano com
  um wrapper que relança até aparecer `FIM` no log.
- Ferramentas genéricas prontas em `scripts/listings/` (ver `scripts/listings/README.md`):
  buscar atributos ao vivo, diagnosticar e aplicar patches com preview e retomada.
- Erro intermitente `invalid_client` (401) da SP-API no container é transitório: só repetir.

## Regras de conteúdo (títulos, destaque, bullets)

- **Título < 75 caracteres + Destaque do Produto** (`title_differentiation`). O Destaque só
  aparece se `item_name` tiver menos de 75 caracteres (a Amazon valida isso no PATCH).
  O que sair do título (benefícios, cor removida etc.) vai para o Destaque (máx. 125).
- **Nunca confiar em diagnóstico salvo** (`dados_raw/*/raw/diagnostico_listing.json` pode
  estar dias atrasado). Sempre refazer o diagnóstico com atributos **ao vivo** antes de
  corrigir — na Jolitex, 81% do que o arquivo apontava já estava resolvido.
- **Não inventar dados.** Medida, altura, diâmetro, galhos etc. só de fonte confiável
  (catálogo do fornecedor, site oficial, cadastro). Divergência entre fontes = reportar,
  não escolher. Valores impossíveis (ex.: toalha "1,40m x 210m") = erro de digitação da
  fonte, deixar de fora e reportar.
- **Conversão para medidas brasileiras de verdade**: jardas→metros, libras→kg, com vírgula
  decimal ("9,1 kg / 137 m") — não apenas traduzir a palavra da unidade.
- Atributos idênticos em produtos claramente diferentes (peso, compartimentos, cor) costumam
  ser cópia de cadastro: não propagar; conferir com título/model_name e corrigir ou reportar.
- Ao copiar categoria de um item "irmão", **verificar o nome da categoria no schema** — o
  irmão pode já estar errado (caso Pet Clean: eliminadores de odor em "Peitorais").
- Termos proibidos em título/bullets/descrição (ex.: "oferta", "frete grátis",
  "Presentes de Natal") bloqueiam qualquer PATCH no anúncio até serem removidos.

## Armadilhas da SP-API (Listings Items)

- Incluir `package_level = unit` nos patches (vários productTypes exigem).
- `VALIDATION_PREVIEW` não "enxerga" patches anteriores: um destaque testado em requisição
  separada do título dá falso INVALID ("nome com 75 caracteres ou menos"). Ou ignore, ou
  mande título + destaque **na mesma requisição**.
- **Categoria travada (erro 101168)**: não dá para mudar `product_category`/
  `product_subcategory` de alguns ASINs. Às vezes basta trocar só o `productType` no body
  (sem tocar na categoria); se não, só o suporte do Vendor Central resolve.
- Erro 101158 (valor inválido de categoria/nó): pegue os valores válidos no schema do
  productType (`get_definitions_product_type` → `properties.<attr>...anyOf[].enum` +
  `enumNames`). Nunca copie o código de categoria de outro produto sem conferir.
- productType genérico `PRODUCT` recusa alterações ("erro interno"): enviar com o
  productType correto (SHIRT, SWEATSHIRT…).
- `list_price` antigo sem `value_with_tax` trava o PATCH: reenviar o mesmo valor como
  `value_with_tax`.
- Variações: pai criado com PUT (`requirements: LISTING`, `parentage_level=parent`,
  `variation_theme`), filhos via PATCH (`parentage_level=child`,
  `child_parent_sku_relationship`, atributo do tema). Temas válidos no schema
  (`variation_theme...enum`, não o `enumDeprecated`).

## Chamados ao suporte (Vendor Central)

- Canal: **Vendor Central** (nunca Seller Central). Identificar a conta pelo nome e código
  de fornecedor.
- Padrão: saudação ("Prezados,"), contexto curto, **um pedido por chamado**, lista de ASINs
  com nome do produto, fechamento ("Atenciosamente, <conta>").
- Linguagem simples: **sem jargão interno** (API, código de erro, ID de categoria/nó,
  nome de productType) e sem perguntas que só nós saberíamos responder.
- Antes de redigir, reler os chamados anteriores da mesma conta (`docs/chamados/`).

## Comunicação com o usuário

- Responder em português, direto e sem jargão.
- Antes de aplicar em massa: diagnóstico ao vivo → preview em amostra (1+ por productType)
  → aplicação com retomada → verificação ao vivo de amostra. Reportar números finais
  (aceitos/recusados) e o que ficou de fora e por quê.
- Pendências abertas e histórico de lotes aplicados: `PENDENCIAS.md`.
