-- BMC snapshots: persisted daily collection so the UI never shows simulated data.
CREATE TABLE IF NOT EXISTS bmc_snapshots (
    id          CHAR(36)     NOT NULL PRIMARY KEY,
    server_id   CHAR(36)     NOT NULL,
    collected_at DATETIME    NOT NULL DEFAULT (UTC_TIMESTAMP()),
    source      VARCHAR(16)  NOT NULL DEFAULT 'live',
    protocol    VARCHAR(16)  NULL,
    power       VARCHAR(8)   NULL,
    health      VARCHAR(16)  NULL,
    cpu_temp_c  INT          NULL,
    inlet_temp_c INT         NULL,
    processor_summary JSON   NULL,
    memory_summary    JSON   NULL,
    memory_modules    JSON   NULL,
    drives            JSON   NULL,
    fans              JSON   NULL,
    psus              JSON   NULL,
    recent_logs       JSON   NULL,
    history           JSON   NULL,
    alerts            JSON   NULL,
    CONSTRAINT fk_bmc_snapshots_server
        FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_bmc_snapshots_server_time
    ON bmc_snapshots (server_id, collected_at DESC);
