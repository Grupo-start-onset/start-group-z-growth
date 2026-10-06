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

## 4. Limite de 1.600 chamadas/dia — não confirmado como real
Investigado nesta sessão: não existe menção a um teto diário de 1.600 chamadas
na documentação oficial da SP-API (o rate limit documentado é por segundo,
ex: 5 req/s pra Listings Items API, sem teto diário). O usuário disse que o
número veio de um colega — combinamos de seguir só a documentação oficial daqui
pra frente, mas vale confirmar a origem do número caso reapareça.
