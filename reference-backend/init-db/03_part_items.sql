-- ================================================================
-- Migration: add per-item spare parts tracking (part_items table)
-- ================================================================
-- Run AFTER 01_schema.sql has been executed (the part_items and
-- altered stock_movements tables should already exist).
--
-- This script backfills part_items rows for existing Parts that
-- have stock > 0, so historical inventory counts are preserved.
-- Newly-created part_items will have NULL SN (operators can
-- backfill SNs later via the PartDetail UI).
-- ================================================================
USE cmdb;
SET NAMES utf8mb4;

-- Create a stored procedure that creates N part_item rows per Part
-- where stock > 0. Each Part gets stock-many rows with NULL SN.
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

-- Verify: part stock counts should match item counts
SELECT 'part_items backfill complete' AS message;
SELECT p.id, p.brand, p.model, p.stock AS old_stock,
       COUNT(pi.id) AS item_count
FROM parts p
LEFT JOIN part_items pi ON pi.part_id = p.id
GROUP BY p.id
HAVING p.stock != COUNT(pi.id);
