-- ================================================================
-- Migration: part_items DDL + stock_movements alter + backfill
-- ================================================================
-- Run this on an EXISTING deployment to upgrade the database for
-- per-item spare parts tracking.
--
-- Usage (on private deployment server):
--   docker compose -f docker-compose.yml -p cmdb exec -T mysql \
--     mysql -u cmdb -p'YOUR_PASSWORD' cmdb < reference-backend/init-db/03_part_items.sql
-- ================================================================
USE cmdb;
SET NAMES utf8mb4;

-- ── 1. Create part_items table (if not already present) ──────────
CREATE TABLE IF NOT EXISTS part_items (
  id                   CHAR(36)     NOT NULL PRIMARY KEY,
  part_id              CHAR(36)     NOT NULL,
  sn                   VARCHAR(128) NULL UNIQUE,
  status               ENUM('in_stock','allocated','in_use','scrapped') NOT NULL DEFAULT 'in_stock',
  location             VARCHAR(128) NULL,
  installed_server_id  CHAR(36)     NULL,
  remark               TEXT         NULL,
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_part_item_part    FOREIGN KEY (part_id)             REFERENCES parts(id) ON DELETE CASCADE,
  CONSTRAINT fk_part_item_server  FOREIGN KEY (installed_server_id) REFERENCES servers(id) ON DELETE SET NULL,
  INDEX idx_part_items_part   (part_id),
  INDEX idx_part_items_status (status),
  INDEX idx_part_items_server (installed_server_id)
) ENGINE=InnoDB;

-- ── 2. Add part_item_id to stock_movements (if not already) ──────
-- MySQL 8.0 does not support ADD COLUMN IF NOT EXISTS, so we catch
-- the "Duplicate column" error with a no-op handler.
DROP PROCEDURE IF EXISTS add_part_item_id_col;

DELIMITER //
CREATE PROCEDURE add_part_item_id_col()
BEGIN
  DECLARE CONTINUE HANDLER FOR 1060 BEGIN END;
  ALTER TABLE stock_movements
    ADD COLUMN part_item_id CHAR(36) NULL AFTER part_id,
    ADD INDEX idx_movements_part_item (part_item_id),
    ADD CONSTRAINT fk_movement_part_item
      FOREIGN KEY (part_item_id) REFERENCES part_items(id) ON DELETE SET NULL;
END //
DELIMITER ;

CALL add_part_item_id_col();
DROP PROCEDURE IF EXISTS add_part_item_id_col;

-- ── 3. Backfill part_items from existing Parts ───────────────────
DROP PROCEDURE IF EXISTS backfill_part_items;

DELIMITER //
CREATE PROCEDURE backfill_part_items()
BEGIN
  DECLARE done INT DEFAULT 0;
  DECLARE v_part_id CHAR(36);
  DECLARE v_stock INT;
  DECLARE v_location VARCHAR(128);
  DECLARE i INT;
  DECLARE cur CURSOR FOR
    SELECT id, stock, location FROM parts WHERE stock > 0;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO v_part_id, v_stock, v_location;
    IF done THEN
      LEAVE read_loop;
    END IF;

    SET i = 0;
    WHILE i < v_stock DO
      INSERT IGNORE INTO part_items (id, part_id, sn, status, location)
      VALUES (UUID(), v_part_id, NULL, 'in_stock', v_location);
      SET i = i + 1;
    END WHILE;
  END LOOP;
  CLOSE cur;
END //
DELIMITER ;

CALL backfill_part_items();
DROP PROCEDURE IF EXISTS backfill_part_items;

-- ── 4. Verify ────────────────────────────────────────────────────
SELECT 'Migration complete' AS status;
SELECT p.id, p.brand, p.model, p.stock AS old_stock,
       COUNT(pi.id) AS item_count
FROM parts p
LEFT JOIN part_items pi ON pi.part_id = p.id
GROUP BY p.id
HAVING p.stock != COUNT(pi.id);
