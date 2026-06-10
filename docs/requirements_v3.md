# Odoo CLI requirements — v3 (Platform)

This document tracks the v3 "platform" phase: turning the local CLI into a
foundation that AI agents, cloud services, and advanced workflows can build on.
`requirements.md` (v1) and `requirements_v2.md` are the canonical earlier specs.
Nothing here is committed scope yet — these are design intents, collected so the
earlier phases don't paint us into a corner, to be fleshed out once v2 is stable.

## MCP frontend
 - expose CLI operations as MCP tools for AI agents (`odoo-mcp` / `odoo mcp serve`)
 - MCP tools call the same core services as CLI commands; no business logic in
   the frontend (see `architecture.md` → dependency rules)
 - builds on v2's machine-readable groundwork: `--json` output, `odoo rpc`,
   `odoo status`, configurable Odoo credentials
 - tool design (granularity, schemas, auth) to be defined

## Cloud backend
 - candidates: Odoo.sh, managed workspaces, managed databases, cloud runners
 - the `Backend` interface is deliberately not defined before v3 (see
   `architecture.md` → "Backend seam (deferred)"): an interface extracted from a
   single implementation is usually the wrong one, so it is extracted when this
   second implementation exists to shape it
 - a cloud backend may execute an `OdooBinCommand` by translating it into a
   remote job, or reject unsupported capabilities through typed errors
 - the CLI grammar (commands, target flags, resolution rules) must not change
   per backend

## Extensions
 - advanced workflows packaged as extensions that expose CLI commands and/or MCP
   tools while reusing the same core and backend APIs
 - candidates: support workflows, Odoo.sh workflows, dump/restore/neutralize
   variants, upgrade flows, export tooling
 - extensions must not redefine workspace resolution, target resolution, addons
   path resolution, venv rules, or server lifecycle
 - packaging and discovery mechanism (e.g. entry points) to be defined

## Open questions
 - distribution: does the MCP frontend ship in the same package as the CLI or
   separately?
 - authentication and secret handling for cloud backends
 - capability negotiation between frontends and backends: what does a command or
   MCP tool do when the active backend cannot support it?
