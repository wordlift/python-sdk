# Validation Specs

## Google Search Gallery SHACLs

When a Google Search Gallery feature includes container types (for example
`ItemList`, `BreadcrumbList`, `QAPage`, `FAQPage`, `Quiz`, `ProfilePage`, `Product`,
`Recipe`, `Course`, `Review`) and their contained types (`ListItem`, `Question`,
`Answer`, `Comment`, `Offer`, `AggregateOffer`, `HowToStep`, `Person`, `Organization`, `Rating`,
`AggregateRating`, `Review`, `ItemList`), the generator scopes contained
constraints under the container properties instead of targeting the contained
types globally. This prevents list-, Q&A-, and product/profile-specific rules from
applying to unrelated nodes.

The generator also captures "one of" requirements expressed in prose lists
(for example, Product snippets requiring `review` or `aggregateRating` or
`offers`) and emits `sh:or` constraints so any listed property satisfies the
requirement.

For Product snippets, `offers` supports either an `Offer` shape or an
`AggregateOffer` shape.

When a required property row includes alternatives (for example,
`price or priceSpecification.price`), the generator treats the row as a
`sh:or` group so either property satisfies the requirement.

Schema.org grammar checks intentionally allow URL and text literals for every
property (in addition to the documented range types).

## JSON-LD validation from URLs

The validation module can render a URL with Playwright, extract all
`application/ld+json` fragments, flatten them into a single list of JSON-LD
nodes, and pass them through the SHACL validation pipeline.

Playwright is a required dependency for URL rendering. Install browser binaries
with `playwright install` after the Python dependencies are installed.
