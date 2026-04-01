# Changelog

## 0.10.2 — 2026-04-01
- Fix: specs-pull updates local frontmatter (spec_version, feature_status, doc_status) when content matches but metadata has drifted — prevents stale base_version causing false 409 conflicts on push

## 0.10.1 — 2026-03-31
- Align marketplace and plugin versions

## 0.10.0 — 2026-03-31
- Feature and document management commands (create, rename, delete features and documents)

## 0.9.1 — 2026-03-31
- Fix: remove explicit hooks reference — auto-discovered by convention

## 0.9.0 — 2026-03-31
- Phased spec commands: `/spec requirements`, `/spec design`, `/spec infra`, `/spec plan`

## 0.8.1 — 2026-03-29
- Fix: register hooks in plugin manifest
