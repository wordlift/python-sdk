# HTML Converter

The `HtmlConverter` utility class provides a mechanism to convert HTML strings into valid XHTML strings. This is particularly useful when working with XML-based processing pipelines that require well-formed XML input.

## Features

- **DOCTYPE Removal**: Automatically strips `<!DOCTYPE ...>` declarations.
- **Invalid Character Stripping**: Removes control characters invalid in XML 1.0 (e.g., null bytes).
- **Attribute Sanitization**: Removes attributes with invalid XML names.
- **Value Sanitization**: Strips invalid characters from attribute values.
- **Namespace Safety**: Rewrites undeclared prefixed tags (e.g. `o:p` -> `p`) and removes undeclared prefixed attributes (e.g. `foo:bar`) to avoid XML parser `unbound prefix` failures.
- **Encoding**: Produces UTF-8 encoded, recover-mode parsed XHTML.

## Usage

```python
from wordlift_sdk.utils import HtmlConverter

# 1. Initialize the converter
converter = HtmlConverter()

# 2. Convert HTML to XHTML
raw_html = """
<!DOCTYPE html>
<html>
  <body>
    <o:p xlink:href="https://example.com" data-id="123">
      <p>Hello & World</p>
    </o:p>
  </body>
</html>
"""

try:
    xhtml = converter.convert(raw_html)
    print(xhtml)
    # Output will be a valid XHTML string:
    # <html>
    #   <body>
    #     <p data-id="123">
    #       <p>Hello &amp; World</p>
    #     </p>
    #   </body>
    # </html>
except ImportError:
    print("lxml library is required. Install with 'pip install lxml'.")
except RuntimeError as e:
    print(f"Conversion failed: {e}")
```

## Requirements

The `lxml` library is required for this utility to function.

```bash
pip install lxml
```

## API Reference

### `HtmlConverter`

**`convert(self, html: str) -> str`**

Converts an HTML string to a valid XHTML string.

- **Args:**
    - `html` (str): The raw HTML string to convert.

- **Returns:**
    - `str`: A sanitized XHTML string.

- **Raises:**
    - `ImportError`: If the `lxml` library is not installed.
    - `RuntimeError`: If the conversion process fails.
