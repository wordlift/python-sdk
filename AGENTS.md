# AGENTS

## Project Notes

- Generated Google SHACLs scope contained type requirements under container types
  (for example `ItemList`/`BreadcrumbList` → `ListItem`, `QAPage`/`FAQPage`/`Quiz`
  → `Question`/`Answer`/`Comment`, `ProfilePage` → `Person`/`Organization`,
  `Product` → `Offer`, `Recipe` → `HowToStep`, `Course` → `Organization`/`CreativeWork`)
  when both appear in a feature definition. This prevents constraints from firing
  on unrelated nodes.
- Python support is validated against 3.10–3.14; ensure tests pass on 3.14 before
  bumping the range.
