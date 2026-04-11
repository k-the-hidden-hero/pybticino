# Changelog

## v1.7.1
- Fix `ConcurrencyError` in `resubscribe()`: send-only, no `recv()` conflict with listener
- Python 3.13 compatibility: lowered `requires-python` from `>=3.14` to `>=3.13`
- Fix `except A, B:` syntax error on Python 3.13

## v1.7.0
- Add `resubscribe()` method for token refresh on existing connection
- Fix `_is_running` stuck state in `connect()`
- Add `SignalingClient` for WebRTC signaling
- Add `token_callback` and `set_tokens()` to `AuthHandler`

## v1.6.0
- Add `token_callback` parameter to `AuthHandler`
- Add `set_tokens()` for restoring saved tokens

## v1.5.3
- Remove `filter=silent` from subscribe (caused error code 11)
- Disable application-level ping/pong (caused disconnections after ~10 min)

## v1.5.2
- Increase API timeout to 30s
- Handle error responses from subscribe immediately

## v1.5.1
- Increase API default timeout from 15s to 30s

## v1.5.0
- Python 3.14 support
- Modern CI/CD with GitHub Actions
- Comprehensive test suite (54 tests)
- Published to PyPI with Trusted Publisher (OIDC)
