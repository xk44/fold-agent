"""Role-based access control model for FoldAgent.

Defines roles, permissions, and the mapping between them.
Actual auth middleware is deferred — this is the permission model only.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    admin = "admin"
    researcher = "researcher"
    reviewer = "reviewer"
    readonly = "readonly"


class Permission(str, Enum):
    create_case = "create_case"
    edit_case = "edit_case"
    delete_case = "delete_case"
    run_pipeline = "run_pipeline"
    export_data = "export_data"
    manage_users = "manage_users"
    view_audit = "view_audit"
    view_cases = "view_cases"
    submit_alphafold = "submit_alphafold"
    record_attestation = "record_attestation"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.admin: set(Permission),
    Role.researcher: {
        Permission.create_case,
        Permission.edit_case,
        Permission.run_pipeline,
        Permission.export_data,
        Permission.view_audit,
        Permission.view_cases,
        Permission.submit_alphafold,
        Permission.record_attestation,
    },
    Role.reviewer: {
        Permission.view_cases,
        Permission.view_audit,
        Permission.export_data,
        Permission.record_attestation,
    },
    Role.readonly: {
        Permission.view_cases,
        Permission.view_audit,
    },
}


def check_permission(role: str, permission: str) -> bool:
    try:
        r = Role(role)
        p = Permission(permission)
    except ValueError:
        return False
    return p in ROLE_PERMISSIONS.get(r, set())


def get_role_permissions(role: str) -> list[str]:
    try:
        r = Role(role)
    except ValueError:
        return []
    return sorted(p.value for p in ROLE_PERMISSIONS.get(r, set()))
