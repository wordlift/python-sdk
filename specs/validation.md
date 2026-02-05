# Validation Specs

## Google Search Gallery SHACLs

When a Google Search Gallery feature includes container types (for example
`ItemList`, `BreadcrumbList`, `QAPage`, `FAQPage`, `Quiz`, `ProfilePage`, `Product`,
`Recipe`, `Course`, `Review`) and their contained types (`ListItem`, `Question`,
`Answer`, `Comment`, `Offer`, `HowToStep`, `Person`, `Organization`, `Rating`,
`AggregateRating`), the generator scopes
contained constraints under the container properties instead of targeting the
contained types globally. This prevents list-, Q&A-, and product/profile-specific
rules from applying to unrelated nodes.

Schema.org grammar checks intentionally allow URL and text literals for every
property (in addition to the documented range types).

## JSON-LD validation from URLs

The validation module can render a URL with Playwright, extract all
`application/ld+json` fragments, flatten them into a single list of JSON-LD
nodes, and pass them through the SHACL validation pipeline.

Playwright is a required dependency for URL rendering. Install browser binaries
with `playwright install` after the Python dependencies are installed.
