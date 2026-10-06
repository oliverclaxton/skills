# Contract and recipes

## Contract CSV

Header matching is case-insensitive and exact for the `Elevate …` names; anything else falls back to fuzzy guessing, so use these exactly. Arrays (category, size, images, colour…) are **pipe-separated** in one cell. One CSV row = one variant.

| Header | Req | Rule |
|---|---|---|
| `Elevate Group Key` | for variants | Parent style ID. Rows sharing it become one product group. Alias: `Elevate Group ID`. Must differ from Product Key |
| `Elevate Product Key` | yes | One per colour/product. Rows sharing it become variants of that product. `A-Za-z0-9#+./_-`, ≤ 47 chars (the tool appends `_p` / `_v1`) |
| `Elevate Title` | yes | Product name **without** size/variant text; the tool takes the common prefix across variants |
| `Elevate URL` | yes | Relative, starts with `/` (query string kept). Strip the domain yourself |
| `Elevate Stock` | yes | Whole number ≥ 0. Turn "in stock"/"out of stock" into 1/0 |
| `Elevate List Price` | yes | Plain decimal with `.`: `1299.00`. No currency, no thousands separators (the tool treats `,` as a decimal point) |
| `Elevate Selling Price` | yes | ≤ List Price. Equal to List Price when there's no sale |
| `Elevate Size` | with variants | ≤ 127 chars (variant label limit). Unique per variant within a product, or supply `Elevate Variant SKU` |
| `Elevate Variant SKU` | recommended | Unique per row; becomes the variant label (≤ 127 chars). Stops size collisions failing import |
| `Elevate Variant URL` | no | Relative path |
| `Elevate Images` | no | ≤ 25 absolute URLs (`https://` or `//`), first is primary. Images are read from the first row of each product |
| `Elevate Brand`, `Elevate Description` | no | Description: plain text preferred; HTML is stripped |
| `Elevate Category` | no | ≤ 100 values. Hierarchy inside one value uses ` > `: `Clothing > Tops > T-Shirts` |
| `Elevate Ontology` | no | Single string, ` > ` separated |
| `Elevate Age`, `Department`, `Product Type` | no | ≤ 20 values each |
| `Elevate Gender`, `Pattern`, `Name`, `Series` | no | Series ≤ 20 chars. Name = translatable display name |
| `Elevate Release Date` | no | ISO 8601, `2026-03-01` |
| `Elevate Colour` | no | Only `#RRGGBB`/`#RGB` or `Gold`, `Silver`, `Multi`, `Transparent` |
| `Elevate Cost` | no | > 0 and < Selling Price, else leave blank |
| `customLabel:<name>` | no | Any number of columns. Becomes a facetable custom label; `|`-separated for multi-value. `<name>` XML-safe: letters, digits, `_ . -`, not starting with a digit |

Not expressible by header: custom **numbers** (set in the tool's mapping step, and choose Variant level for per-size values) and per-market overrides. Market, locale, currency and API key are entered in the tool.

## Grouping model

```
Group Key  (style)            ->  one Elevate product group
  Product Key (colour)        ->  one product; title/images/description/category from its first row
    Size / Variant SKU (row)  ->  one variant; stock + prices per row
```

- No Group Key: every distinct Product Key is its own group of one product.
- Two colours with identical sizes need **different** Product Keys under the same Group Key, otherwise their sizes collide.
- Product-level fields (title, brand, description, images, category, colour) come from the first row of the product; put the right value there or make it identical on every row.
- Duplicate ids across the feed usually mean the same item in several markets/languages, or variants sharing an id. Find out which before dropping.

## Reshape recipes

| Feed looks like | Do |
|---|---|
| Parent row + child rows (`parent_id`, `item_group_id`) | Group Key = parent id; Product Key = child id, or `<parent>-<colour>` when children are sizes |
| Only a variant SKU like `1096378-1-XS` | Group Key = first segment, Product Key = drop last segment, Size = last segment. Verify each derived key sits under exactly one parent |
| One row per style, sizes in a cell (`S,M,L`) | Split and `explode`; Variant SKU = `<key>-<size>`; stock per size only if the feed has it, else ask |
| Wide sizes (`Size_S`, `Size_M` stock columns) | `melt` to rows; the column name is the Size, the value is Stock; drop zero-stock sizes only if the user agrees |
| Category levels in `Cat1`,`Cat2`,`Cat3` | Join non-empty with ` > ` into one `Elevate Category` |
| Multiple categories per item | Join with `|` |
| `"20.95 EUR"`, `"1.299,00"`, `"£12"` | Extract the number; normalise to `.` decimal yourself, since the tool cannot tell `1.299` from `1,299` |
| Sale price blank | Selling = List |
| Price in minor units (`1999`) | Divide by 100 only after confirming with sample rows |
| Colour names (`Navy`) | Keep the name in `customLabel:colour_name`; put a hex in `Elevate Colour` only from a real mapping table, else omit |
| `image_1`…`image_8` plus `additional_image_link` | Join non-empty, de-duplicated, in order, with `|`; absolute URLs only |
| Protocol-less or relative image paths | Prefix the site's origin (ask if not visible in the feed) |
| Absolute product URLs | Keep path + query, drop the origin |
| HTML descriptions | Strip tags, collapse whitespace |
| Rows for inactive/hidden/draft items | Filter, count, report |
| Several markets/languages in one file | Ask which to load; one CSV per market |
| Excel with header offset or several sheets | `read_excel(header=N, sheet_name=…)`; the tool reads only the first sheet that has data |
| Keys with spaces or accents, or > 47 chars | Replace with a stable slug or hash-suffixed truncation, and keep the mapping unique |

## Limits the checker enforces

Product/Group keys `A-Za-z0-9#+./_-` ≤ 47 · Variant SKU / Size (variant label) ≤ 127 · Selling ≤ List · Cost > 0 and < Selling · images ≤ 25 and absolute · category ≤ 100 · age/department/product type ≤ 20 · series ≤ 20 chars · a product with several variants needs a unique size or Variant SKU on each.

## Source of truth

Contract derived from `any-feed-to-voyado`: `lib/elevate/fields.ts` (column candidates), `lib/elevate/mapper.ts` (transforms), `lib/elevate/jsonl.ts` (grouping) and `import.schema.ts` (schema). If the tool's candidate lists change, update the table above.
