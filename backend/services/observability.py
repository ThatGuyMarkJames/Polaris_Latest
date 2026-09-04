"""
POLARIS Observability & Audit Trail Service
Records every prediction, uncertainty interval, optimizer solve, and safety decision into persistent storage.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.database.db import get_db_connection


def log_forecast_and_decision(
    station_id: str,
    model_version: str,
    horizon_hours: int,
    prediction_type: str,
    predictions: Dict[str, Any],
    uncertainty: Optional[Dict[str, Any]] = None,
    optimizer_status: Optional[str] = None,
    actions_taken: Optional[List[str]] = None,
    safety_decision: Optional[str] = None,
    input_data_version: Optional[str] = "v2.0-openmeteo"
):
    """
    Logs an immutable record of forecasting and automated dispatch decisions for observability.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            INSERT INTO forecast_log (
                timestamp, station_id, model_version, input_data_version,
                horizon_hours, prediction_type, predictions_json, uncertainty_json,
                optimizer_status, actions_json, safety_decision, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_iso,
            station_id,
            model_version,
            input_data_version,
            horizon_hours,
            prediction_type,
            json.dumps(predictions),
            json.dumps(uncertainty or {}),
            optimizer_status,
            json.dumps(actions_taken or []),
            safety_decision,
            now_iso
        ))
        conn.commit()
    except Exception as e:
        print(f"Failed to write forecast audit log: {e}")
