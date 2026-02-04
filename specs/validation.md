# Validation Specs

## Google Search Gallery SHACLs

When a Google Search Gallery feature includes both `ItemList` and `ListItem` requirements,
`ListItem` constraints are scoped under `ItemList` via `itemListElement` instead of
targeting `ListItem` globally. This prevents carousel rules from applying to unrelated
lists such as `BreadcrumbList`.
