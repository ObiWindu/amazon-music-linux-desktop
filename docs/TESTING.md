# Testing

Run all:
```
./scripts/run-tests.sh
```
Unit + security:
```
python3 -m pytest tests/unit tests/security
```
Integration (requires display):
```
python3 -m pytest tests/integration
```

DRM acceptance requires real Amazon account and subscription; see DRM_COMPATIBILITY.md.
