USE cmdb;
-- Force connection charset so Chinese strings are stored as utf8mb4, not
-- re-encoded from the client's default (often latin1) into the utf8mb4
-- columns — which would produce mojibake like "ç³»ç»Ÿç®¡ç¿".
SET NAMES utf8mb4;

-- Seed accounts (bcrypt hashes generated and verified with passlib bcrypt scheme).
-- admin    / admin123
-- operator / 123456
-- viewer   / 123456
INSERT INTO profiles (id, username, name, email, password_hash, role, enabled) VALUES
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'admin',    '系统管理员', 'admin@corp.local',    '$2b$12$R9pcrosiOLz82vHqhQLZkOMP7q8O4UqYPghQTFD.8icQdPc2yaTsC', 'admin',    1),
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'operator', '运维工程师', 'operator@corp.local', '$2b$12$7KU5SurJvbM6CEKQxYwLFuTFFk2yQFqLmTj3vhk9eyI2smaA9R9yy', 'operator', 1),
('cccccccc-cccc-cccc-cccc-cccccccccccc', 'viewer',   '只读访客',   'viewer@corp.local',   '$2b$12$FlZrHXRZlLQkYHyoED2HJegT3C1/ivv1Ne2AxOiTrxlBdwPHjxPgm', 'viewer',   1);

INSERT INTO servers (id, hostname, sn, asset_tag, manufacturer, model, cpu_model, cpu_count, memory_gb, disk_count, idc, rack, u_position, mgmt_ip, biz_ip, bmc_protocol, bmc_user, status, owner, purchase_date, warranty_end, tags, remark) VALUES
('11111111-0000-0000-0000-000000000001','bj-prod-web-01','CN7420A001','AS-2023-0001','Dell','PowerEdge R750','Intel Xeon Gold 6338 @ 2.0GHz',2,256,8,'BJ-IDC-A','A03','U12-U13','10.10.20.11','172.16.10.11','redfish','admin','online','infra-team','2023-03-15','2026-03-14',JSON_ARRAY('prod','web'),'前端反向代理'),
('11111111-0000-0000-0000-000000000002','bj-prod-db-01','CN7420A002','AS-2023-0002','HPE','ProLiant DL380 Gen10','Intel Xeon Gold 6248R @ 3.0GHz',2,512,12,'BJ-IDC-A','A04','U08-U09','10.10.20.12','172.16.10.12','redfish','Administrator','online','dba-team','2022-09-01','2025-08-31',JSON_ARRAY('prod','db','core'),'MySQL 主库'),
('11111111-0000-0000-0000-000000000003','sh-stg-app-01','CN7420A003','AS-2023-0003','Lenovo','ThinkSystem SR650','Intel Xeon Silver 4314 @ 2.4GHz',2,128,4,'SH-IDC-B','B11','U20-U21','10.20.30.13','172.16.20.13','ipmi','ADMIN','maintenance','app-team','2021-11-20','2024-11-19',JSON_ARRAY('stg','app'),NULL),
('11111111-0000-0000-0000-000000000004','bj-prod-cache-01','CN7420A004','AS-2024-0004','Inspur','NF5280M6','Intel Xeon Platinum 8358 @ 2.6GHz',2,384,6,'BJ-IDC-A','A05','U02-U03','10.10.20.14','172.16.10.14','redfish','admin','online','infra-team','2024-01-10','2027-01-09',JSON_ARRAY('prod','cache','redis'),NULL),
('11111111-0000-0000-0000-000000000005','sh-prod-gpu-01','CN7420A005','AS-2024-0005','Supermicro','AS-4124GS-TNR','AMD EPYC 7763 @ 2.45GHz',2,1024,8,'SH-IDC-B','B02','U30-U33','10.20.30.15','172.16.20.15','redfish','ADMIN','online','ai-team','2024-04-20','2027-04-19',JSON_ARRAY('prod','gpu','ai'),'8 卡 A100 训练机'),
('11111111-0000-0000-0000-000000000006','bj-test-build-01','CN7420A006','AS-2020-0006','Huawei','FusionServer 2288H V5','Intel Xeon Silver 4210 @ 2.2GHz',2,64,2,'BJ-IDC-A','A09','U18','10.10.20.16','172.16.10.16','ipmi','root','offline','devops-team','2020-06-12','2023-06-11',JSON_ARRAY('test','ci'),'Jenkins 构建机，已过保'),
('11111111-0000-0000-0000-000000000007','bj-prod-storage-01','CN7420A007','AS-2023-0007','Dell','PowerEdge R740xd','Intel Xeon Gold 6230R @ 2.1GHz',2,192,24,'BJ-IDC-A','A06','U24-U25','10.10.20.17','172.16.10.17','redfish','admin','online','storage-team','2023-07-08','2026-07-07',JSON_ARRAY('prod','storage','ceph'),NULL),
('11111111-0000-0000-0000-000000000008','gz-prod-edge-01','CN7420A008','AS-2024-0008','Lenovo','ThinkSystem SR630','Intel Xeon Silver 4310 @ 2.1GHz',2,96,4,'GZ-IDC-C','C01','U05','10.30.40.18','172.16.30.18','redfish','admin','retired','edge-team','2019-02-22','2022-02-21',JSON_ARRAY('edge'),'已下架待回收');

INSERT INTO parts (id, category, brand, model, spec, stock, safety_stock, unit, location, status, remark) VALUES
('22222222-0000-0000-0000-000000000001','disk','Samsung','PM9A3','1.92TB U.2 NVMe SSD',18,10,'块','BJ 备件库 A-2-1','in_stock',NULL),
('22222222-0000-0000-0000-000000000002','disk','Seagate','ST16000NM001G','16TB 7200rpm SATA HDD',6,8,'块','BJ 备件库 A-2-2','in_stock','库存低于安全线'),
('22222222-0000-0000-0000-000000000003','memory','Micron','MTA36ASF8G72PZ','64GB DDR4-3200 RDIMM',32,16,'条','BJ 备件库 B-1-1','in_stock',NULL),
('22222222-0000-0000-0000-000000000004','memory','Samsung','M393A4K40DB3-CWE','32GB DDR4-3200 RDIMM',12,20,'条','BJ 备件库 B-1-2','in_stock','库存低于安全线'),
('22222222-0000-0000-0000-000000000005','nic','Mellanox','MCX516A-CCAT','ConnectX-5 双口 100GbE',8,4,'块','BJ 备件库 C-1-1','in_stock',NULL),
('22222222-0000-0000-0000-000000000006','nic','Intel','X710-DA2','双口 10GbE SFP+',14,6,'块','BJ 备件库 C-1-2','in_stock',NULL),
('22222222-0000-0000-0000-000000000007','optical','Finisar','FTLX8574D3BCL','10G SFP+ SR 850nm 300m',50,20,'个','BJ 备件库 D-1-1','in_stock',NULL),
('22222222-0000-0000-0000-000000000008','optical','InnoLight','TR-FC85S-N00','100G QSFP28 SR4 100m',22,10,'个','BJ 备件库 D-1-2','in_stock',NULL),
('22222222-0000-0000-0000-000000000009','optical','InnoLight','TR-FC13L-N00','10G SFP+ LR 1310nm 10km',4,10,'个','BJ 备件库 D-1-3','in_stock','库存严重不足'),
('22222222-0000-0000-0000-000000000010','other','Dell','PERC H755','12Gb SAS RAID 卡',5,2,'块','BJ 备件库 E-1-1','in_stock',NULL);

INSERT INTO stock_movements (id, part_id, type, quantity, operator, related_server_id, reason, created_at) VALUES
('33333333-0000-0000-0000-000000000001','22222222-0000-0000-0000-000000000001','inbound',20,'zhang.wei',NULL,'2024 Q2 采购入库','2024-04-12 09:21:00'),
('33333333-0000-0000-0000-000000000002','22222222-0000-0000-0000-000000000001','outbound',2,'li.ming','11111111-0000-0000-0000-000000000002','DB 主库扩容','2024-05-03 14:11:00'),
('33333333-0000-0000-0000-000000000003','22222222-0000-0000-0000-000000000004','outbound',8,'li.ming','11111111-0000-0000-0000-000000000001','Web 节点内存升级','2024-05-15 10:30:00'),
('33333333-0000-0000-0000-000000000004','22222222-0000-0000-0000-000000000007','inbound',50,'wang.fang',NULL,'光模块批次到货','2024-06-01 08:00:00'),
('33333333-0000-0000-0000-000000000005','22222222-0000-0000-0000-000000000009','outbound',6,'li.ming','11111111-0000-0000-0000-000000000007','Ceph 跨机房互联','2024-06-12 16:42:00'),
('33333333-0000-0000-0000-000000000006','22222222-0000-0000-0000-000000000006','return',1,'zhao.lei','11111111-0000-0000-0000-000000000003','故障返修后归还','2024-06-20 11:05:00'),
('33333333-0000-0000-0000-000000000007','22222222-0000-0000-0000-000000000002','scrap',2,'zhang.wei',NULL,'坏盘报废','2024-07-01 09:00:00');

INSERT INTO audit_logs (id, actor, action, target, detail, level, created_at) VALUES
(UUID(),'admin','user.login','session','管理员登录系统','info','2024-07-10 08:30:12'),
(UUID(),'li.ming','server.update','srv:bj-prod-db-01','修改备注信息','info','2024-07-09 17:45:00'),
(UUID(),'admin','role.update','user:viewer.zhao','调整角色：viewer → operator','warn','2024-06-28 14:12:00'),
(UUID(),'system','bmc.alert','srv:bj-prod-cache-01','BMC 心跳异常 30s 自动恢复','warn','2024-06-25 03:11:00'),
(UUID(),'admin','server.create','srv:gz-prod-edge-01','录入边缘节点资产','info','2024-06-20 10:00:00');
