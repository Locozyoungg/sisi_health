"""Envelope encryption primitives and the KeyProvider interface.

Design (spec 2, key management): every user record has its own AES-256-GCM data
key, wrapped by a master key. The master key lives behind the KeyProvider
interface — dev/demo uses a local file, staging/prod requires
SISI_MASTER_KEY_B64 (and a self-hosted Vault / cloud KMS in the pilot).
Key rotation procedure: see docs/runbook.md (Phase 8); the provider is
versioned per data key (core.data_keys.key_version) so rotation is additive.
"""
