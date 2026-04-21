CREATE DATABASE IF NOT EXISTS `pulse_price_compare`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `pulse_price_compare`;

CREATE TABLE IF NOT EXISTS `searched_products` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `query_text` VARCHAR(255) NOT NULL,
  `normalized_query` VARCHAR(255) NOT NULL,
  `total_offers` INT NOT NULL DEFAULT 0,
  `platform_count` INT NOT NULL DEFAULT 0,
  `provider_count` INT NOT NULL DEFAULT 0,
  `live_provider_count` INT NOT NULL DEFAULT 0,
  `lowest_price` DECIMAL(12, 2) NULL,
  `highest_price` DECIMAL(12, 2) NULL,
  `average_price` DECIMAL(12, 2) NULL,
  `cheapest_title` VARCHAR(500) NULL,
  `cheapest_platform` VARCHAR(120) NULL,
  `cheapest_price` DECIMAL(12, 2) NULL,
  `used_demo_fallback` BOOLEAN NOT NULL DEFAULT FALSE,
  `result_payload` LONGTEXT NULL,
  `searched_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_searched_products_searched_at` (`searched_at`),
  INDEX `idx_searched_products_normalized_query` (`normalized_query`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
