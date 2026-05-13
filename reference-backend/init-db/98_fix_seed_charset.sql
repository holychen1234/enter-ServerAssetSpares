-- Hot-fix: rewrite Chinese fields that were corrupted because the initial
-- seed ran with a non-utf8mb4 client connection. Run this AFTER applying
-- the docker-compose charset change. Idempotent.
USE cmdb;
SET NAMES utf8mb4;

UPDATE profiles SET name = '系统管理员' WHERE username = 'admin';
UPDATE profiles SET name = '运维工程师' WHERE username = 'operator';
UPDATE profiles SET name = '只读访客'   WHERE username = 'viewer';

-- Verify
SELECT username, name, email FROM profiles;
