# Pendências / próximas sessões

## 1. Skill especializado em otimização de conteúdo de listing (título/bullets/descrição)
Ideia do usuário (06/10/2026): em vez de reescrever título/bullets/descrição "no
bom senso", montar um skill dedicado com as regras oficiais da Amazon
documentadas, e usar esse skill como base pra qualquer correção de texto —
mais consistente e auditável do que confiar em reescrita genérica.

Passos sugeridos:
1. Reunir a documentação oficial da Amazon sobre título, bullet points,
   descrição, imagens e conteúdo proibido (Seller Central / Vendor Central
   Style Guide — por categoria, já que as regras de caracteres variam).
2. Criar um skill do projeto com essas regras como referência (parecido com
   o skill `dataviz` já usado nesta sessão).
3. Construir o processo de correção em cima desse skill.
4. Decidir junto, com base na qualidade observada: publica direto via API ou
   passa por uma revisão humana antes (lote semanal, por exemplo) — pelo menos
   na primeira leva, até confiarmos no padrão.

Motivação: diferente das correções de atributo (marca, imagem, categoria,
nível de pacote — todas com resposta ACCEPTED/INVALID clara da Amazon), texto
de marketing não tem essa validação binária. A Amazon aceita um título ruim
sem reclamar, então um processo 100% autônomo rodando todo dia sem revisão
corre risco de piorar listagens sem ninguém perceber (perda de SEO, texto
pior, possível violação de política só percebida depois via supressão).

## 2. JOLITEX — reclassificação de categoria (productType), itens restantes
Hoje (06/10/2026) reclassificamos 198 ASINs "HOME" (genérico) para categorias
específicas (VASE, BASKET, FOOD_STORAGE_CONTAINER, TRASH_CAN, TRAY,
BATHROOM_CONTAINER_SET, DISHWARE_PLATE, FURNITURE_CART, HANGING_ORNAMENT,
KNIFE_BLOCK_SET, FLATWARE, THERMOS, BUTTER_DISH, STORAGE_BOX, SHELF, CADDY,
DISPOSABLE_NAPKIN, BED_LINEN_SET, FITTED_SHEET) — 198/198 aceitos.

Ficaram de fora:
- **83 ASINs "HOME" sem padrão de nome reconhecível** — precisam de pesquisa
  individual de categoria (via `search_definitions_product_types`) e validação
  um a um. Lista completa nos dados do script `reclassificar_jolitex_lote2.py`
  (ver `sem_match` na análise), ou refazer a partir do catálogo completo
  (ver item abaixo).
- **~173 ASINs que não aparecem na busca paginada** — a conta tem 1.173 ASINs
  reais, mas `search_listings_items` só pagina até 1.000 resultados (limite da
  própria API da Amazon, não é bug nosso). Pra alcançar os ~173 restantes,
  precisa de outro caminho: relatório de inventário via Reports API (ex:
  GET_MERCHANT_LISTINGS_ALL_DATA ou similar), que não tem esse teto de 1.000.

Mecanismo de reclassificação já validado e funcionando (reaproveitar):
- `GET /listings/2021-08-01/items/{sellerId}/{sku}` (via `search_listings_items`
  com `includedData=['attributes']`) pra pegar os atributos atuais.
- `PUT /listings/2021-08-01/items/{sellerId}/{sku}` (`put_listings_item`) com
  `productType` novo + todos os atributos atuais (removendo `cost_price` do
  payload — reenviar custo trava com erro 101202 em conta Vendor Advantage) e
  incluindo `package_level: unit` (a Amazon as vezes passa a exigir esse
  atributo ao mudar de categoria, mesmo que não exigisse antes).

## 3. Rio Master — imagens faltando (132 ASINs sem imagem principal)
Aguardando: ou (a) export do time que cuida do Playbook da Rio Master com os
arquivos originais em alta resolução (JPEG/PNG, não webp) dos ~132 SKUs
listados, ou (b) acesso mais direto ao Playbook pra automatizar a busca.
Mensagem de pedido já foi redigida nesta sessão (contém a lista completa dos
132 SKUs).

## 4. Card "Venda própria × outros distribuidores" — ajustes pendentes
Construído nesta sessão (06/10/2026) usando `distributorView` MANUFACTURING
(Fabricação, soma de todos os vendors da mesma marca) vs SOURCING (Origem, só
a própria conta) no `GET_VENDOR_SALES_REPORT`. Dúvidas do usuário esclarecidas
durante a sessão, registrar pra não perder o contexto:

- **Isso NÃO é "venda 1P × venda 3P" (marketplace)**. `GET_VENDOR_SALES_REPORT`
  é exclusivo de conta Vendor — não enxerga vendedores terceiros no marketplace
  de jeito nenhum. "Outros distribuidores" = outras contas Vendor cadastradas
  vendendo a mesma marca/fabricante (outro fornecedor direto pra Amazon), não
  revendedores do marketplace.
- **Testado e confirmado nesta sessão**: não há como buscar dados de 3P via
  API. Vendas de outros sellers são dado privado deles, a Amazon nunca expõe
  isso pra outro participante. Testei `get_item_offers` e
  `get_competitive_pricing_for_asins` (Product Pricing API) pra Blidshop — deu
  `Unauthorized` (permissão de Pricing não autorizada nessa integração Vendor).
  Pra ter visibilidade de ofertas/preços de terceiros (não vendas, só
  concorrência de Buy Box), precisaria autorizar a permissão "Pricing" no
  Seller Central da conta — configuração fora daqui. O card mais próximo que
  já temos hoje pra sinalizar concorrência é "Oferta em Destaque"
  (`transformar_destaque.py`), que mostra % de visualizações em que a Amazon/
  outro vendedor ganha o Buy Box — não é venda, mas é o proxy mais próximo que
  temos.
- **Ruído de medição**: contas sem nenhum outro distribuidor conhecido (ex.:
  Blidshop) ainda mostram uma diferença pequena entre Fabricação e Origem
  (Blidshop R$711, 0,4%; Rio Master R$394, 1%; WIWU R$641, 1,6%; Petiko R$30,
  1,5%) — isso é ruído de reconciliação entre os dois relatórios (pedidos
  separados à Amazon, podem ter cortes de dados ligeiramente diferentes), não
  um distribuidor real. Só Petclean (8%) e Jolitex (23%) têm diferença grande
  o suficiente pra ser provavelmente real.
  **Ação sugerida, ainda não aplicada**: só exibir "outros distribuidores" no
  card quando a diferença passar de um limite (ex.: 3-5%); abaixo disso,
  mostrar como "sem diferença relevante" pra não confundir contas que não têm
  outro distribuidor de verdade.
- **Texto do card a corrigir**: a label atual usa "outros distribuidores /
  market place", copiada do painel de referência do parceiro que o usuário
  mostrou — mas "market place" é enganoso dado o que a métrica realmente mede.
  Trocar por algo tipo "outros distribuidores/fornecedores Vendor da mesma
  marca".

## 5. Criação de listings novos (ASIN/SKU que ainda não existe) via API
Pergunta do usuário (06/10/2026): dá pra subir produto novo pelo mesmo
mecanismo usado hoje pra editar? Resposta: sim, tecnicamente — `putListingsItem`
("Creates a new or fully-updates an existing listings item") cria um listing
novo quando o SKU informado ainda não existe na conta, usando o mesmo endpoint
que já validamos hoje pra PATCH/PUT de edição.

Diferenças importantes em relação a editar um item existente (o que fizemos
hoje):
- Precisa enviar **todos** os atributos obrigatórios da categoria de uma vez
  (título, bullets, descrição, imagens, dimensões, EAN/GTIN ou isenção,
  preço/custo etc.) — não dá pra reaproveitar atributos já preenchidos, porque
  não existem ainda.
- Em conta Vendor (caso da Jolitex), a criação de ASIN novo pode passar por
  aprovação/triagem da Amazon antes de ficar visível — precisa confirmar esse
  comportamento especificamente (não testado ainda).
- Se o produto novo for variação de um já existente (cor/tamanho diferente do
  mesmo produto pai), entra a lógica de vínculo ao ASIN pai — mesma área que
  já deu problema hoje (atributo `size`/`color` inconsistente na família).

Ainda não implementado nem testado nesta sessão — é um fluxo novo (hoje só
mexemos em listings que já existiam). Desenhar com calma na próxima sessão:
provavelmente vale um teste piloto com 1 produto novo real antes de escalar,
igual fizemos hoje com a reclassificação de categoria.

## 6. Limite de 1.600 chamadas/dia — não confirmado como real
Investigado nesta sessão: não existe menção a um teto diário de 1.600 chamadas
na documentação oficial da SP-API (o rate limit documentado é por segundo,
ex: 5 req/s pra Listings Items API, sem teto diário). O usuário disse que o
número veio de um colega — combinamos de seguir só a documentação oficial daqui
pra frente, mas vale confirmar a origem do número caso reapareça.
