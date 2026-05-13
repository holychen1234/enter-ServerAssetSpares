-- Hot-fix script: reset the three seed accounts' passwords to the documented
-- defaults. Use this when an existing deployment was initialized with the old
-- broken bcrypt hashes.
--
-- How to apply (no data loss):
--   docker compose exec -T mysql mysql -ucmdb -pcmdb123 cmdb < init-db/99_fix_seed_passwords.sql

USE cmdb;

UPDATE profiles SET password_hash = '$2b$12$R9pcrosiOLz82vHqhQLZkOMP7q8O4UqYPghQTFD.8icQdPc2yaTsC'
  WHERE username = 'admin';

UPDATE profiles SET password_hash = '$2b$12$7KU5SurJvbM6CEKQxYwLFuTFFk2yQFqLmTj3vhk9eyI2smaA9R9yy'
  WHERE username = 'operator';

UPDATE profiles SET password_hash = '$2b$12$FlZrHXRZlLQkYHyoED2HJegT3C1/ivv1Ne2AxOiTrxlBdwPHjxPgm'
  WHERE username = 'viewer';

SELECT username, role, enabled, LEFT(password_hash, 7) AS hash_prefix FROM profiles;
