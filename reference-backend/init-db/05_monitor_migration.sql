-- Migration: add monitor category + workstation linkage to parts system
USE cmdb;
SET NAMES utf8mb4;

-- Add "monitor" to part_category enum
ALTER TABLE parts MODIFY COLUMN category ENUM('disk','memory','nic','optical','monitor','other') NOT NULL;

-- Add installed_workstation_id to part_items
ALTER TABLE part_items ADD COLUMN installed_workstation_id CHAR(36) NULL,
    ADD INDEX idx_part_items_ws (installed_workstation_id),
    ADD CONSTRAINT fk_part_items_ws FOREIGN KEY (installed_workstation_id) REFERENCES workstations(id) ON DELETE SET NULL;

-- Add related_workstation_id to stock_movements
ALTER TABLE stock_movements ADD COLUMN related_workstation_id CHAR(36) NULL,
    ADD INDEX idx_movements_ws (related_workstation_id),
    ADD CONSTRAINT fk_movements_ws FOREIGN KEY (related_workstation_id) REFERENCES workstations(id) ON DELETE SET NULL;
