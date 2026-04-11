# pybticino

Async Python library for the BTicino/Netatmo API. Controls BTicino Classe 100X/300X video intercom systems via the Netatmo cloud.

## Overview

pybticino provides:

- **OAuth2 authentication** with automatic token refresh and persistence
- **REST API** for home topology, device status, and control
- **WebSocket** for real-time push notifications (doorbell rings, connection events)
- **WebRTC signaling** for live video calls (experimental)

## Quick install

```bash
pip install pybticino
```

Requires Python 3.13+.

## Used by

- [bticino_intercom](https://github.com/k-the-hidden-hero/bticino_intercom) — Home Assistant custom integration

## Links

- [PyPI](https://pypi.org/project/pybticino/)
- [GitHub](https://github.com/k-the-hidden-hero/pybticino)
- [Issues](https://github.com/k-the-hidden-hero/pybticino/issues)
