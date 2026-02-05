# TLS/SSL Specs

## CA Bundle Resolution

The SDK enforces SSL verification. CA bundle resolution follows these rules:

1. If an explicit CA bundle path is provided, use it when it exists.
2. On macOS, prefer the system CA bundle if available; otherwise fall back to `certifi`.
3. On other platforms, rely on the system CA bundle when available.
