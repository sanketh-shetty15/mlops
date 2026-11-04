"""
api/schemas.py
---------------
Pydantic request and response models for the FastAPI endpoints.

Pydantic validates every incoming request field automatically —
wrong types or missing required fields return a clear 422 error
before the model even sees the data.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict


class AccidentFeatures(BaseModel):
    """
    Input features for a single accident severity prediction.
    All fields match ML_FEATURE_COLUMNS in config.py.
    Missing optional fields default to None (imputed by preprocessor).
    """
    accident_hour:           int   = Field(..., ge=0, le=23,
                                           description="Hour of day 0-23")
    weekday_num:             int   = Field(..., ge=0, le=6,
                                           description="0=Monday … 6=Sunday")
    accident_month:          int   = Field(..., ge=1, le=12,
                                           description="Month 1-12")
    road_type:               int   = Field(...,
                                           description="STATS19 road type code")
    speed_limit:             int   = Field(..., ge=0,
                                           description="Speed limit in mph")
    junction_detail:         Optional[int]   = Field(None)
    light_conditions:        Optional[int]   = Field(None)
    road_surface_conditions: Optional[int]   = Field(None)
    urban_or_rural_area:     Optional[int]   = Field(None,
                                                      description="1=Urban 2=Rural")
    number_of_vehicles:      Optional[int]   = Field(None, ge=0)
    number_of_casualties:    Optional[int]   = Field(None, ge=0)
    temperature_2m:          Optional[float] = Field(None,
                                                      description="°C from Open-Meteo")
    precipitation:           Optional[float] = Field(None, ge=0,
                                                      description="mm")
    wind_speed_10m:          Optional[float] = Field(None, ge=0,
                                                      description="mph")
    weather_code:            Optional[int]   = Field(None,
                                                      description="WMO weather code")

    model_config = {
        "json_schema_extra": {
            "example": {
                "accident_hour":           8,
                "weekday_num":             0,
                "accident_month":          1,
                "road_type":               6,
                "speed_limit":             30,
                "junction_detail":         13,
                "light_conditions":        1,
                "road_surface_conditions": 1,
                "urban_or_rural_area":     1,
                "number_of_vehicles":      2,
                "number_of_casualties":    1,
                "temperature_2m":         -0.7,
                "precipitation":           0.0,
                "wind_speed_10m":          14.5,
                "weather_code":            2
            }
        }
    }


class PredictionResponse(BaseModel):
    """Response from POST /predict/severity"""
    severity_code:  int            = Field(..., description="1=Fatal 2=Serious 3=Slight")
    severity_label: str            = Field(..., description="Fatal | Serious | Slight")
    confidence:     float          = Field(..., description="Probability of predicted class")
    probabilities:  Dict[str, float] = Field(...,
                                              description="P(Fatal), P(Serious), P(Slight)")
    model_type:     str
    champion_model: str
    latency_ms:     Optional[float] = None


class BatchRequest(BaseModel):
    """Request body for POST /predict/batch"""
    records: list[AccidentFeatures]


class BatchResponse(BaseModel):
    """Response from POST /predict/batch"""
    predictions:  list[PredictionResponse]
    total:        int
    latency_ms:   float


class HealthResponse(BaseModel):
    status:       str
    model_loaded: bool
    model_type:   str
    version:      str


class ModelInfoResponse(BaseModel):
    model_path:    str
    model_type:    str
    champion_model:str
    metrics:       dict
    feature_count: int
    features:      list[str]
