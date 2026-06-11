"""
上位机 HTTP API 服务 — 部署在 192.168.0.101 上

提供两个接口：
  GET  /api/v1/health                   → 健康检查
  POST /api/v1/crankshaft/model-by-serial → 根据流水号查询机型号

部署步骤（在上位机 192.168.0.101 上执行）：
  1. 安装依赖：pip install flask pyodbc
  2. 修改下方 DATABASE_CONFIG 中的数据库连接参数
  3. 启动：python host_api_server.py
  4. 验证：浏览器打开 http://192.168.0.101:8080/api/v1/health
"""

from __future__ import annotations

import json
import logging
import socket
import sys
from datetime import datetime

from flask import Flask, jsonify, request

# ── 数据库配置（按实际环境修改）─────────────────────────────
DATABASE_CONFIG = {
    "server": r"192.168.0.101\SQL201",
    "database": "BLT",
    "username": "sa",
    "password": "123456",
    "driver": "ODBC Driver 17 for SQL Server",
}

# ── 服务配置 ─────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8080

# ── 日志（输出到文件，pythonw.exe 无控制台也能正常写）─────
import os as _os

_LOG_DIR = _os.path.dirname(_os.path.abspath(__file__))
_LOG_FILE = _os.path.join(_LOG_DIR, "host_api.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout) if sys.stdout else logging.NullHandler(),
    ],
)
logger = logging.getLogger("host_api")

app = Flask(__name__)


def get_db_connection():
    import pyodbc

    conn_str = (
        f"DRIVER={{{DATABASE_CONFIG['driver']}}};"
        f"SERVER={DATABASE_CONFIG['server']};"
        f"DATABASE={DATABASE_CONFIG['database']};"
        f"UID={DATABASE_CONFIG['username']};"
        f"PWD={DATABASE_CONFIG['password']}"
    )
    return pyodbc.connect(conn_str, timeout=5)


# ──────────────────────────────────────────────────────────
#  GET /api/v1/health
# ──────────────────────────────────────────────────────────
@app.route("/api/v1/health", methods=["GET"])
def health():
    """健康检查 — 同时验证数据库连接。"""
    db_ok = False
    db_error = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_ok = True
    except Exception as exc:
        db_error = str(exc)

    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else f"error: {db_error}",
        "timestamp": datetime.now().isoformat(),
        "server": socket.gethostname(),
    })


# ──────────────────────────────────────────────────────────
#  POST /api/v1/crankshaft/model-by-serial
# ──────────────────────────────────────────────────────────
@app.route("/api/v1/crankshaft/model-by-serial", methods=["POST"])
def model_by_serial():
    """
    根据流水号查询机型号。

    请求体 JSON:
      { "serialNo": "SN20260608001", "source": "vision-inspection", "requestId": "uuid" }

    响应 JSON:
      成功: { "code": 0, "message": "ok", "machineType": "10V3AABB1234" }
      流水号不存在: { "code": 1003, "message": "serial not found", "machineType": "" }
      参数错误: { "code": 400, "message": "missing serialNo" }
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"code": 400, "message": "invalid JSON body"}), 400

    serial_no = (data.get("serialNo") or "").strip()
    source = data.get("source", "unknown")
    request_id = data.get("requestId", "")

    if not serial_no:
        return jsonify({"code": 400, "message": "missing serialNo", "machineType": ""}), 400

    # 流水号校验：非"0"、长度 10
    if serial_no == "0" or len(serial_no) != 10:
        logger.warning(
            "无效流水号: serialNo=%s source=%s requestId=%s", serial_no, source, request_id
        )
        return jsonify({"code": 1003, "message": "invalid serialNo", "machineType": ""})

    logger.info("查询机型: serialNo=%s source=%s requestId=%s", serial_no, source, request_id)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = (
            "SELECT TOP 1 MachineType "
            "FROM [BLT].[dbo].[T_SerialNo] "
            "WHERE ActSerialNo = ?"
        )
        cursor.execute(sql, (serial_no,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row is None:
            logger.info("未找到流水号: serialNo=%s", serial_no)
            return jsonify({"code": 1003, "message": "serial not found", "machineType": ""})

        machine_type = str(row[0]).strip()
        logger.info(
            "查询成功: serialNo=%s → machineType=%s requestId=%s",
            serial_no, machine_type, request_id,
        )
        return jsonify({
            "code": 0,
            "message": "ok",
            "machineType": machine_type,
        })

    except Exception as exc:
        logger.error("数据库查询失败: serialNo=%s error=%s", serial_no, exc)
        return jsonify({"code": 500, "message": f"database error: {exc}", "machineType": ""}), 500


# ──────────────────────────────────────────────────────────
#  启动入口
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("========================================")
    logger.info("上位机 HTTP API 服务 v1.0 启动")
    logger.info("监听: http://%s:%s", HOST, PORT)
    logger.info("========================================")
    app.run(host=HOST, port=PORT, debug=False)
