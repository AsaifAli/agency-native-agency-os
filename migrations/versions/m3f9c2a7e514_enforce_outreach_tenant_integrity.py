"""Enforce organization/workspace-consistent outreach relationships.

Revision ID: m3f9c2a7e514
Revises: l2e8a0b6d549
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "m3f9c2a7e514"
down_revision: Union[str, Sequence[str], None] = "l2e8a0b6d549"
branch_labels = None
depends_on = None


def _assert_no_orphaned_scope_relationships() -> None:
    checks = {
        "contacts.workspace": """
            SELECT count(*) FROM contacts c
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = c.org_id AND w.id = c.workspace_id
            )
        """,
        "leads.workspace": """
            SELECT count(*) FROM leads l
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = l.org_id AND w.id = l.workspace_id
            )
        """,
        "approvals.workspace": """
            SELECT count(*) FROM approvals a
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = a.org_id AND w.id = a.workspace_id
            )
        """,
        "outbound_senders.workspace": """
            SELECT count(*) FROM outbound_senders s
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = s.org_id AND w.id = s.workspace_id
            )
        """,
        "communication_consents.scope": """
            SELECT count(*) FROM communication_consents c
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = c.org_id AND w.id = c.workspace_id
            ) OR NOT EXISTS (
                SELECT 1 FROM contacts p
                WHERE p.org_id = c.org_id AND p.workspace_id = c.workspace_id
                  AND p.id = c.contact_id
            )
        """,
        "communication_blocks.scope": """
            SELECT count(*) FROM communication_blocks b
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = b.org_id AND w.id = b.workspace_id
            ) OR NOT EXISTS (
                SELECT 1 FROM contacts p
                WHERE p.org_id = b.org_id AND p.workspace_id = b.workspace_id
                  AND p.id = b.contact_id
            )
        """,
        "outbound_messages.scope": """
            SELECT count(*) FROM outbound_messages m
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = m.org_id AND w.id = m.workspace_id
            ) OR NOT EXISTS (
                SELECT 1 FROM outbound_senders s
                WHERE s.org_id = m.org_id AND s.workspace_id = m.workspace_id
                  AND s.id = m.sender_id
            ) OR NOT EXISTS (
                SELECT 1 FROM contacts c
                WHERE c.org_id = m.org_id AND c.workspace_id = m.workspace_id
                  AND c.id = m.contact_id
            ) OR (
                m.lead_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM leads l
                    WHERE l.org_id = m.org_id AND l.workspace_id = m.workspace_id
                      AND l.id = m.lead_id
                )
            ) OR (
                m.consent_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM communication_consents c
                    WHERE c.org_id = m.org_id AND c.workspace_id = m.workspace_id
                      AND c.id = m.consent_id
                )
            ) OR (
                m.approval_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM approvals a
                    WHERE a.org_id = m.org_id AND a.workspace_id = m.workspace_id
                      AND a.id = m.approval_id
                )
            )
        """,
        "outbound_message_events.scope": """
            SELECT count(*) FROM outbound_message_events e
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces w
                WHERE w.org_id = e.org_id AND w.id = e.workspace_id
            ) OR NOT EXISTS (
                SELECT 1 FROM outbound_messages m
                WHERE m.org_id = e.org_id AND m.workspace_id = e.workspace_id
                  AND m.id = e.message_id
            )
        """,
    }
    connection = op.get_bind()
    violations = {
        name: int(connection.execute(sa.text(statement)).scalar_one())
        for name, statement in checks.items()
    }
    violations = {name: count for name, count in violations.items() if count}
    if violations:
        raise RuntimeError(
            "Tenant-integrity migration aborted; repair orphaned relationships first: "
            + ", ".join(f"{name}={count}" for name, count in violations.items())
        )


def upgrade() -> None:
    _assert_no_orphaned_scope_relationships()

    with op.batch_alter_table("workspaces") as batch:
        batch.create_unique_constraint("uq_workspaces_org_id", ["org_id", "id"])
    with op.batch_alter_table("contacts") as batch:
        batch.create_unique_constraint("uq_contacts_scope_id", ["org_id", "workspace_id", "id"])
        batch.create_foreign_key(
            "fk_contacts_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
    with op.batch_alter_table("leads") as batch:
        batch.create_unique_constraint("uq_leads_scope_id", ["org_id", "workspace_id", "id"])
        batch.create_foreign_key(
            "fk_leads_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
    with op.batch_alter_table("approvals") as batch:
        batch.create_unique_constraint("uq_approvals_scope_id", ["org_id", "workspace_id", "id"])
        batch.create_foreign_key(
            "fk_approvals_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
    with op.batch_alter_table("outbound_senders") as batch:
        batch.create_unique_constraint("uq_outbound_senders_scope_id", ["org_id", "workspace_id", "id"])
        batch.create_foreign_key(
            "fk_outbound_senders_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
    with op.batch_alter_table("communication_consents") as batch:
        batch.create_unique_constraint("uq_communication_consents_scope_id", ["org_id", "workspace_id", "id"])
        batch.create_foreign_key(
            "fk_communication_consents_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_communication_consents_contact_scope", "contacts",
            ["org_id", "workspace_id", "contact_id"],
            ["org_id", "workspace_id", "id"], ondelete="CASCADE",
        )
    with op.batch_alter_table("communication_blocks") as batch:
        batch.create_foreign_key(
            "fk_communication_blocks_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_communication_blocks_contact_scope", "contacts",
            ["org_id", "workspace_id", "contact_id"],
            ["org_id", "workspace_id", "id"], ondelete="CASCADE",
        )
    with op.batch_alter_table("outbound_messages") as batch:
        batch.create_unique_constraint("uq_outbound_messages_scope_id", ["org_id", "workspace_id", "id"])
        batch.create_foreign_key(
            "fk_outbound_messages_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_outbound_messages_sender_scope", "outbound_senders",
            ["org_id", "workspace_id", "sender_id"],
            ["org_id", "workspace_id", "id"], ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_outbound_messages_contact_scope", "contacts",
            ["org_id", "workspace_id", "contact_id"],
            ["org_id", "workspace_id", "id"], ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_outbound_messages_lead_scope", "leads",
            ["org_id", "workspace_id", "lead_id"],
            ["org_id", "workspace_id", "id"], ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_outbound_messages_consent_scope", "communication_consents",
            ["org_id", "workspace_id", "consent_id"],
            ["org_id", "workspace_id", "id"], ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_outbound_messages_approval_scope", "approvals",
            ["org_id", "workspace_id", "approval_id"],
            ["org_id", "workspace_id", "id"], ondelete="RESTRICT",
        )
    with op.batch_alter_table("outbound_message_events") as batch:
        batch.create_foreign_key(
            "fk_outbound_message_events_workspace_scope", "workspaces",
            ["org_id", "workspace_id"], ["org_id", "id"], ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_outbound_message_events_message_scope", "outbound_messages",
            ["org_id", "workspace_id", "message_id"],
            ["org_id", "workspace_id", "id"], ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("outbound_message_events") as batch:
        batch.drop_constraint("fk_outbound_message_events_message_scope", type_="foreignkey")
        batch.drop_constraint("fk_outbound_message_events_workspace_scope", type_="foreignkey")
    with op.batch_alter_table("outbound_messages") as batch:
        for name in (
            "fk_outbound_messages_approval_scope", "fk_outbound_messages_consent_scope",
            "fk_outbound_messages_lead_scope", "fk_outbound_messages_contact_scope",
            "fk_outbound_messages_sender_scope", "fk_outbound_messages_workspace_scope",
        ):
            batch.drop_constraint(name, type_="foreignkey")
        batch.drop_constraint("uq_outbound_messages_scope_id", type_="unique")
    with op.batch_alter_table("communication_blocks") as batch:
        batch.drop_constraint("fk_communication_blocks_contact_scope", type_="foreignkey")
        batch.drop_constraint("fk_communication_blocks_workspace_scope", type_="foreignkey")
    with op.batch_alter_table("communication_consents") as batch:
        batch.drop_constraint("fk_communication_consents_contact_scope", type_="foreignkey")
        batch.drop_constraint("fk_communication_consents_workspace_scope", type_="foreignkey")
        batch.drop_constraint("uq_communication_consents_scope_id", type_="unique")
    with op.batch_alter_table("outbound_senders") as batch:
        batch.drop_constraint("fk_outbound_senders_workspace_scope", type_="foreignkey")
        batch.drop_constraint("uq_outbound_senders_scope_id", type_="unique")
    with op.batch_alter_table("approvals") as batch:
        batch.drop_constraint("fk_approvals_workspace_scope", type_="foreignkey")
        batch.drop_constraint("uq_approvals_scope_id", type_="unique")
    with op.batch_alter_table("leads") as batch:
        batch.drop_constraint("fk_leads_workspace_scope", type_="foreignkey")
        batch.drop_constraint("uq_leads_scope_id", type_="unique")
    with op.batch_alter_table("contacts") as batch:
        batch.drop_constraint("fk_contacts_workspace_scope", type_="foreignkey")
        batch.drop_constraint("uq_contacts_scope_id", type_="unique")
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_constraint("uq_workspaces_org_id", type_="unique")
