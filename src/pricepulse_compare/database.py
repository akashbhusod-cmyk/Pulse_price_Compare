from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pricepulse_compare.settings import AppSettings, DATA_DIR


@dataclass(slots=True)
class DatabaseStatus:
    enabled: bool
    available: bool
    message: str


class SearchHistoryRepository:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._last_connect_attempt = 0.0
        self.status = DatabaseStatus(
            enabled=settings.mysql_enabled,
            available=False,
            message="MySQL history logging is disabled.",
        )
        self.backup_path = DATA_DIR / "search_history_backup.json"
        self.pending_path = DATA_DIR / "search_history_pending.json"

    def init_schema(self) -> None:
        if not self.settings.mysql_enabled:
            return

        self._last_connect_attempt = time.monotonic()
        try:
            connector = self._connector()
            database_name = self._database_name()
            server_connection = connector.connect(**self._server_config())
            server_cursor = server_connection.cursor()
            server_cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            server_cursor.close()
            server_connection.close()

            db_connection = connector.connect(**self._database_config())
            db_cursor = db_connection.cursor()
            db_cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS searched_products (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    query_text VARCHAR(255) NOT NULL,
                    normalized_query VARCHAR(255) NOT NULL,
                    total_offers INT NOT NULL DEFAULT 0,
                    platform_count INT NOT NULL DEFAULT 0,
                    provider_count INT NOT NULL DEFAULT 0,
                    live_provider_count INT NOT NULL DEFAULT 0,
                    lowest_price DECIMAL(12, 2) NULL,
                    highest_price DECIMAL(12, 2) NULL,
                    average_price DECIMAL(12, 2) NULL,
                    cheapest_title VARCHAR(500) NULL,
                    cheapest_platform VARCHAR(120) NULL,
                    cheapest_price DECIMAL(12, 2) NULL,
                    used_demo_fallback BOOLEAN NOT NULL DEFAULT FALSE,
                    result_payload LONGTEXT NULL,
                    searched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_searched_products_searched_at (searched_at),
                    INDEX idx_searched_products_normalized_query (normalized_query)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            db_connection.commit()
            db_cursor.close()
            db_connection.close()

            self.status = DatabaseStatus(
                enabled=True,
                available=True,
                message=f"Connected to MySQL database `{database_name}`.",
            )
        except Exception as exc:
            self.status = DatabaseStatus(
                enabled=True,
                available=False,
                message=f"MySQL history logging is unavailable: {exc}",
            )

    def record_search(self, result: dict[str, Any]) -> None:
        record = self._record_from_result(result)
        if not record:
            return

        self._append_local_record(self.backup_path, record)
        self._ensure_available()
        if not self.status.enabled or not self.status.available:
            self._append_local_record(self.pending_path, record)
            return

        try:
            self._insert_record(record)
        except Exception as exc:
            self.status = DatabaseStatus(
                enabled=True,
                available=False,
                message=f"MySQL history logging failed: {exc}",
            )
            self._append_local_record(self.pending_path, record)
            return

        try:
            self._sync_pending_records()
        except Exception as exc:
            self.status = DatabaseStatus(
                enabled=True,
                available=False,
                message=f"MySQL pending history sync failed: {exc}",
            )

    def recent_searches(self, limit: int = 8) -> list[dict[str, Any]]:
        self._ensure_available()
        if not self.status.enabled or not self.status.available:
            return self._local_records(self.backup_path, limit=limit)

        try:
            self._sync_pending_records()
            connector = self._connector()
            connection = connector.connect(**self._database_config())
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    id,
                    query_text,
                    total_offers,
                    platform_count,
                    lowest_price,
                    cheapest_title,
                    cheapest_platform,
                    cheapest_price,
                    searched_at
                FROM searched_products
                ORDER BY searched_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            cursor.close()
            connection.close()
            return rows
        except Exception as exc:
            self.status = DatabaseStatus(
                enabled=True,
                available=False,
                message=f"MySQL history lookup failed: {exc}",
            )
            return self._local_records(self.backup_path, limit=limit)

    def _record_from_result(self, result: dict[str, Any]) -> dict[str, Any] | None:
        summary = result.get("summary", {})
        highlights = result.get("highlights", {})
        cheapest = highlights.get("cheapest") if isinstance(highlights, dict) else None
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(cheapest, dict):
            cheapest = {}

        query = str(result.get("query", "")).strip()
        if not query:
            return None

        return {
            "query_text": query,
            "normalized_query": " ".join(query.lower().split()),
            "total_offers": summary.get("total_offers", 0),
            "platform_count": summary.get("platform_count", 0),
            "provider_count": summary.get("provider_count", 0),
            "live_provider_count": summary.get("live_provider_count", 0),
            "lowest_price": summary.get("lowest_price"),
            "highest_price": summary.get("highest_price"),
            "average_price": summary.get("average_price"),
            "cheapest_title": cheapest.get("title"),
            "cheapest_platform": cheapest.get("platform"),
            "cheapest_price": cheapest.get("price"),
            "used_demo_fallback": bool(result.get("used_demo_fallback")),
            "result_payload": json.dumps(result, ensure_ascii=True),
            "searched_at": datetime.now(),
        }

    def _insert_record(self, record: dict[str, Any]) -> None:
        connector = self._connector()
        connection = connector.connect(**self._database_config())
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO searched_products (
                query_text,
                normalized_query,
                total_offers,
                platform_count,
                provider_count,
                live_provider_count,
                lowest_price,
                highest_price,
                average_price,
                cheapest_title,
                cheapest_platform,
                cheapest_price,
                used_demo_fallback,
                result_payload,
                searched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record["query_text"],
                record["normalized_query"],
                record["total_offers"],
                record["platform_count"],
                record["provider_count"],
                record["live_provider_count"],
                record["lowest_price"],
                record["highest_price"],
                record["average_price"],
                record["cheapest_title"],
                record["cheapest_platform"],
                record["cheapest_price"],
                record["used_demo_fallback"],
                record["result_payload"],
                record["searched_at"],
            ),
        )
        connection.commit()
        cursor.close()
        connection.close()

    def _sync_pending_records(self) -> None:
        pending_records = self._read_local_records(self.pending_path)
        if not pending_records:
            return

        synced_count = 0
        for record in pending_records:
            self._insert_record(record)
            synced_count += 1

        remaining_records = pending_records[synced_count:]
        self._write_local_records(self.pending_path, remaining_records)

    def _append_local_record(self, path, record: dict[str, Any]) -> None:
        records = self._read_local_records(path)
        records.append(record)
        self._write_local_records(path, records[-500:])

    def _local_records(self, path, limit: int) -> list[dict[str, Any]]:
        records = self._read_local_records(path)
        records.sort(key=lambda row: row["searched_at"], reverse=True)
        rows = records[:limit]
        for index, row in enumerate(rows, start=1):
            row.setdefault("id", f"local-{index}")
        return rows

    def _read_local_records(self, path) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        try:
            raw_records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        records = []
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                continue
            searched_at = raw_record.get("searched_at")
            if isinstance(searched_at, str):
                try:
                    raw_record["searched_at"] = datetime.fromisoformat(searched_at)
                except ValueError:
                    raw_record["searched_at"] = datetime.now()
            elif not isinstance(searched_at, datetime):
                raw_record["searched_at"] = datetime.now()
            records.append(raw_record)
        return records

    def _write_local_records(self, path, records: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for record in records:
            serialized = dict(record)
            searched_at = serialized.get("searched_at")
            if isinstance(searched_at, datetime):
                serialized["searched_at"] = searched_at.isoformat(timespec="seconds")
            payload.append(serialized)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    @staticmethod
    def _connector():
        import mysql.connector

        return mysql.connector

    def _server_config(self) -> dict[str, Any]:
        return {
            "host": self.settings.mysql_host,
            "port": self.settings.mysql_port,
            "user": self.settings.mysql_user,
            "password": self.settings.mysql_password,
            "connection_timeout": self.settings.mysql_connection_timeout,
        }

    def _database_config(self) -> dict[str, Any]:
        return {
            **self._server_config(),
            "database": self._database_name(),
        }

    def _database_name(self) -> str:
        database_name = self.settings.mysql_database.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
            raise ValueError("MYSQL_DATABASE can only contain letters, numbers, and underscores.")
        return database_name

    def _ensure_available(self) -> None:
        if not self.settings.mysql_enabled or self.status.available:
            return

        if time.monotonic() - self._last_connect_attempt < 10:
            return

        self.init_schema()
