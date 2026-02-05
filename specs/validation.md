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
