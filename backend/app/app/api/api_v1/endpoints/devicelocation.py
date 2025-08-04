# backend/app/app/api/api_v1/endpoints/devicelocation.py
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime, timezone
from math import radians, cos, sin, sqrt, atan2
import logging

from app import crud, models
from app.api import deps
from .utils import ReportLogging

logger = logging.getLogger(__name__)

router = APIRouter()
router.route_class = ReportLogging

# ===== SHARED MODELS =====

class PointModel(BaseModel):
    latitude: float
    longitude: float

class CircleAreaModel(BaseModel):
    areaType: Literal["CIRCLE"] = "CIRCLE"
    center: PointModel
    radius: float

# ===== LOCATION RETRIEVAL MODELS =====

class RetrievalDeviceModel(BaseModel):
    networkAccessIdentifier: Optional[str] = Field(None, example="IMSI123456789012345")

class RetrievalLocationRequest(BaseModel):
    device: Optional[RetrievalDeviceModel] = None
    maxAge: Optional[int] = None
    maxSurface: Optional[int] = None

class RetrievalLocationResponse(BaseModel):
    lastLocationTime: str
    area: CircleAreaModel

# ===== LOCATION VERIFICATION MODELS =====

class LocationVerificationDeviceModel(BaseModel):
    networkAccessIdentifier: Optional[str] = Field(None, example="IMSI123456789012345")
    supi: Optional[str] = None

class LocationVerificationAreaModel(BaseModel):
    areaType: str = Field(..., example="CIRCLE")
    center: PointModel
    radius: float

class LocationVerificationRequest(BaseModel):
    device: LocationVerificationDeviceModel
    area: LocationVerificationAreaModel
    maxAge: Optional[int] = None

# ===== HELPER FUNCTIONS =====

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on earth (in meters)"""
    R = 6371000  # Earth's radius in meters
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2)**2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def get_ue_location(supi: str, db: Session):
    """Get UE location using NEF-Emulator CRUD functions (same as UE endpoint)"""
    try:
        # Use the same CRUD function as the UE endpoint
        ue = crud.ue.get_supi(db=db, supi=supi)
        if not ue:
            return None
            
        # For device location APIs, we'll be more permissive with access
        # since these are typically used by network operators
        return {
            "latitude": ue.latitude,
            "longitude": ue.longitude,
            "last_updated": ue.updated_at or datetime.now(timezone.utc)
        }
    except Exception as e:
        logger.error(f"Error getting UE location for {supi}: {e}")
        return None

# ===== LOCATION RETRIEVAL ENDPOINT =====

@router.post("/location-retrieval/v0.4/retrieve", response_model=RetrievalLocationResponse)
async def retrieve_location(
    body: RetrievalLocationRequest, 
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    """
    CAMARA Location Retrieval API - Get device location from NEF database
    """
    supi = body.device.networkAccessIdentifier if body.device else None
    if not supi:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "MISSING_IDENTIFIER",
                "message": "Only networkAccessIdentifier (IMSI/SUPI) is supported in this implementation."
            }
        )

    if body.maxAge == 0:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "LOCATION_RETRIEVAL.UNABLE_TO_FULFILL_MAX_AGE",
                "message": "Unable to provide expected freshness for location"
            }
        )
    
    if body.maxSurface is not None:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "LOCATION_RETRIEVAL.UNABLE_TO_FULFILL_MAX_SURFACE",
                "message": "Unable to provide accurate acceptable surface for location"
            }
        )

    # Get UE location from NEF database
    location_info = get_ue_location(supi, db)
    if not location_info or location_info["latitude"] is None or location_info["longitude"] is None:
        return JSONResponse(
            status_code=404,
            content={
                "status": 404,
                "code": "LOCATION_RETRIEVAL.DEVICE_NOT_FOUND",
                "message": "The location server is not able to locate the mobile"
            }
        )

    last_location_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    area = CircleAreaModel(
        areaType="CIRCLE",
        center=PointModel(
            latitude=location_info["latitude"], 
            longitude=location_info["longitude"]
        ),
        radius=100  # Fixed accuracy radius as NEF Emulator doesn't provide accuracy
    )

    return RetrievalLocationResponse(
        lastLocationTime=last_location_time,
        area=area
    )

# ===== LOCATION VERIFICATION ENDPOINT =====

@router.post("/location-verification/v1/location/verify")
async def location_verification(
    body: LocationVerificationRequest, 
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    """
    CAMARA Location Verification API - Verify if device is in specified area
    """
    device = body.device
    area = body.area
    max_age = body.maxAge

    supi = device.networkAccessIdentifier or device.supi
    if not supi:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "MISSING_IDENTIFIER",
                "message": "Only networkAccessIdentifier (IMSI/SUPI) is supported in this implementation."
            }
        )

    if area.areaType != "CIRCLE":
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "LOCATION_VERIFICATION.AREA_NOT_COVERED",
                "message": "Only areaType=CIRCLE is supported."
            }
        )

    ref_lat = area.center.latitude
    ref_lon = area.center.longitude
    radius = area.radius or 100

    if ref_lat is None or ref_lon is None:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "LOCATION_VERIFICATION.INVALID_AREA",
                "message": "Center latitude and longitude are required."
            }
        )

    # Get UE location from NEF database
    location_info = get_ue_location(supi, db)
    if not location_info or location_info["latitude"] is None or location_info["longitude"] is None:
        return {
            "verificationResult": "UNKNOWN"
        }

    ue_lat = location_info["latitude"]
    ue_lon = location_info["longitude"]
    last_location_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Calculate distance between UE and reference point
    distance = haversine(ue_lat, ue_lon, ref_lat, ref_lon)

    verification_result = "TRUE" if distance <= radius else "FALSE"

    return {
        "verificationResult": verification_result,
        "lastLocationTime": last_location_time,
        "distance": round(distance, 2)
    }

# ===== UTILITY ENDPOINTS =====

@router.get("/health")
async def health_check():
    """Health check endpoint for CAMARA Device Location APIs"""
    return {
        "status": "healthy",
        "apis": [
            "Location Retrieval v0.4",
            "Location Verification v1"
        ],
        "integration": "NEF-Emulator",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
