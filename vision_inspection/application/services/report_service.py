from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from vision_inspection.utils.logger import get_logger

logger = get_logger(__name__)


class ReportService:
    """Excel 报表导出服务 — 按日期范围汇总检测记录，生成含图表的 .xlsx 文件。"""

    def __init__(self, records_root: str | Path) -> None:
        self._records_root = Path(records_root)

    def export_excel(
        self,
        output_path: str | Path,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Path:
        output_path = Path(output_path)
        records = self._collect_records(start_date, end_date)
        if not records:
            logger.warning("导出报表: 日期范围内无记录")
            records = []

        df = pd.DataFrame(records)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
            if not df.empty:
                df.to_excel(writer, sheet_name="检测记录", index=False)
            summary_df = self._build_summary(df)
            summary_df.to_excel(writer, sheet_name="每日汇总", index=False)
            self._add_yield_chart(writer, summary_df)

        logger.info("报表已导出: %s (%d 条记录)", output_path, len(records))
        return output_path

    def _collect_records(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> list[dict]:
        records: list[dict] = []
        if not self._records_root.exists():
            return records

        for summary_csv in self._records_root.rglob("summary.csv"):
            try:
                df = pd.read_csv(summary_csv, encoding="utf-8-sig")
                for _, row in df.iterrows():
                    ts_str = str(row.get("timestamp", ""))
                    try:
                        ts = pd.to_datetime(ts_str)
                    except Exception:
                        continue
                    if start_date and ts < start_date:
                        continue
                    if end_date and ts > end_date:
                        continue
                    records.append(row.to_dict())
            except Exception as exc:
                logger.warning("跳过无法读取的 CSV: %s (%s)", summary_csv, exc)
                continue
        records.sort(key=lambda r: str(r.get("timestamp", "")))
        return records

    def _build_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["date", "total", "ok", "ng", "yield_rate"])
        df_copy = df.copy()
        df_copy["date"] = pd.to_datetime(df_copy["timestamp"]).dt.strftime("%Y-%m-%d")
        summary = df_copy.groupby("date").agg(
            total=("overall_result", "count"),
            ok=("overall_result", lambda x: (x == "OK").sum()),
            ng=("overall_result", lambda x: (x == "NG").sum()),
        ).reset_index()
        summary["yield_rate"] = (summary["ok"] / summary["total"] * 100).round(1)
        return summary

    def _add_yield_chart(self, writer, summary_df: pd.DataFrame) -> None:
        if summary_df.empty or len(summary_df) < 2:
            return
        try:
            from openpyxl.chart import LineChart, Reference
            from openpyxl.utils import get_column_letter
        except ImportError:
            return

        ws = writer.sheets["每日汇总"]
        chart = LineChart()
        chart.title = "合格率趋势"
        chart.y_axis.title = "合格率 (%)"
        chart.x_axis.title = "日期"
        chart.style = 10
        chart.height = 15
        chart.width = 25

        data_col = summary_df.columns.get_loc("yield_rate") + 1
        cat_col = summary_df.columns.get_loc("date") + 1
        data_ref = Reference(ws, min_col=data_col, min_row=1, max_row=len(summary_df) + 1)
        cat_ref = Reference(ws, min_col=cat_col, min_row=2, max_row=len(summary_df) + 1)
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cat_ref)
        chart.series[0].graphicalProperties.line.width = 25000

        ws.add_chart(chart, f"E2")
