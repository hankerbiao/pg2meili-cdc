-- 启用 UUID 扩展（可选，如果 id 未来转为 UUID 类型）
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 创建自动更新 updated_at 字段的触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- =============================================
-- 表名: test_cases
-- 描述: 存储测试用例及相关业务数据的原始信息
-- =============================================
CREATE TABLE IF NOT EXISTS test_cases (
    -- id: 业务主键
    -- 对应 JSON 中的 "id" 字段。
    -- 建议在应用层确保 ID 的唯一性
    id TEXT PRIMARY KEY,

    -- payload: 核心数据字段
    -- 使用 JSONB 存储完整的业务 JSON 对象。
    -- 优势：
    -- 1. 灵活适应字段增减（Schema-less）。
    -- 2. PostgreSQL 对 JSONB 提供二进制存储和高效解析。
    -- 3. 支持对 JSON 内部字段建立索引。
    payload JSONB NOT NULL,

    -- created_at: 入库时间
    -- 记录数据首次插入数据库的时间，默认为当前事务时间。
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- updated_at: 最后更新时间
    -- 记录数据最后一次被修改的时间。
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================
-- 索引设计
-- =============================================

-- 1. GIN 索引 (通用 JSON 索引)
-- 作用：加速对 payload 中任意键值对的查询。
-- 示例查询：SELECT * FROM test_cases WHERE payload @> '{"author": "张欢"}';
CREATE INDEX IF NOT EXISTS idx_test_cases_payload ON test_cases USING gin (payload);

-- 2. 表达式索引 (针对高频查询字段优化)
-- 如果某些字段查询非常频繁（如 status, ext_id），建议创建独立的表达式索引，性能优于通用的 GIN 索引。

-- 示例：针对 "ext_id" (外部ID) 的索引
CREATE INDEX IF NOT EXISTS idx_test_cases_ext_id ON test_cases ((payload->>'ext_id'));

-- 示例：针对 "status" (状态) 的索引
CREATE INDEX IF NOT EXISTS idx_test_cases_status ON test_cases ((payload->>'status'));

-- 示例：针对 "name" (名称) 的索引
CREATE INDEX IF NOT EXISTS idx_test_cases_name ON test_cases ((payload->>'name'));

-- =============================================
-- 触发器
-- =============================================

-- 应用触发器：当行更新时自动刷新 updated_at 为当前时间
CREATE TRIGGER update_test_cases_updated_at
    BEFORE UPDATE ON test_cases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
