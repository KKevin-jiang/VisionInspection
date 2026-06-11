from __future__ import annotations

from typing import Any

from vision_inspection.utils.logger import get_logger

logger = get_logger(__name__)


class SqlServerClientError(RuntimeError):
    pass


class SqlServerClient:
    """SQL Server 数据库客户端 — 查询机型 + 写检测结果。"""

    def __init__(
        self,
        server: str,
        database: str,
        username: str,
        password: str,
        serial_table: str = "T_SerialNo",
        serial_field: str = "ActSerialNo",
        model_field: str = "MachineType",
        result_table: str = "T_VisionResult",
        station_id: str = "ST001",
    ) -> None:
        self._server = server
        self._database = database
        self._username = username
        self._password = password
        self._serial_table = serial_table
        self._serial_field = serial_field
        self._model_field = model_field
        self._result_table = result_table
        self._station_id = station_id
        self._connection = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        if self._connection is None:
            return False
        try:
            import pyodbc
            cursor = self._connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:
            self._connected = False
            return False

    def connect(self) -> None:
        if self._connected and self.is_connected:
            return
        try:
            import pyodbc
        except ImportError:
            raise SqlServerClientError("pyodbc 未安装，无法连接 SQL Server")
        try:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self._server};"
                f"DATABASE={self._database};"
                f"UID={self._username};"
                f"PWD={self._password}"
            )
            self._connection = pyodbc.connect(conn_str, timeout=5)
            self._connected = True
            logger.info("SQL Server 连接成功: %s/%s", self._server, self._database)
        except Exception as exc:
            self._connected = False
            raise SqlServerClientError(f"SQL Server 连接失败: {exc}") from exc

    def disconnect(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
        self._connected = False

    def query_machine_type(self, serial_no: str) -> str | None:
        self.connect()
        try:
            sql = (
                f"SELECT TOP 1 {self._model_field} "
                f"FROM [{self._database}].[dbo].[{self._serial_table}] "
                f"WHERE {self._serial_field} = ?"
            )
            cursor = self._connection.cursor()
            cursor.execute(sql, (serial_no,))
            row = cursor.fetchone()
            cursor.close()
            if row is None:
                logger.info("未查询到流水号 %s 的机型信息", serial_no)
                return None
            machine_type = str(row[0]).strip()
            logger.info("查询机型成功: serialNo=%s machineType=%s", serial_no, machine_type)
            return machine_type
        except Exception as exc:
            self._connected = False
            raise SqlServerClientError(f"查询机型失败: {exc}") from exc

    def write_result(self, record: dict[str, Any]) -> None:
        self.connect()
        try:
            sql = (
                f"INSERT INTO [{self._database}].[dbo].[{self._result_table}] "
                f"(StationId, SerialNo, MachineType, Result, Score, Algorithm, ImagePath, CreateTime) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())"
            )
            cursor = self._connection.cursor()
            cursor.execute(
                sql,
                (
                    self._station_id,
                    record.get("serial_no", ""),
                    record.get("machine_type", ""),
                    record.get("result", ""),
                    record.get("score", 0),
                    record.get("algorithm", ""),
                    record.get("image_path", ""),
                ),
            )
            self._connection.commit()
            cursor.close()
            logger.info(
                "检测结果写入成功: station=%s serialNo=%s result=%s",
                self._station_id,
                record.get("serial_no"),
                record.get("result"),
            )
        except Exception as exc:
            self._connected = False
            raise SqlServerClientError(f"写检测结果失败: {exc}") from exc
