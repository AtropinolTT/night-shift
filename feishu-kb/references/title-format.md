# Title Format — Paper Doc Naming

`title_clean.py` applies these rules to generate the Feishu doc title for new `source-summary` pages. Source: `scripts/title_clean.py`.

## Format Rule

```
{FirstAuthor}_{Year}_{CleanedTitle}
```

Examples:
- `Zhang, J. — "Lipid Nanoparticle Design Using Deep Learning"` → `Zhang_2024_Lipid_Nanoparticle_Design_Using_Deep_Learning`
- `Kim, S. et al. — "A Novel mRNA Vaccine Platform"` → `Kim_2024_A_Novel_mRNA_Vaccine_Platform`

## Cleaning Rules (apply in order)

1. **Spaces → underscores**: ` ` → `_`
2. **Strip characters**: remove `:`, `,`, `?`, `!`, `*`, `/`, `\`, `'`, `"`, `<`, `>`, `(`, `)`, `[`, `]`
3. **Collapse**: `__` → `_` (repeat until stable)
4. **Trim**: strip leading/trailing `_` from the full string
5. **Truncate**: if total length > 200 chars, truncate at word boundary (prefer to keep first 3 words + last word)

## Edge Cases

| Case | Rule |
|------|------|
| Greek letters (α, β, γ…) | Expand to `alpha`, `beta`, `gamma` |
|化学式 (H2O, mRNA) | Keep as-is |
| Hyphenated words | Keep hyphen: `single-cell` → `single_cell` |
| Chinese title | romanize or keep Chinese; doc title in Feishu can be Chinese |
| No author found | Use `Unknown_Year_` prefix |
| Year unknown | Use `XXXX_` placeholder |

## Implementation

```python
def clean_title(title: str) -> str:
    # 1. strip HTML/JATS
    title = re.sub(r'<[^>]+>', '', title)
    # 2. Greek expansion
    greek = {'α':'alpha','β':'beta','γ':'gamma','δ':'delta','ε':'epsilon',
             'μ':'mu','π':'pi','σ':'sigma','Ω':'omega'}
    for g, e in greek.items():
        title = title.replace(g, e)
    # 3. strip forbidden chars
    title = re.sub(r'[:,\?!\*\\/\'\"<>\(\)\[\]]', '', title)
    # 4. spaces → underscores
    title = '_'.join(title.split())
    # 5. collapse
    while '__' in title:
        title = title.replace('__', '_')
    return title.strip('_')[:200]
```

## CrossRef Field Mapping

| CrossRef field | Extraction |
|----------------|-----------|
| `message.author[0].family` | First author last name |
| `message.published.date-parts[0][0]` | Year (int) |
| `message.title[0]` | Raw title (JATS-stripped via `clean_text()`) |

## See Also

- `wiki-schema.md` — `source-summary` naming (概念 folder uses kebab-case)
- `crossref-helper.md` — CrossRef API + author/year extraction
- `scripts/title_clean.py` — executable implementation
