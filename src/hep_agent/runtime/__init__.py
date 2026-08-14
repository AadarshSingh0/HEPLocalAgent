"""Authoritative managed HEP stack manifest and process environment."""

from .stack import (
    STACK_MANIFEST_SCHEMA,
    StackConfigurationError,
    StackManifest,
    build_controlled_environment,
    build_stack_environment,
    default_manifest_path,
    load_stack_manifest,
    load_configured_stack,
)
from .linkage import inspect_native_linkage, validate_macho_linkage
from .audit import audit_managed_linkage, managed_linkage_targets

__all__ = [
    "STACK_MANIFEST_SCHEMA",
    "StackConfigurationError",
    "StackManifest",
    "build_controlled_environment",
    "build_stack_environment",
    "default_manifest_path",
    "load_stack_manifest",
    "load_configured_stack",
    "inspect_native_linkage",
    "validate_macho_linkage",
    "audit_managed_linkage",
    "managed_linkage_targets",
]
