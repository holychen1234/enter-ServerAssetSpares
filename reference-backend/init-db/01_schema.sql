CREATE DATABASE IF NOT EXISTS cmdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cmdb;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS profiles (
  id                        CHAR(36)      NOT NULL PRIMARY KEY,
  username                  VARCHAR(64)   NOT NULL UNIQUE,
  name                      VARCHAR(64)   NOT NULL,
  email                     VARCHAR(128)  NOT NULL,
  password_hash             VARCHAR(255)  NOT NULL,
  role                      ENUM('admin','operator','viewer') NOT NULL DEFAULT 'viewer',
  enabled                   TINYINT(1)    NOT NULL DEFAULT 1,
  is_deleted                TINYINT(1)    NOT NULL DEFAULT 0,
  password_change_required  TINYINT(1)    NOT NULL DEFAULT 0,
  failed_login_attempts     INT           NOT NULL DEFAULT 0,
  locked_until              DATETIME      NULL,
  last_login                DATETIME      NULL,
  created_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS servers (
  id             CHAR(36)     NOT NULL PRIMARY KEY,
  hostname       VARCHAR(128) NOT NULL,
  sn             VARCHAR(64)  NOT NULL UNIQUE,
  asset_tag      VARCHAR(64)  NOT NULL UNIQUE,
  manufacturer   VARCHAR(32)  NOT NULL,
  model          VARCHAR(64)  NOT NULL,
  cpu_model      VARCHAR(128) NOT NULL,
  cpu_count      INT          NOT NULL DEFAULT 1,
  memory_gb      INT          NOT NULL DEFAULT 0,
  disk_count     INT          NOT NULL DEFAULT 0,
  idc            VARCHAR(64)  NOT NULL,
  rack           VARCHAR(32)  NOT NULL,
  u_position     VARCHAR(32)  NOT NULL,
  mgmt_ip        VARCHAR(64)  NOT NULL,
  biz_ip         VARCHAR(64)  NOT NULL,
  bmc_protocol   ENUM('redfish','ipmi') NOT NULL DEFAULT 'redfish',
  bmc_user       VARCHAR(64)  NOT NULL DEFAULT 'admin',
  bmc_password   VARCHAR(255) NULL,
  status         ENUM('online','offline','maintenance','retired') NOT NULL DEFAULT 'online',
  owner          VARCHAR(64)  NULL,
  purchase_date  DATE         NULL,
  warranty_end   DATE         NULL,
  tags           JSON         NULL,
  remark         TEXT         NULL,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_servers_status (status),
  INDEX idx_servers_idc (idc),
  INDEX idx_servers_brand (manufacturer)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS parts (
  id           CHAR(36)     NOT NULL PRIMARY KEY,
  category     ENUM('disk','memory','nic','optical','other') NOT NULL,
  brand        VARCHAR(64)  NOT NULL,
  model        VARCHAR(128) NOT NULL,
  spec         VARCHAR(255) NOT NULL,
  sn           VARCHAR(128) NULL,
  stock        INT          NOT NULL DEFAULT 0,
  safety_stock INT          NOT NULL DEFAULT 0,
  unit         VARCHAR(16)  NOT NULL DEFAULT '块',
  location     VARCHAR(128) NOT NULL,
  status       ENUM('in_stock','allocated','in_use','scrapped') NOT NULL DEFAULT 'in_stock',
  remark       TEXT         NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_parts_category (category),
  CHECK (stock >= 0)
) ENGINE=InnoDB;

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

CREATE TABLE IF NOT EXISTS stock_movements (
  id                  CHAR(36)     NOT NULL PRIMARY KEY,
  part_id             CHAR(36)     NOT NULL,
  part_item_id        CHAR(36)     NULL,
  type                ENUM('inbound','outbound','return','scrap') NOT NULL,
  quantity            INT          NOT NULL,
  operator            VARCHAR(64)  NOT NULL,
  related_server_id   CHAR(36)     NULL,
  reason              VARCHAR(255) NOT NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_movement_part      FOREIGN KEY (part_id)           REFERENCES parts(id) ON DELETE CASCADE,
  CONSTRAINT fk_movement_part_item FOREIGN KEY (part_item_id)      REFERENCES part_items(id) ON DELETE SET NULL,
  CONSTRAINT fk_movement_server    FOREIGN KEY (related_server_id) REFERENCES servers(id) ON DELETE SET NULL,
  INDEX idx_movements_part      (part_id),
  INDEX idx_movements_part_item (part_item_id),
  INDEX idx_movements_server    (related_server_id),
  INDEX idx_movements_time      (created_at DESC),
  CHECK (quantity > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_logs (
  id          CHAR(36)     NOT NULL PRIMARY KEY,
  actor       VARCHAR(64)  NOT NULL,
  action      VARCHAR(64)  NOT NULL,
  target      VARCHAR(128) NOT NULL,
  detail      TEXT         NULL,
  level       ENUM('info','warn','danger') NOT NULL DEFAULT 'info',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_audit_time (created_at DESC)
) ENGINE=InnoDB;
