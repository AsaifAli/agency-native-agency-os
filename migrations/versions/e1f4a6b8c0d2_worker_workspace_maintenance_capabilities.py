"""Add short-lived workspace capabilities for bounded worker maintenance.

The worker claims one workspace at a time through a SECURITY DEFINER function.
The returned token is transaction-bound and cannot be used to enumerate or read
other workspace rows. Existing execution capabilities remain the only path for
processing a specific execution outside maintenance.
"""
from alembic import op

revision = "e1f4a6b8c0d2"
down_revision = "d9e3f5a7b2c4"
branch_labels = None
depends_on = None

WORKSPACE_TABLES = (
    "agent_sessions", "agents", "approvals", "audit_events", "call_sessions",
    "call_transcripts", "client_onboardings", "clients", "communication_blocks",
    "communication_consents", "contact_activities", "contacts", "contract_records",
    "delegations", "evaluation_runs", "executions", "invoice_records",
    "lead_research_drafts", "lead_research_records", "leads", "machine_identities", "milestones",
    "onboarding_checklist_items", "opportunities", "orchestration_plan_drafts",
    "orchestration_plans", "outbound_message_events", "outbound_messages",
    "outbound_senders", "outbox_events", "outreach_drafts", "payment_receipts",
    "project_costs", "projects", "proposals", "retainer_service_periods",
    "scope_change_requests", "service_offerings", "service_playbooks", "tasks",
    "time_entries", "tool_invocations", "workforce_capabilities", "workforce_members",
    "workforce_positions", "workforce_units",
)
NULLABLE_WORKSPACE_TABLES = {"audit_events", "outbox_events"}


def _policy_parts(table: str) -> tuple[str, str, str]:
    user = "nullif(current_setting('agency_os.user_id', true), '')"
    org_access = f"agency_os_private.user_has_org_access(org_id, {user})"
    workspace_access = (
        f"agency_os_private.user_has_workspace_access(org_id, workspace_id, {user})"
    )
    if table in NULLABLE_WORKSPACE_TABLES:
        human = (
            f"((workspace_id IS NULL AND {org_access}) OR "
            f"(workspace_id IS NOT NULL AND {workspace_access}))"
        )
        machine = (
            "(session_user <> 'agency_os_worker' AND "
            "org_id = nullif(current_setting('agency_os.machine_org_id', true), '') "
            "AND (workspace_id IS NULL OR workspace_id = "
            "nullif(current_setting('agency_os.machine_workspace_id', true), '')))"
        )
        worker = (
            "(session_user = 'agency_os_worker' AND workspace_id IS NOT NULL AND "
            "(agency_os_private.worker_has_execution_context(org_id, workspace_id, NULL) "
            "OR agency_os_private.worker_has_workspace_context(org_id, workspace_id)))"
        )
    else:
        human = workspace_access
        if table == "machine_identities":
            machine = (
                "(session_user <> 'agency_os_worker' AND "
                "org_id = nullif(current_setting('agency_os.machine_org_id', true), '') "
                "AND (workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '') "
                "OR id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')))"
            )
            # Managed-agent tools may access only the identity bound to the
            # current execution's agent. Maintenance leases never grant this.
            worker = (
                "(session_user = 'agency_os_worker' AND subject_type = 'agent' AND EXISTS ("
                "SELECT 1 FROM public.executions AS e "
                "WHERE e.org_id = machine_identities.org_id "
                "AND e.workspace_id = machine_identities.workspace_id "
                "AND e.agent_id = machine_identities.subject_id "
                "AND agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id)))"
            )
        else:
            machine = (
                "(session_user <> 'agency_os_worker' AND "
                "org_id = nullif(current_setting('agency_os.machine_org_id', true), '') "
                "AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), ''))"
            )
            worker = (
                "(session_user = 'agency_os_worker' AND "
                "(agency_os_private.worker_has_execution_context(org_id, workspace_id, NULL) "
                "OR agency_os_private.worker_has_workspace_context(org_id, workspace_id)))"
            )
    return human, machine, worker


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE TABLE agency_os_private.worker_workspace_capabilities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash bytea NOT NULL UNIQUE,
            org_id text NOT NULL,
            workspace_id text NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
            worker_id text NOT NULL,
            expires_at timestamptz NOT NULL,
            invalidated_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (octet_length(token_hash) = 32)
        )
    """)
    op.execute("""
        CREATE INDEX worker_workspace_capabilities_active_idx
        ON agency_os_private.worker_workspace_capabilities
            (workspace_id, worker_id, expires_at)
        WHERE invalidated_at IS NULL
    """)
    op.execute("""
        CREATE TABLE agency_os_private.worker_workspace_transaction_context (
            backend_pid integer NOT NULL,
            transaction_id bigint NOT NULL,
            capability_id uuid NOT NULL
                REFERENCES agency_os_private.worker_workspace_capabilities(id)
                ON DELETE CASCADE,
            org_id text NOT NULL,
            workspace_id text NOT NULL,
            worker_id text NOT NULL,
            established_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (backend_pid, transaction_id)
        )
    """)
    op.execute("""
        ALTER TABLE agency_os_private.worker_workspace_capabilities
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        ALTER TABLE agency_os_private.worker_workspace_transaction_context
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON TABLE
            agency_os_private.worker_workspace_capabilities,
            agency_os_private.worker_workspace_transaction_context
        FROM PUBLIC, agency_os_app, agency_os_worker
    """)

    # An execution capability is established only while the lease is active.
    # Once established, its current transaction must still be able to persist
    # terminal state and audit rows in that same transaction.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.worker_has_execution_context(
            target_org_id text, target_workspace_id text, target_execution_id text DEFAULT NULL
        ) RETURNS boolean
        LANGUAGE sql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
            SELECT session_user = 'agency_os_worker' AND EXISTS (
                SELECT 1
                FROM agency_os_private.worker_transaction_context AS ctx
                JOIN agency_os_private.worker_lease_capabilities AS cap
                  ON cap.id = ctx.capability_id
                JOIN public.executions AS e ON e.id = ctx.execution_id
                JOIN public.execution_attempts AS a
                  ON a.id = ctx.attempt_id AND a.execution_id = e.id
                WHERE ctx.backend_pid = pg_backend_pid()
                  AND ctx.transaction_id = txid_current()
                  AND e.org_id = target_org_id
                  AND e.workspace_id = target_workspace_id
                  AND (target_execution_id IS NULL OR e.id = target_execution_id)
                  AND cap.invalidated_at IS NULL
                  AND cap.expires_at > clock_timestamp()
                  AND cap.execution_id = e.id
                  AND cap.attempt_id = a.id
                  AND cap.worker_id = ctx.worker_id
                  AND cap.lease_generation = ctx.lease_generation
                  AND a.worker_id = ctx.worker_id
                  AND a.lease_generation = ctx.lease_generation
                  AND (
                    (a.status::text IN ('claimed', 'running')
                     AND a.lease_expires_at > clock_timestamp())
                    OR a.status::text IN ('succeeded', 'failed', 'abandoned', 'paused')
                  )
                  AND e.status::text IN ('claimed', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled', 'paused')
            )
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.worker_has_execution_context(text, text, text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.worker_has_execution_context(text, text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.worker_has_execution_context(text, text, text) TO agency_os_app, agency_os_worker")

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.claim_worker_maintenance_scope(
            p_worker_id text,
            p_lease_seconds integer,
            p_token_hash bytea,
            p_after_workspace_id text DEFAULT NULL
        )
        RETURNS TABLE(org_id text, workspace_id text)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            target public.workspaces%ROWTYPE;
            lease_deadline timestamptz;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_worker_id IS NULL OR length(p_worker_id) NOT BETWEEN 1 AND 160
               OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 15 AND 300
               OR p_token_hash IS NULL OR octet_length(p_token_hash) <> 32 THEN
                RAISE EXCEPTION 'invalid worker maintenance claim'
                    USING ERRCODE = '22023';
            END IF;

            DELETE FROM agency_os_private.worker_workspace_transaction_context AS ctx
            WHERE (ctx.backend_pid = pg_backend_pid() AND ctx.transaction_id <> txid_current())
               OR ctx.established_at < clock_timestamp() - interval '1 day'
               OR NOT EXISTS (
                    SELECT 1 FROM pg_stat_activity AS activity
                    WHERE activity.pid = ctx.backend_pid
               );
            DELETE FROM agency_os_private.worker_workspace_capabilities AS cap
            WHERE cap.expires_at < clock_timestamp() - interval '1 day'
               OR cap.invalidated_at < clock_timestamp() - interval '1 day';

            SELECT w.* INTO target
            FROM public.workspaces AS w
            WHERE (p_after_workspace_id IS NULL OR w.id > p_after_workspace_id)
              AND NOT EXISTS (
                  SELECT 1
                  FROM agency_os_private.worker_workspace_capabilities AS cap
                  WHERE cap.workspace_id = w.id
                    AND cap.invalidated_at IS NULL
                    AND cap.expires_at > clock_timestamp()
              )
            ORDER BY w.id
            LIMIT 1
            FOR UPDATE OF w SKIP LOCKED;

            IF NOT FOUND THEN
                RETURN;
            END IF;

            lease_deadline := clock_timestamp()
                + make_interval(secs => p_lease_seconds);

            INSERT INTO agency_os_private.worker_workspace_capabilities (
                token_hash, org_id, workspace_id, worker_id, expires_at
            ) VALUES (
                p_token_hash, target.org_id, target.id, p_worker_id, lease_deadline
            );

            INSERT INTO public.audit_events (
                id, org_id, workspace_id, actor_user_id, event_type,
                resource_type, resource_id, payload, created_at
            ) VALUES (
                gen_random_uuid()::text, target.org_id, target.id, NULL,
                'worker.maintenance_scope_claimed', 'workspace', target.id,
                jsonb_build_object('worker_id', p_worker_id, 'lease_seconds', p_lease_seconds)::json,
                clock_timestamp()
            );

            RETURN QUERY SELECT target.org_id, target.id;
        END
        $function$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.establish_worker_workspace_context(
            p_token bytea, p_org_id text, p_workspace_id text, p_worker_id text
        ) RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE capability agency_os_private.worker_workspace_capabilities%ROWTYPE;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_token IS NULL OR octet_length(p_token) <> 32
               OR p_org_id IS NULL OR p_workspace_id IS NULL
               OR p_worker_id IS NULL OR length(p_worker_id) NOT BETWEEN 1 AND 160 THEN
                RETURN false;
            END IF;

            SELECT c.* INTO capability
            FROM agency_os_private.worker_workspace_capabilities AS c
            WHERE c.token_hash = sha256(p_token)
              AND c.org_id = p_org_id
              AND c.workspace_id = p_workspace_id
              AND c.worker_id = p_worker_id
              AND c.invalidated_at IS NULL
              AND c.expires_at > clock_timestamp()
            FOR UPDATE;

            IF NOT FOUND THEN
                RETURN false;
            END IF;

            INSERT INTO agency_os_private.worker_workspace_transaction_context (
                backend_pid, transaction_id, capability_id,
                org_id, workspace_id, worker_id
            ) VALUES (
                pg_backend_pid(), txid_current(), capability.id,
                p_org_id, p_workspace_id, p_worker_id
            )
            ON CONFLICT (backend_pid, transaction_id) DO UPDATE SET
                capability_id = EXCLUDED.capability_id,
                org_id = EXCLUDED.org_id,
                workspace_id = EXCLUDED.workspace_id,
                worker_id = EXCLUDED.worker_id,
                established_at = clock_timestamp();

            RETURN true;
        END
        $function$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.worker_has_workspace_context(
            target_org_id text, target_workspace_id text
        ) RETURNS boolean
        LANGUAGE sql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
            SELECT session_user = 'agency_os_worker' AND EXISTS (
                SELECT 1
                FROM agency_os_private.worker_workspace_transaction_context AS ctx
                JOIN agency_os_private.worker_workspace_capabilities AS cap
                  ON cap.id = ctx.capability_id
                WHERE ctx.backend_pid = pg_backend_pid()
                  AND ctx.transaction_id = txid_current()
                  AND ctx.org_id = target_org_id
                  AND ctx.workspace_id = target_workspace_id
                  AND cap.org_id = target_org_id
                  AND cap.workspace_id = target_workspace_id
                  AND cap.worker_id = ctx.worker_id
                  AND cap.invalidated_at IS NULL
                  AND cap.expires_at > clock_timestamp()
            )
        $function$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.release_worker_maintenance_scope()
        RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            released_count integer;
            released_scope record;
        BEGIN
            IF session_user <> 'agency_os_worker' THEN
                RETURN false;
            END IF;
            UPDATE agency_os_private.worker_workspace_capabilities AS cap
            SET invalidated_at = clock_timestamp()
            FROM agency_os_private.worker_workspace_transaction_context AS ctx
            WHERE ctx.backend_pid = pg_backend_pid()
              AND ctx.transaction_id = txid_current()
              AND cap.id = ctx.capability_id
              AND cap.invalidated_at IS NULL
              AND cap.expires_at > clock_timestamp()
            RETURNING cap.org_id, cap.workspace_id, cap.worker_id
            INTO released_scope;
            GET DIAGNOSTICS released_count = ROW_COUNT;
            IF released_count <> 1 THEN
                RETURN false;
            END IF;
            INSERT INTO public.audit_events (
                id, org_id, workspace_id, actor_user_id, event_type,
                resource_type, resource_id, payload, created_at
            ) VALUES (
                gen_random_uuid()::text, released_scope.org_id,
                released_scope.workspace_id, NULL,
                'worker.maintenance_scope_released', 'workspace',
                released_scope.workspace_id,
                jsonb_build_object('worker_id', released_scope.worker_id)::json,
                clock_timestamp()
            );
            RETURN true;
        END
        $function$
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.renew_worker_maintenance_scope(
            p_lease_seconds integer DEFAULT 300
        ) RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE renewed_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_lease_seconds IS NULL
               OR p_lease_seconds NOT BETWEEN 15 AND 300 THEN
                RETURN false;
            END IF;
            UPDATE agency_os_private.worker_workspace_capabilities AS cap
            SET expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds)
            FROM agency_os_private.worker_workspace_transaction_context AS ctx
            WHERE ctx.backend_pid = pg_backend_pid()
              AND ctx.transaction_id = txid_current()
              AND cap.id = ctx.capability_id
              AND cap.invalidated_at IS NULL
              AND cap.expires_at > clock_timestamp();
            GET DIAGNOSTICS renewed_count = ROW_COUNT;
            RETURN renewed_count = 1;
        END
        $function$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.invalidate_worker_execution_capability()
        RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE invalidated_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker' THEN
                RETURN false;
            END IF;
            UPDATE agency_os_private.worker_lease_capabilities AS cap
            SET invalidated_at = clock_timestamp()
            FROM agency_os_private.worker_transaction_context AS ctx
            WHERE ctx.backend_pid = pg_backend_pid()
              AND ctx.transaction_id = txid_current()
              AND cap.id = ctx.capability_id
              AND cap.invalidated_at IS NULL;
            GET DIAGNOSTICS invalidated_count = ROW_COUNT;
            RETURN invalidated_count = 1;
        END
        $function$
    """)

    worker_only_functions = (
        "claim_worker_maintenance_scope(text, integer, bytea, text)",
        "renew_worker_maintenance_scope(integer)",
        "invalidate_worker_execution_capability()",
        "establish_worker_workspace_context(bytea, text, text, text)",
        "release_worker_maintenance_scope()",
    )
    for signature in worker_only_functions:
        op.execute(f"ALTER FUNCTION agency_os_private.{signature} OWNER TO agency_os_migrator")
        op.execute(f"REVOKE ALL ON FUNCTION agency_os_private.{signature} FROM PUBLIC, agency_os_app")
        op.execute(f"GRANT EXECUTE ON FUNCTION agency_os_private.{signature} TO agency_os_worker")

    # RLS expressions invoke this predicate for every role; the app role must
    # be able to evaluate its false worker branch without gaining any capability.
    op.execute("ALTER FUNCTION agency_os_private.worker_has_workspace_context(text, text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.worker_has_workspace_context(text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.worker_has_workspace_context(text, text) TO agency_os_app, agency_os_worker")

    # The managed-agent tool adapter may read its own agent identity and update
    # only last_used_at. The row policy below binds both operations to the
    # current execution capability and its exact agent.
    op.execute("REVOKE ALL ON TABLE public.machine_identities FROM agency_os_worker")
    op.execute("GRANT SELECT ON TABLE public.machine_identities TO agency_os_worker")
    op.execute("GRANT UPDATE (last_used_at) ON TABLE public.machine_identities TO agency_os_worker")

    for table in WORKSPACE_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public."{table}"')
        human, machine, worker = _policy_parts(table)
        predicate = f"({human} OR {machine} OR {worker})"
        op.execute(
            f'CREATE POLICY tenant_isolation ON public."{table}" '
            f'USING ({predicate}) WITH CHECK ({predicate})'
        )

    op.execute("DROP POLICY IF EXISTS execution_attempt_tenant_isolation ON public.execution_attempts")
    attempts = """
        EXISTS (
            SELECT 1 FROM public.executions AS e
            WHERE e.id = execution_attempts.execution_id
              AND (
                agency_os_private.user_has_workspace_access(
                    e.org_id, e.workspace_id,
                    nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    session_user <> 'agency_os_worker'
                    AND e.org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND e.workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
                OR (
                    session_user = 'agency_os_worker'
                    AND (
                        agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id)
                        OR agency_os_private.worker_has_workspace_context(e.org_id, e.workspace_id)
                    )
                )
              )
        )
    """
    op.execute(
        f"CREATE POLICY execution_attempt_tenant_isolation ON public.execution_attempts "
        f"USING ({attempts}) WITH CHECK ({attempts})"
    )

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.workspaces")
    op.execute("DROP POLICY IF EXISTS workspace_select ON public.workspaces")
    workspace_predicate = """
        (
            agency_os_private.user_has_workspace_access(
                org_id, id, nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                session_user <> 'agency_os_worker'
                AND org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
            )
            OR (
                session_user = 'agency_os_worker'
                AND (
                    agency_os_private.worker_has_execution_context(org_id, id, NULL)
                    OR agency_os_private.worker_has_workspace_context(org_id, id)
                )
            )
        )
    """
    op.execute(
        f"CREATE POLICY workspace_select ON public.workspaces "
        f"FOR SELECT USING ({workspace_predicate})"
    )

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.organizations")
    org_predicate = """
        (
            agency_os_private.user_has_org_access(
                id, nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                session_user <> 'agency_os_worker'
                AND id = nullif(current_setting('agency_os.machine_org_id', true), '')
            )
            OR (
                session_user = 'agency_os_worker'
                AND EXISTS (
                    SELECT 1 FROM public.workspaces AS w
                    WHERE w.org_id = organizations.id
                      AND (
                        agency_os_private.worker_has_execution_context(w.org_id, w.id, NULL)
                        OR agency_os_private.worker_has_workspace_context(w.org_id, w.id)
                      )
                )
            )
        )
    """
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.organizations "
        f"USING ({org_predicate}) WITH CHECK ({org_predicate})"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: workspace capabilities are part of the worker RLS security boundary"
    )
