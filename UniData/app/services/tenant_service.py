"""应用租户 PostgreSQL schema 的生命周期管理。"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenant import tenant_schema
from app.models.open_platform import OpenPlatformApp


def _schema_sql(schema: str) -> str:
    # tenant_schema() 只生成 tenant_ + 十六进制字符，校验后才进入 DDL 标识符。
    if not schema.startswith("tenant_") or any(ch not in "0123456789abcdefghijklmnopqrstuvwxyz_" for ch in schema):
        raise ValueError("非法租户 schema")
    return schema


_CDC_ROLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _cdc_outbox_policy_sql(cdc_role: str) -> tuple[str, str]:
    """为 Debezium 复制角色创建 outbox 全量读策略（快照阶段需绕过 RLS）。"""
    if not _CDC_ROLE_PATTERN.fullmatch(cdc_role):
        raise ValueError("search_outbox_cdc_role 必须是合法的 PostgreSQL 角色名")
    return (
        "DROP POLICY IF EXISTS outbox_cdc_full_read ON public.search_outbox",
        # 角色可能尚未创建（如单元测试库），存在才建策略，避免 DDL 失败。
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{cdc_role}') THEN
                EXECUTE format(
                    'CREATE POLICY outbox_cdc_full_read ON public.search_outbox '
                    'FOR SELECT TO %I USING (true)',
                    '{cdc_role}'
                );
            END IF;
        END
        $$
        """,
    )


async def ensure_search_outbox(db: AsyncSession) -> None:
    """创建公共 outbox、序列、可复用的触发器函数，并启用 outbox 的 RLS。"""
    statements = (
        """
        CREATE SEQUENCE IF NOT EXISTS public.search_outbox_event_version_seq
        AS BIGINT
        """,
        """
        CREATE TABLE IF NOT EXISTS public.search_outbox (
            event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            app_id VARCHAR NOT NULL,
            collection VARCHAR NOT NULL,
            document_id VARCHAR NOT NULL,
            operation VARCHAR NOT NULL CHECK (operation IN ('upsert', 'delete')),
            document JSONB,
            event_version BIGINT NOT NULL DEFAULT nextval('public.search_outbox_event_version_seq'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        # 兼容早期手工/ORM 建表的 outbox：补齐默认值与序列类型，避免 CDC 触发器依赖表默认值。
        """
        ALTER TABLE public.search_outbox
            ALTER COLUMN event_id SET DEFAULT gen_random_uuid(),
            ALTER COLUMN event_version TYPE BIGINT USING event_version::bigint,
            ALTER COLUMN event_version SET DEFAULT nextval('public.search_outbox_event_version_seq'),
            ALTER COLUMN created_at SET DEFAULT NOW()
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'public.search_outbox'::regclass
                  AND conname = 'ck_search_outbox_operation'
            ) THEN
                ALTER TABLE public.search_outbox
                ADD CONSTRAINT ck_search_outbox_operation
                CHECK (operation IN ('upsert', 'delete'));
            END IF;
        END
        $$
        """,
        "CREATE INDEX IF NOT EXISTS ix_search_outbox_route ON public.search_outbox (app_id, collection, event_version)",
        # outbox 是全租户共享的 CDC 传输表：业务角色（含表 owner）经 RLS 只能读自己
        # 租户的行，防止共享连接角色被注入后拖走全部租户文档；Debezium 复制角色由
        # outbox_cdc_full_read 策略豁免（pgoutput 流式解码不受 RLS 影响，但快照 SELECT 需要）。
        "ALTER TABLE public.search_outbox ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE public.search_outbox FORCE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS outbox_tenant_isolation ON public.search_outbox",
        """
        CREATE POLICY outbox_tenant_isolation ON public.search_outbox
        USING (app_id = current_setting('app.tenant_id', true))
        WITH CHECK (app_id = current_setting('app.tenant_id', true))
        """,
        """
        CREATE OR REPLACE FUNCTION public.emit_search_outbox()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE
            operation_name TEXT;
            document_json JSONB;
            document_key TEXT;
            tenant_id TEXT;
            collection_name TEXT;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                tenant_id := OLD.app_id::TEXT;
                collection_name := OLD.collection::TEXT;
                document_key := OLD.id::TEXT;
            ELSE
                tenant_id := NEW.app_id::TEXT;
                collection_name := NEW.collection::TEXT;
                document_key := NEW.id::TEXT;
            END IF;
            IF tenant_id IS NULL OR tenant_id = '' OR collection_name IS NULL OR collection_name = '' OR document_key IS NULL OR document_key = '' THEN
                RAISE EXCEPTION 'search outbox route fields cannot be empty';
            END IF;

            IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND COALESCE(NEW.is_delete, FALSE)) THEN
                operation_name := 'delete';
                document_json := NULL;
            ELSE
                operation_name := 'upsert';
                document_json := COALESCE(NEW.payload, '{}'::jsonb) || jsonb_build_object('id', document_key);
            END IF;

            INSERT INTO public.search_outbox (event_id, app_id, collection, document_id, operation, document, event_version)
            VALUES (
                gen_random_uuid(),
                tenant_id,
                collection_name,
                document_key,
                operation_name,
                document_json,
                nextval('public.search_outbox_event_version_seq')
            );
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $function$
        """,
    )
    cdc_role = (get_settings().search_outbox_cdc_role or "").strip()
    if cdc_role:
        statements = statements + _cdc_outbox_policy_sql(cdc_role)
    for statement in statements:
        await db.execute(text(statement))


async def ensure_collection_settings_rls(db: AsyncSession) -> None:
    """为公共控制表增加租户级读写约束。"""
    statements = (
        "ALTER TABLE public.collection_settings ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE public.collection_settings FORCE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS collection_settings_tenant_isolation ON public.collection_settings",
        """
        CREATE POLICY collection_settings_tenant_isolation
        ON public.collection_settings
        USING (app_id = current_setting('app.tenant_id', true))
        WITH CHECK (app_id = current_setting('app.tenant_id', true))
        """,
    )
    for statement in statements:
        await db.execute(text(statement))


async def tenant_exists(db: AsyncSession, app_id: str) -> bool:
    """检查当前数据库中是否已创建租户 schema。"""
    if not isinstance(db, AsyncSession):
        return True
    schema = _schema_sql(tenant_schema(app_id))
    result = await db.execute(
        text("SELECT to_regnamespace(:schema_name) IS NOT NULL"),
        {"schema_name": schema},
    )
    return bool(result.scalar())


async def ensure_tenant(db: AsyncSession, app_id: str) -> str:
    """按会话懒初始化历史租户，避免旧应用在迁移窗口内访问失败。"""
    schema = _schema_sql(tenant_schema(app_id))
    if isinstance(db, AsyncSession) and await db.get(OpenPlatformApp, app_id) is None:
        raise ValueError(f"应用不存在，不能初始化租户: {app_id}")
    if not await tenant_exists(db, app_id):
        await provision_tenant(db, app_id)
    return schema


async def provision_tenant(db: AsyncSession, app_id: str) -> str:
    """幂等创建租户 schema、文档表、RLS 和 CDC trigger。"""
    schema = _schema_sql(tenant_schema(app_id))
    # 并发懒初始化同一租户时串行化 DDL：即使 IF NOT EXISTS，并发 CREATE TABLE /
    # DROP+CREATE POLICY 仍可能因 pg_type 唯一约束等竞争而失败。
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:schema))"),
        {"schema": schema},
    )
    await ensure_search_outbox(db)
    ddl = (
        f'CREATE SCHEMA IF NOT EXISTS "{schema}"',
        f'''
        CREATE TABLE IF NOT EXISTS "{schema}".uni_documents (
            row_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            id VARCHAR NOT NULL,
            app_id VARCHAR NOT NULL,
            collection VARCHAR NOT NULL,
            app_name VARCHAR NOT NULL,
            payload JSONB,
            is_delete BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT "ck_{schema}_app_id" CHECK (app_id = '{app_id.replace("'", "''")}'),
            CONSTRAINT "uq_{schema}_app_collection_id" UNIQUE (app_id, collection, id),
            CONSTRAINT "fk_{schema}_app_id" FOREIGN KEY (app_id) REFERENCES public.open_platform_apps(id) ON DELETE RESTRICT
        )
        ''',
        f'CREATE INDEX IF NOT EXISTS "ix_{schema}_app_collection" ON "{schema}".uni_documents (app_id, collection)',
        f'CREATE INDEX IF NOT EXISTS "ix_{schema}_collection_id" ON "{schema}".uni_documents (collection, id)',
        f'ALTER TABLE "{schema}".uni_documents REPLICA IDENTITY FULL',
        f'ALTER TABLE "{schema}".uni_documents ENABLE ROW LEVEL SECURITY',
        f'ALTER TABLE "{schema}".uni_documents FORCE ROW LEVEL SECURITY',
        f'''DROP POLICY IF EXISTS tenant_isolation ON "{schema}".uni_documents''',
        f'''
        CREATE POLICY tenant_isolation ON "{schema}".uni_documents
        USING (app_id = current_setting('app.tenant_id', true))
        WITH CHECK (app_id = current_setting('app.tenant_id', true))
        ''',
        f'''DROP TRIGGER IF EXISTS emit_search_outbox ON "{schema}".uni_documents''',
        f'''
        CREATE TRIGGER emit_search_outbox
        AFTER INSERT OR UPDATE OR DELETE ON "{schema}".uni_documents
        FOR EACH ROW EXECUTE FUNCTION public.emit_search_outbox()
        ''',
    )
    for statement in ddl:
        await db.execute(text(statement))
    return schema


async def drop_tenant(db: AsyncSession, app_id: str) -> str:
    schema = _schema_sql(tenant_schema(app_id))
    await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    return schema
