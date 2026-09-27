-- MySQL dump 10.13  Distrib 8.0.41, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: skybeat
-- ------------------------------------------------------
-- Server version	8.0.41

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `admin_sessions`
--

DROP TABLE IF EXISTS `admin_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `admin_sessions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `session_hash` binary(32) NOT NULL,
  `google_sub` varchar(255) NOT NULL,
  `email` varchar(320) NOT NULL,
  `hosted_domain` varchar(253) DEFAULT NULL,
  `issued_at` datetime(6) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `last_used_at` datetime(6) NOT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `authorization_policy_version` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_admin_sessions_session_hash` (`session_hash`),
  KEY `ix_admin_sessions_expiry` (`expires_at`),
  KEY `ix_admin_sessions_last_used` (`last_used_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `admin_sessions`
--

LOCK TABLES `admin_sessions` WRITE;
/*!40000 ALTER TABLE `admin_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `admin_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('a58c71d904ef');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `alert_events`
--

DROP TABLE IF EXISTS `alert_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alert_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_uuid` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `incident_id` bigint unsigned NOT NULL,
  `device_id` bigint unsigned NOT NULL,
  `event_kind` varchar(32) NOT NULL,
  `occurred_at` datetime(6) NOT NULL,
  `detected_at` datetime(6) NOT NULL,
  `project_name_snapshot` varchar(128) NOT NULL,
  `device_name_snapshot` varchar(128) NOT NULL,
  `reason_snapshot` varchar(128) DEFAULT NULL,
  `details` json NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_alert_events_event_uuid` (`event_uuid`),
  UNIQUE KEY `uq_alert_events_incident_kind` (`incident_id`,`event_kind`),
  KEY `ix_alert_events_device_occurred` (`device_id`,`occurred_at`),
  CONSTRAINT `fk_alert_events_device_id_devices` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_alert_events_incident_id_incidents` FOREIGN KEY (`incident_id`) REFERENCES `incidents` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_alert_events_ck_alert_events_kind` CHECK ((`event_kind` in (_utf8mb4'DEVICE_OFFLINE',_utf8mb4'DEVICE_RECOVERED',_utf8mb4'GPU_DEGRADED',_utf8mb4'GPU_RECOVERED')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alert_events`
--

LOCK TABLES `alert_events` WRITE;
/*!40000 ALTER TABLE `alert_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `alert_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `audit_events`
--

DROP TABLE IF EXISTS `audit_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `actor` varchar(128) NOT NULL,
  `action` varchar(64) NOT NULL,
  `project_id` bigint unsigned DEFAULT NULL,
  `device_id` bigint unsigned DEFAULT NULL,
  `occurred_at` datetime(6) NOT NULL,
  `details` json NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_audit_events_project_id_projects` (`project_id`),
  KEY `ix_audit_events_device_id` (`device_id`),
  KEY `ix_audit_events_occurred_at` (`occurred_at`),
  CONSTRAINT `fk_audit_events_device_id_devices` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_audit_events_project_id_projects` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_events`
--

LOCK TABLES `audit_events` WRITE;
/*!40000 ALTER TABLE `audit_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `audit_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `device_credentials`
--

DROP TABLE IF EXISTS `device_credentials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `device_credentials` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `credential_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `device_id` bigint unsigned NOT NULL,
  `token_digest` binary(32) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `expires_at` datetime(6) DEFAULT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `last_used_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_device_credentials_credential_id` (`credential_id`),
  KEY `ix_credentials_device_lifecycle` (`device_id`,`revoked_at`,`expires_at`),
  CONSTRAINT `fk_device_credentials_device_id_devices` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `device_credentials`
--

LOCK TABLES `device_credentials` WRITE;
/*!40000 ALTER TABLE `device_credentials` DISABLE KEYS */;
/*!40000 ALTER TABLE `device_credentials` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `device_latest`
--

DROP TABLE IF EXISTS `device_latest`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `device_latest` (
  `device_id` bigint unsigned NOT NULL,
  `heartbeat_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `received_at` datetime(6) NOT NULL,
  `collected_at` datetime(6) NOT NULL,
  `schema_version` bigint unsigned NOT NULL,
  `agent_version` varchar(64) NOT NULL,
  `hostname` varchar(253) NOT NULL,
  `primary_ip` varchar(45) DEFAULT NULL,
  `cpu_percent` float DEFAULT NULL,
  `memory_percent` float DEFAULT NULL,
  `disk_summary` json NOT NULL,
  `gpu_summary` json NOT NULL,
  `payload` json NOT NULL,
  PRIMARY KEY (`device_id`),
  CONSTRAINT `fk_device_latest_device_id_devices` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `device_latest`
--

LOCK TABLES `device_latest` WRITE;
/*!40000 ALTER TABLE `device_latest` DISABLE KEYS */;
/*!40000 ALTER TABLE `device_latest` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `devices`
--

DROP TABLE IF EXISTS `devices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `devices` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `device_uuid` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `project_id` bigint unsigned NOT NULL,
  `name` varchar(128) NOT NULL,
  `monitoring_enabled` tinyint(1) NOT NULL,
  `monitoring_started_at` datetime(6) NOT NULL,
  `last_seen_at` datetime(6) DEFAULT NULL,
  `gpu_monitoring_enabled` tinyint(1) NOT NULL,
  `expected_gpu_min_count` bigint unsigned NOT NULL,
  `expected_gpu_uuids` json NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `availability_state` varchar(16) NOT NULL DEFAULT 'ONLINE',
  `gpu_effective_state` varchar(32) NOT NULL DEFAULT 'OK',
  `gpu_failure_streak` bigint unsigned NOT NULL DEFAULT '0',
  `gpu_ok_streak` bigint unsigned NOT NULL DEFAULT '0',
  `gpu_last_sample_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_devices_device_uuid` (`device_uuid`),
  KEY `ix_devices_project_id` (`project_id`),
  CONSTRAINT `fk_devices_project_id_projects` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_devices_ck_devices_state` CHECK ((`availability_state` in (_utf8mb4'ONLINE',_utf8mb4'SUSPECT',_utf8mb4'OFFLINE'))),
  CONSTRAINT `ck_devices_disabled_gpu_policy` CHECK (((0 <> `gpu_monitoring_enabled`) or ((`expected_gpu_min_count` = 0) and (json_length(`expected_gpu_uuids`) = 0)))),
  CONSTRAINT `ck_devices_gpu_count` CHECK ((`expected_gpu_min_count` between 0 and 64)),
  CONSTRAINT `ck_devices_gpu_inventory` CHECK (((json_type(`expected_gpu_uuids`) = _utf8mb4'ARRAY') and (json_length(`expected_gpu_uuids`) <= 64))),
  CONSTRAINT `ck_devices_gpu_monitoring` CHECK ((`gpu_monitoring_enabled` in (0,1))),
  CONSTRAINT `ck_devices_monitoring` CHECK ((`monitoring_enabled` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `devices`
--

LOCK TABLES `devices` WRITE;
/*!40000 ALTER TABLE `devices` DISABLE KEYS */;
/*!40000 ALTER TABLE `devices` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `heartbeat_receipts`
--

DROP TABLE IF EXISTS `heartbeat_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `heartbeat_receipts` (
  `device_id` bigint unsigned NOT NULL,
  `heartbeat_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `payload_hash` tinyblob NOT NULL,
  `received_at` datetime(6) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `response_payload` json NOT NULL,
  PRIMARY KEY (`device_id`,`heartbeat_id`),
  KEY `ix_heartbeat_receipts_expires_at` (`expires_at`),
  CONSTRAINT `fk_heartbeat_receipts_device_id_devices` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `heartbeat_receipts`
--

LOCK TABLES `heartbeat_receipts` WRITE;
/*!40000 ALTER TABLE `heartbeat_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `heartbeat_receipts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `heartbeat_samples`
--

DROP TABLE IF EXISTS `heartbeat_samples`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `heartbeat_samples` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `device_id` bigint unsigned NOT NULL,
  `heartbeat_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `received_at` datetime(6) NOT NULL,
  `collected_at` datetime(6) NOT NULL,
  `schema_version` bigint unsigned NOT NULL,
  `agent_version` varchar(64) NOT NULL,
  `payload` json NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_heartbeat_samples_device_received` (`device_id`,`received_at`),
  KEY `ix_heartbeat_samples_received_at` (`received_at`),
  CONSTRAINT `fk_heartbeat_samples_device_id_devices` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `heartbeat_samples`
--

LOCK TABLES `heartbeat_samples` WRITE;
/*!40000 ALTER TABLE `heartbeat_samples` DISABLE KEYS */;
/*!40000 ALTER TABLE `heartbeat_samples` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `incidents`
--

DROP TABLE IF EXISTS `incidents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `incidents` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `incident_uuid` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `device_id` bigint unsigned NOT NULL,
  `incident_type` varchar(32) NOT NULL,
  `opened_at` datetime(6) NOT NULL,
  `detected_at` datetime(6) NOT NULL,
  `closed_at` datetime(6) DEFAULT NULL,
  `close_reason` varchar(64) DEFAULT NULL,
  `current_reason` varchar(64) DEFAULT NULL,
  `active_key` varchar(128) GENERATED ALWAYS AS ((case when (`closed_at` is null) then concat(`device_id`,_utf8mb4':',`incident_type`) else NULL end)) STORED,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_incidents_incident_uuid` (`incident_uuid`),
  UNIQUE KEY `uq_incidents_active_key` (`active_key`),
  KEY `ix_incidents_device_type_closed` (`device_id`,`incident_type`,`closed_at`),
  CONSTRAINT `fk_incidents_device_id_devices` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_incidents_ck_incidents_type` CHECK ((`incident_type` in (_utf8mb4'AVAILABILITY',_utf8mb4'GPU')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `incidents`
--

LOCK TABLES `incidents` WRITE;
/*!40000 ALTER TABLE `incidents` DISABLE KEYS */;
/*!40000 ALTER TABLE `incidents` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notification_attempts`
--

DROP TABLE IF EXISTS `notification_attempts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notification_attempts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `delivery_id` bigint unsigned NOT NULL,
  `attempt_no` bigint unsigned NOT NULL,
  `started_at` datetime(6) NOT NULL,
  `finished_at` datetime(6) DEFAULT NULL,
  `outcome` varchar(32) DEFAULT NULL,
  `error_category` varchar(64) DEFAULT NULL,
  `provider_message_id` varchar(256) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_notification_attempts_delivery_attempt` (`delivery_id`,`attempt_no`),
  CONSTRAINT `fk_notification_attempts_delivery_id_notification_deliveries` FOREIGN KEY (`delivery_id`) REFERENCES `notification_deliveries` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notification_attempts`
--

LOCK TABLES `notification_attempts` WRITE;
/*!40000 ALTER TABLE `notification_attempts` DISABLE KEYS */;
/*!40000 ALTER TABLE `notification_attempts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notification_deliveries`
--

DROP TABLE IF EXISTS `notification_deliveries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notification_deliveries` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `delivery_uuid` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `event_id` bigint unsigned NOT NULL,
  `channel` varchar(16) NOT NULL,
  `recipient_key` varchar(64) NOT NULL,
  `destination_snapshot` varchar(320) NOT NULL,
  `provider_name` varchar(64) NOT NULL,
  `status` varchar(16) NOT NULL,
  `attempt_count` bigint unsigned NOT NULL,
  `next_attempt_at` datetime(6) DEFAULT NULL,
  `expires_at` datetime(6) NOT NULL,
  `lease_token` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `lease_expires_at` datetime(6) DEFAULT NULL,
  `superseded_at` datetime(6) DEFAULT NULL,
  `last_error_category` varchar(64) DEFAULT NULL,
  `provider_message_id` varchar(256) DEFAULT NULL,
  `cancel_reason` varchar(64) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_notification_deliveries_delivery_uuid` (`delivery_uuid`),
  UNIQUE KEY `uq_notification_deliveries_event_channel_recipient` (`event_id`,`channel`,`recipient_key`),
  KEY `ix_notification_deliveries_due` (`status`,`next_attempt_at`),
  KEY `ix_notification_deliveries_lease` (`status`,`lease_expires_at`),
  CONSTRAINT `fk_notification_deliveries_event_id_alert_events` FOREIGN KEY (`event_id`) REFERENCES `alert_events` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_notification_deliveries_ck_notification_deliveries_channel` CHECK ((`channel` in (_utf8mb4'EMAIL',_utf8mb4'SMS'))),
  CONSTRAINT `ck_notification_deliveries_ck_notification_deliveries_status` CHECK ((`status` in (_utf8mb4'PENDING',_utf8mb4'IN_PROGRESS',_utf8mb4'RETRY_WAIT',_utf8mb4'SUCCEEDED',_utf8mb4'FAILED',_utf8mb4'CANCELLED')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notification_deliveries`
--

LOCK TABLES `notification_deliveries` WRITE;
/*!40000 ALTER TABLE `notification_deliveries` DISABLE KEYS */;
/*!40000 ALTER TABLE `notification_deliveries` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `oauth_transactions`
--

DROP TABLE IF EXISTS `oauth_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `oauth_transactions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `state_hash` binary(32) NOT NULL,
  `nonce_hash` binary(32) NOT NULL,
  `nonce_ciphertext` blob NOT NULL,
  `browser_binding_hash` binary(32) NOT NULL,
  `pkce_verifier_ciphertext` blob NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `consumed_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_oauth_transactions_state_hash` (`state_hash`),
  KEY `ix_oauth_transactions_expiry` (`expires_at`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oauth_transactions`
--

LOCK TABLES `oauth_transactions` WRITE;
/*!40000 ALTER TABLE `oauth_transactions` DISABLE KEYS */;
INSERT INTO `oauth_transactions` VALUES (1,_binary 'i6¢Çûìmw/©ÇÄõK±u\nVùtp\'= âò\«\„',_binary '\ÔF[R\ƒ\˜d∏o\ˆj\…=1ÖfÇL\‹2\œX)&\ˆ≥e',_binary 'gAAAAABqtPZAPfAt2ndj5xzDfeDtDFFdJBE0rfsJd-d_olUNQtUSwtJ53qaxQjSQGB_AwlRC-sMPybLNTVWKPwwBgums6WlAPAcnTr06EfHNnIvYhR_dToDvoHY2dpWrLRJNlTXcp1YV',_binary '\◊H\Ît¨ß¯Ná+1\ÕD≠Ø\ﬁT∫L\Ù≤)≤5@/\Ÿû',_binary 'gAAAAABqtPZA45i2wbcTi1Ox2ZjkPHXmty9P46odsBjsNennKnLDOUmOSbnHrssETwUI52GCwyP1txvSc02ldtvBqIXeoJJc2t3ubCE4lSfwdhR-HNrYWkaLBH--e6MfJU4corOKf-Safz9Uj1PBU2dY_3-Ewg4KCRLJS26egsIdDMgUyYns2_Nfjf9wmwJmtiIps-RIhtku','2026-09-24 10:06:56.309934','2026-09-24 10:16:56.309934',NULL),(2,_binary '--0˛_ÖD^ ç\Û\Ë`^\Œ\ﬁ\Ï\ r\Ò\›\ÕËëÅ\·DW',_binary 'h\‹Nò˛ó=≤é \◊øVGMà\È\ÿ*dWu\"\€\0˝båãº',_binary 'gAAAAABqtPcQqf3QWHui3d2i1UlNnf7h-HETucsTxjsqSNUvQmDhUIcdkWtK9UobO0gURdYRO_mSJ4D-CI4F7hjAPiYFXz1QOCp0zse4IO64PEXRl-e0zbPvRavkbF4Rcz4u6JTDpa79',_binary '\‹\Êaí\„ü…ã16\ `\Í\Á2\Ë+»å>≠\“51\≈\Â\⁄e\'',_binary 'gAAAAABqtPcQW0y30Cst7IE39-eP_0ip2uLoIgMcQ3qPtvQxrkbfgBiQ6I1LO-FNlci6-sYR6nAXpLg82GLKg1mZ7SSrwTiZM6D5C5sZcj9Z_1A5tsm7zUxPqxhFlLXauXT7CbpJ84cx3Ob4g0YceLDYReau2yesua2siFoU0k22huEGBR9v_Melwf3xmPLSIe9uvT9gFWwz','2026-09-24 10:10:24.449037','2026-09-24 10:20:24.449037',NULL),(3,_binary 'Üy™˙ZÜ\ÏKº\Ò\…\‹&¸\ı9\ 4\ÚóL6N\Ã¡êp',_binary '\Û™%\‹\‰rΩ1H˙Jqµ¯=\"y-î\‰1¬Ä2∑ì(0ªΩ™',_binary 'gAAAAABqtPcUYpmtmUArcWTUN_cB9hXgAQmkJ3HoQ9boZ9tB7kYfuICspYbnv12qVh8kjNVrjRawtKVM4Y5DqvbwLraANA1MTJ1fyQSFVg0N3TApmamicUiyizEgqtVEEmhJTYxk15g4',_binary 'íì\Ôƒ§c\·6T\Ò/M\“G\Ì\Ô\Úu\„–á¿\«\Ìù\œ\Ú{',_binary 'gAAAAABqtPcUGGQfEHyKROz53NXsSDawih9_q2CJ0GjJRJ2DED5KT37a7SbwElj-osP2-d1HVEE2zK_uFqaipPHu2mB0_CjI3jjTj0EfaS8WJND-FLU03FUeNpOAQ-PhnGJcRTcaTmULfL8PNCRaPUC1Z6B0F0NL1mJLK-SP88uYycSCyni0sYEQnuWJpa0Egbp1EeXwGJZY','2026-09-24 10:10:28.509402','2026-09-24 10:20:28.509402',NULL),(4,_binary '<•O¢Ω¯^\ÿœ°è£¨@|\–\ÿ\ÊA_QF≤–Å\Ÿ\Ìô\Ú',_binary '%-\„7†\Ùà,*\Óú˛.ª\˜±“™4~*Öúæm.b',_binary 'gAAAAABqtPcU0mvyRWUXt3l6Sn-q4_O8CkD9bdjYHxk568qGgRMEZl5NTPlLgOCewS6e3LxQJXZK-5UfRNojUvji6WPUdk8XKGuN79lIr8n9JhkPSII6yiMPMvJ2O_MCEoT1gj168Fcn',_binary 'ñüxsSE;	\–ﬁô\Ô˝èjL\’\ÍEEcE\Ú\È\„ \›\Ì',_binary 'gAAAAABqtPcUvDRGXfzCIE-uz_GXiqoB0CyPiC7vF7IHGe5j2nnjHp1tWZK3eIjqM4PnApOq78O2UpORtEaMx7lXMTP_qVM5eNHfVwEEdE0J1lbuerp8kybkozZph4CSyYK2mVsHGJgEu94n9fGakluGMVFy-2ldRlRHhva-drk15MmnGKAxopi7ffPfFfEdpYNyBaf1R4Dn','2026-09-24 10:10:28.944935','2026-09-24 10:20:28.944935',NULL),(5,_binary '≠\Ë<¥±˛\“e\‚)g¯ñ\‘L_#’π\ \„ª\÷\0\À\ÍÉ',_binary 'ó Üvz\Î\n59DpS9óo¢}Åd\√ÆAãï≠˝oCe',_binary 'gAAAAABqtPcVbkksqc9QKmWWbpEePmr-XsihlCRBjQ9c0g6FsL0EpGeA7evnuRqefnFWXbpqjhzO831pLb6S2yJE9coAaS6xG9RLmVrCnTjdtHjuieISSIy8TXXcN_gPqbnkiJxgQOvz',_binary 'é\‡\–q\05fn2\Á\r\ƒ\Â	ó\È\÷a\»IdESKq@@\Èà£',_binary 'gAAAAABqtPcV_SufIrSK_CK2AkcojXJBM6d4zYFIBXv8vX9HCUuG9x35LD4JJpLdvEMmgzd0DpT8DijI4cYBEp53uTk3eJmuOApIt1FTQwYIN5XtdlDsHvKfUpmIDL4_aNoN33HTGWio9ezG5Ze1ryuZvYfl6Gq2C-_fzdl9JYxz4X9Cmwm8_18QU6yAGAPzAhxKpCjtRqjw','2026-09-24 10:10:29.137504','2026-09-24 10:20:29.137504',NULL),(6,_binary 'U”°\·\Ã,9W+ÇOD6É\ÿ-!y˙*B\ÏQ	ïÇ/B\ı',_binary 'o˚\r˚ßr\Ò\Îz:\ÛëÜ\÷yî¸o\0VP™	KµÀ™',_binary 'gAAAAABqtPcVn9W2uR9HiuEAp8_pnqY-JqhqfEDRb1wxLMcijGMsFOjkg89pBNZSSg8F8KHl5-Lv5HnRprMzgB0UzZ4GB0-WWD97rVUlHDdy2jKcnkceShxleh2mLmcLvqwDswT5Toto',_binary 'ÖÅ˙ZW\‹bU8ä\ˆB6\∆=k\ﬂb\ÛSÜ\·\‘z\Ù˚Ü\ÿ',_binary 'gAAAAABqtPcVQY87H4II6UW86LiTZX-dp89QNnw75HBgWMqbPXXq-2SEGq3edSgrcXUYbE1VxhtWEvmkICYbmrg7y0FrDnVNnBvGFmnHzDTNgN0PqOmfagzENuQ7SOs9Ju_7wmKmfpDJmTn1ymtbIEUmXklNjijI_yk1DXmicZGd8YVJEBZ1vJbQX-ssujN6A8xdojQFCuQB','2026-09-24 10:10:29.324100','2026-09-24 10:20:29.324100',NULL),(7,_binary 'V\«\Î4\∆l\€*\Õ\Ù\‹\◊ \ÂVT\ÊB\Òæ∑\ z`4¨\Ú',_binary 'Dl√ïµC\·\ﬂ/L\√\Î.µ¯v3´˛\ﬁ‹®<ΩÇö\√SY',_binary 'gAAAAABqtPcVXAaPv8wjFUNVYAH8wmB-smTHsZjLM-Ji5QVtWQng3w4jsnQkKw9-T4JV_xYRZATPJi4kJkmahGvgOCxftQoRLs486Rmv7PxK1L-BI9GsNDucrNAQ2zRhjZxd4l07JQHn',_binary 'µ®hPõ[ÅVaéN˝jaÑ¶A\Í\¬v8^í\"jï',_binary 'gAAAAABqtPcVnlKP9M3m2qWdQY5ZH6hk-vklfoIdwaSl277k1sh4McR3l7xD1lQjRnpnkzbzprcRTCV3l56Xr-3MchxxjHJBuXr_0GGp0cqD-fVlif0gIrgImsWElM4U-SkGdX2f9bV782XELagNY7MyAThS-wljdtrrXQtovb0L5-y97rZsNmw3CQbEDR_yV_dKF5ylzofY','2026-09-24 10:10:29.489728','2026-09-24 10:20:29.489728',NULL),(8,_binary '^\Ï•iH;N~\”ñHÇHq\·\Óx∑\Z≥Lt\·œÄ\„XZj',_binary 'W\Áu ´Ç\”\œKk\ÊrBeâ%\ı∫ô>n\ﬁºPSµ>u',_binary 'gAAAAABqtPfMO2V3Gf4TWCy_psnGhjSaQrqFROSkYfDg1BPdk7fgvdJhVa_lgzQ_H53gvqqblyRK2OIcQFvgup79tKZN3BdY_ltYdffn_yU-MrJMnPFBRYJk68XwUMzRH_mssbiWqWfC',_binary 'A{\‚\»B&\Ùvõ$\ﬁÀíh)v¯G¶uwR«∫\ mu',_binary 'gAAAAABqtPfMohGb2EkTbAM1VXQVcEjwQ_DKLz30KEiR1XRpU9x2ZbgQETkrbpsxUR1e_eSCQtlGecIf8e5xlZiDnZ8RPQoigASiH1jIrj6GkRrEJlVdj-p4aLDafCxIZ8gSeB4tG9RM6Nc8lClJAaDurktf8DMubfmMa1jdTZ5VjBAqjoqCEVHED1CP0qSEhjqaYmdhIeg1','2026-09-24 10:13:32.007245','2026-09-24 10:23:32.007245',NULL),(9,_binary '+Pw•O∑≈íïút{eæâÆ_£\ÊbJG9\rã\\∫R',_binary 'Ω\—\œ\‹5ñL£•Ç\Z¢íkj∑ó∏ò˙ã\ƒ(ˇ!\Ô8Ä\⁄h',_binary 'gAAAAABqtPfPI96HNTn4-Hq82a5wJTC_gRxd-ajDEKLE63Ngr-8hV0gsjLdrGBw3h4hAJ4IXEVknI2nJJkf_oHjvPAz1Uux-TDKFS2ClYQXSRKOr9mlYNz-WmmRmuNxy4V5J0-Gfez0e',_binary '\r\◊\ﬂ3ø\…\√xoÈ±Ål≠;9ö)Ω˛Å©\€\Î\Êy\Ó',_binary 'gAAAAABqtPfP6LduaCmP6ZWKSBcPQU130xdBGLC6SrHFZ90AkCsZEt-tEdEvxPROheC0C2WcdUWOz9haTSgoNJ4BZgnsaLs-e4wLIwHwiS1m7h4irOe0Vd7LY0NVIOhcYy9WDNG6lfisPvXBCgsMjVf0p8mHslsdsgaYpNR_CIjxbSjinkLGZCkRE3PHYcILVStzm5YWT9Qu','2026-09-24 10:13:35.880727','2026-09-24 10:23:35.880727',NULL),(10,_binary '\◊-\‰g\˜µô\"°ë0\„ªbN€≠WU\Ò\ÁU~˛E\r\ƒ.¥',_binary '_ª\0^¯+\Ôì2\‚CC^BC[	>\≈]¯£\¬<õ\ƒ\Ï5',_binary 'gAAAAABqtPfQTGMBl_G6FSMb3Wv49u8tqfm6HO826-6DzRGlqt5xjbwv9aOG3k-ePuMvkcz3M1ehElgLYnsdlgwX7d4sv1HLF_zH5mZnXD5atHwpglDqTQ8LbHEQDtn9-nUs4j-dRkLY',_binary '\€\ıl•\∆¯rëXEN\ÛñNù⁄∂Z©€ñ\ÏÅ\n\œNè´éÖK',_binary 'gAAAAABqtPfQFFb32sPAsu0MpZgWgGmQkFzV2LCJlWI6fMylj0VNKiOrzR1chQby-KlhkitPShaAurgSbN_1T-KdfbwzYtbC07ZdoOd13I736Aa1zSvGjLJFO15Czk0cDXyApMi68nyYzksOH1nqYSeILjnKLDscIMmGkHFNqrYqjF2S-hASz_dqpPOM1FLxetffyuJzdAqD','2026-09-24 10:13:36.319547','2026-09-24 10:23:36.319547',NULL),(11,_binary 'ì¨£^6\'6iV0ˇ\Á8\‘4™y~«ã\Ëcmë\\£`\ÿ}',_binary '\Úé\≈⁄≠∂-6ô\⁄*O6ä“ã\Ús1k\◊l{\’ﬁ§s?\Ó\◊aû',_binary 'gAAAAABqtPfQPL_iVkYkSz3S0IV2eQX-asr9kY9W7k7uEmroVZDJSUUF02EjI1v6Rr1rK-S5tboimB_6ycssdySvxn6uBnGlhsuBLjxxvty7zgfQ3XC7jLgaf4Yc6_4JvI9iOkRs04vB',_binary '¥J°§j#‹¨í>lÌùêT˙Çæfü\€}Í≤òπ+gG',_binary 'gAAAAABqtPfQw4WtTyXnACw1r3x9nct5nFmnev9jrWX_2M3XbUQOvF1Sm1cLywUKyZa9EtX-zUt1jqtufFxVcab8UgeGlw4XF21cainxvIat_BWJ-n3qnI3PXJmm34mhQuBUEin-PkugVu9AtlsYLtiM8DSW4qS4Iq-bee9itGn2hafdei_YjAeFnirLLOYhpcK-MKn3FxQE','2026-09-24 10:13:36.530234','2026-09-24 10:23:36.530234',NULL),(12,_binary 'Œ≥FqY§\ÀÅ\ˆøJìwJ93¶\Z∂U„≥¢‚Ü¶Y_s\’\ﬁ',_binary 'g%\‹Z,\ﬁ:∆•\Ò\"\ÌÅ;\ı™§åç∂:mt\‹+\Œ.',_binary 'gAAAAABqtPfQGc9WpjKXubYLArHH3VSqz0mo850A4fc6KGS9to45S1FQldXwg0WbP9YARUbPxLNv4NSBs00SCJrDi9SrpMWmfzbA-nj9uefv-yxLdwUpR1Rp5rzcqIFNKmQgpyEFiv6f',_binary 'O˝üa<™ç\«\À2\ÔüWëy#f.}/-¥/Hv\Û%B',_binary 'gAAAAABqtPfQ5hO1acd9Xdy99HadPQF9nQxMdi3q4s03fBhrx3rTF-43QbtC0uLiVqhLFZVvxkaNNXAx8pefuowy0bAnCM9BzKq1pmwPIRlJBvlnFQdk8secEoCfojHMQu4if9dDuZRM5eZDuYjZjnxXsLWOjjeJ_hudG5gPXl6ZYrZf4uy88o5ZY2x7EM3niicKNC3tIeA0','2026-09-24 10:13:36.712225','2026-09-24 10:23:36.712225',NULL),(13,_binary 'Q°ãì˛ºTwX\ÁôIÉû\Ê¡H\Ûæ\Ù\‡∆™LäºZ\·\˜\⁄',_binary '§˙\À	%/n\ÂU?m´Ü\Ì©ß+˚GÖYë¢JPæXy',_binary 'gAAAAABqtPfQeI4txVK3d0KdmMB4be1ZKgsjZtYVfh9FuZdgB1_IMcnp-KIE31VG0OmDmNbp6DJHdXA30RFeEtogaVP6M8c_soLE5Mk5zCTe1Np6yipc7SKKX89e7QYhaiXYhDwbZ_nY',_binary 'R<÷ÜDN@•ºü2Ñ_x\ˆ◊Åï9GoNK–πÀ¥nTú',_binary 'gAAAAABqtPfQju0Do3XA2W_oxS8F1hkrIojmTpJQnqKoGpR8g5_sFmE2VF6YF8SjOZCXwt-mnsVGTyCSQfwRO62sDHueUVQil-iQu0CoDu43Kc0SZhaQP9vp8XWO1zPwuUxrTd_YOc6stMenxdfyqfbhB-Xv-WRMz4JxBHfIG4N4vkbgSwiQNi1rT4psqU7I1rU5W-g12FAR','2026-09-24 10:13:36.907534','2026-09-24 10:23:36.907534',NULL),(14,_binary '•)/XPê\'3Å\ÚG7W^\«g!ík\›€í\ﬁ˚ßl|˛	',_binary '∏\Ò.\ÈÅ\Ó∏\Ã\ˆû¯îM\ËWé∑\Êu∫\ı%6∫TˇØ',_binary 'gAAAAABqtPy4rPx3WWkFDg1fuo2Z-Ob8HEqhThpQJhBKujckUD3Lk4TyXzU6dwURa-m0kf4kB78VyvYpZDy6p6d1EBpmZ2e8kxcl3IF19cbkqYkZ-cLiqwwKq1G6L4Jbrc6iW3e_MWoi',_binary '\˜Ø*\"A\…\‹	#∫#¥\ŒÜ\Ôf™∫æ\Ú÷ÑÒÑäöZm',_binary 'gAAAAABqtPy4FAulHg7JXgP7ecPzWxZWa1y2bQTS--rmepZQOM4tBGp97WcH4rJ1Cv3LXUEAQkzymJj8Cvz4EyThQgSzuVuXXyaca-nfTxrFVbCLVecepXNI5dbmqmNKI9aipuARrSQBgcKTqO-k2eH3eBcZEb6Gd8Gj_S2K7QAM_p5v2f3L_s18zMBIv6jM6ebvllxYCJUl','2026-09-24 10:34:32.169901','2026-09-24 10:44:32.169901',NULL),(15,_binary '∂\Z\ÿ\"!r\Óî\n&á-ifõ\Ùx¥7)7XX\ˆ\ÌÆ',_binary 'åOLy$ﬂä•xu<∏\ƒ)9û3zê\r<ülã¯\Í=B',_binary 'gAAAAABquLR5L8qFwui4MbtvmrTvz0icR36kf0BfiV0nlFRwrEAcfXiFcg0zBE4VipnAOJalatqKQTMzIWjvHDGz17rtNe1cxgzvAQ97tGVzh3r3P6jBTwoMDK5gbojxE8PN9xfQkr7e',_binary ')\ÿk\’«†Å@\÷.X≤éÑ)ã˛\‘\–)e~\ÍY˛Ts\À\Á≤',_binary 'gAAAAABquLR5XmxlMVyvVqKK8L5pHxFBgkludWVhcCvnCXzOPX3wPcxoXdzHtCm9QCor3J7xQSD2Fl8RFrs89L8mAUuz-0-iGwGJye8XUeYq6TB9W3eDt9lTD8tsWBgiKzXbn7rjZbbjud37Olrp9JxK1t_9E5XJQOKDp2ayYLCXjIBZn5TqDcy3OJ6AGB3zI5YjdlJF8-W4','2026-09-27 06:15:21.279108','2026-09-27 06:25:21.279108',NULL),(16,_binary '≤\Ô¸\¬JÙàíü}Pß\Íßt5ò¯D_÷∏¢sº≠¯\‹',_binary '¢Ø°\"\ËKΩØï˚\ıMbñº¸\Òè\ﬁ\›π\Ò¡n¯\0',_binary 'gAAAAABquLSMoZ4yvXzOHGq7g8JLCNQ9kA7KCzrm5JCYQMxLkdFDnAAxsfERSztoSBFJU9u3igAD2yfMnhFiKGE26psyqYKt4QuVIvBQvDQPu-F386S8AoYkpNJnn-je3nJmC0uXWhrM',_binary 'bå«âS\'6\Ì\Á+>de§PàC\€¨$y\€HR\Ú;\·ç',_binary 'gAAAAABquLSM9MaMqVtn6SR1S_PMa8QpMCAn-GGim7kL277sjT3lWnE3aEnQke3OCn4xMENHEnMJGg19Ysq5NGdJ3AwQKRF25HnsBNrTt5Hsv8z77EV9nIz3CP-hBPyRsW1zj9-yPr2cQ5bnFS-kFcg95MsfjAsaQ-ghBABB2KiWRWn4AlPZIFsTlAJfzWssTDB43nSD18Pd','2026-09-27 06:15:40.899988','2026-09-27 06:25:40.899988',NULL),(17,_binary 'b≥\«\˜ªä:˝zv\˜Ü\›NV≥\núK[±å˘©6',_binary '◊©îq5\Í¢3á8z¢\ÎÖ.^U&4\ÎBJû†“Ç˘	',_binary 'gAAAAABquLSQCvERaN4-JCMOYRkk3Xxe1WMPkEXhqU2lA-rjFzpCNZqmEFOjjztMi_xJR5roUCaBMhAiRKO7iakSrRcWd8bWTUrzTwS_yvxdH0WF-PIqb8zaMv-WiOpAa8VkMvpKHD6f',_binary '2zYb\\W6\‚#ù\Âû˝í_ìµHAN0ü¬•Ñ±',_binary 'gAAAAABquLSQg2vdanuv-T5kkYDg9doh4Lv_1ecUvpWxg7MhpVbm9ds2OXxegaWvsZxq6yIB9MwapE20Bi-lukG_-fG2nMBSAIvh-0VNmEm25ZEHrGnQ3CgLNeGzDux89TakmHtlBptpkWYmdJz5MVYtl_n6hp8I7aYf7gRIclXAYoKM6rz5iIcTzZEM9X8QpBlnWeS26BXl','2026-09-27 06:15:44.601637','2026-09-27 06:25:44.601637',NULL);
/*!40000 ALTER TABLE `oauth_transactions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `projects`
--

DROP TABLE IF EXISTS `projects`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `projects` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `public_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `name` varchar(128) NOT NULL,
  `description` varchar(512) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_projects_public_id` (`public_id`),
  CONSTRAINT `ck_projects_active` CHECK ((`is_active` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `projects`
--

LOCK TABLES `projects` WRITE;
/*!40000 ALTER TABLE `projects` DISABLE KEYS */;
/*!40000 ALTER TABLE `projects` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-27 22:54:12
