from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Literal, List, Dict
import requests
import uvicorn
from datetime import datetime, timezone
from uuid import uuid4
import threading
import time

app = FastAPI()

NEF_URL = "http://localhost:8888"  # or "http://host.docker.internal:8888" if using Docker
USERNAME = "admin@my-email.com"
PASSWORD = "pass"

access_token = None

@app.on_event("startup")
def login_to_nef():
    global access_token
    print("🔐 Requesting token from NEF...")
    try:
        res = requests.post(
            f"{NEF_URL}/api/v1/login/access-token",
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "",
                "username": USERNAME,
                "password": PASSWORD,
                "scope": "",
                "client_id": "",
                "client_secret": ""
            }
        )
        res.raise_for_status()
        access_token = res.json()["access_token"]
        print("✅ Got access token:", access_token)
    except Exception as e:
        print("❌ Failed to get access token:", e)

@app.get("/test-token")
def test_token():
    if not access_token:
        return {"error": "Token not found"}

    res = requests.post(
        f"{NEF_URL}/api/v1/login/test-token",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {access_token}"
        }
    )
    return res.json()

@app.get("/ue/{supi}")
def get_ue_info(supi: str):
    if not access_token:
        return {"error": "No access token"}

    res = requests.get(
        f"{NEF_URL}/api/v1/UEs/{supi}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    return res.json()

# Shared models
class PointModel(BaseModel):
    latitude: float
    longitude: float

class CircleAreaModel(BaseModel):
    areaType: Literal["CIRCLE"] = "CIRCLE"
    center: PointModel
    radius: float

# --------- Location Retrieval Endpoint ---------
class RetrievalDeviceModel(BaseModel):
    networkAccessIdentifier: Optional[str] = Field(None, example="IMSI123456789012345")

class RetrievalLocationRequest(BaseModel):
    device: Optional[RetrievalDeviceModel] = None
    maxAge: Optional[int] = None
    maxSurface: Optional[int] = None

class RetrievalLocationResponse(BaseModel):
    lastLocationTime: str
    area: CircleAreaModel

@app.post("/location-retrieval/v0.4/retrieve", response_model=RetrievalLocationResponse)
async def retrieve_location(body: RetrievalLocationRequest):
    supi = body.device.networkAccessIdentifier if body.device else None
    if not supi:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "MISSING_IDENTIFIER",
                "message": "Só é suportado networkAccessIdentifier (IMSI/SUPI) nesta implementação."
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

    if not access_token:
        return JSONResponse(
            status_code=401,
            content={
                "status": 401,
                "code": "UNAUTHENTICATED",
                "message": "Token de acesso não disponível."
            }
        )

    res = requests.get(
        f"{NEF_URL}/api/v1/UEs/{supi}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if res.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "status": 404,
                "code": "LOCATION_RETRIEVAL.DEVICE_NOT_FOUND",
                "message": "The location server is not able to locate the mobile"
            }
        )
    ue = res.json()
    ue_lat = ue.get("latitude")
    ue_lon = ue.get("longitude")
    last_location_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if ue_lat is None or ue_lon is None:
        return JSONResponse(
            status_code=404,
            content={
                "status": 404,
                "code": "LOCATION_RETRIEVAL.DEVICE_NOT_FOUND",
                "message": "The location server is not able to locate the mobile"
            }
        )

    area = CircleAreaModel(
        areaType="CIRCLE",
        center=PointModel(latitude=ue_lat, longitude=ue_lon),
        radius=100  # Fixed value, as NEF Emulator does not provide accuracy
    )

    return RetrievalLocationResponse(
        lastLocationTime=last_location_time,
        area=area
    )

# --------- Location Verification Endpoint ---------
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

@app.post("/location-verification/v1/location/verify")
async def location_verification(body: LocationVerificationRequest):
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
                "message": "Só é suportado networkAccessIdentifier (IMSI/SUPI) nesta implementação."
            }
        )

    if area.areaType != "CIRCLE":
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "LOCATION_VERIFICATION.AREA_NOT_COVERED",
                "message": "Só é suportado areaType=CIRCLE."
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
                "message": "Latitude e longitude do centro são obrigatórios."
            }
        )

    if not access_token:
        return JSONResponse(
            status_code=401,
            content={
                "status": 401,
                "code": "UNAUTHENTICATED",
                "message": "Token de acesso não disponível."
            }
        )

    res = requests.get(
        f"{NEF_URL}/api/v1/UEs/{supi}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if res.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "status": 404,
                "code": "IDENTIFIER_NOT_FOUND",
                "message": "Identificador do dispositivo não encontrado."
            }
        )
    ue = res.json()
    ue_lat = ue.get("latitude")
    ue_lon = ue.get("longitude")
    last_location_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if ue_lat is None or ue_lon is None:
        return JSONResponse(
            status_code=200,
            content={
                "verificationResult": "UNKNOWN"
            }
        )

    from math import radians, cos, sin, sqrt, atan2
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = radians(lat1), radians(lat2)
        d_phi = radians(lat2 - lat1)
        d_lambda = radians(lon2 - lon1)
        a = sin(d_phi / 2)**2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    distance = haversine(ue_lat, ue_lon, ref_lat, ref_lon)

    if distance <= radius:
        verification_result = "TRUE"
    else:
        verification_result = "FALSE"

    return {
        "verificationResult": verification_result,
        "lastLocationTime": last_location_time,
        "distance": round(distance, 2)
    }

from fastapi import BackgroundTasks
from pydantic import HttpUrl
from typing import List, Dict
from uuid import uuid4
import threading
import time

# In-memory storage for geofencing subscriptions and state
geofencing_subscriptions: Dict[str, dict] = {}
geofencing_states: Dict[str, str] = {}  # (subscription_id) -> "inside"|"outside"
geofencing_events_count: Dict[str, int] = {}  # (subscription_id) -> int

# --- Geofencing Models ---

class GeofencingDeviceModel(BaseModel):
    networkAccessIdentifier: Optional[str] = Field(None, example="IMSI123456789012345")
    phoneNumber: Optional[str] = None
    ipv4Address: Optional[str] = None
    ipv6Address: Optional[str] = None

class GeofencingPointModel(BaseModel):
    latitude: float
    longitude: float

class GeofencingCircleAreaModel(BaseModel):
    areaType: Literal["CIRCLE"]
    center: GeofencingPointModel
    radius: int

class GeofencingAreaModel(GeofencingCircleAreaModel):
    pass

class GeofencingSubscriptionDetailModel(BaseModel):
    device: Optional[GeofencingDeviceModel] = None
    area: GeofencingAreaModel

class GeofencingConfigModel(BaseModel):
    subscriptionDetail: GeofencingSubscriptionDetailModel
    initialEvent: Optional[bool] = False
    subscriptionMaxEvents: Optional[int] = None
    subscriptionExpireTime: Optional[str] = None

class GeofencingSubscriptionRequestModel(BaseModel):
    protocol: Literal["HTTP"]
    sink: HttpUrl
    types: List[Literal[
        "org.camaraproject.geofencing-subscriptions.v0.area-entered",
        "org.camaraproject.geofencing-subscriptions.v0.area-left"
    ]]
    config: GeofencingConfigModel

class GeofencingSubscriptionResponseModel(BaseModel):
    protocol: Literal["HTTP"]
    sink: HttpUrl
    types: List[str]
    config: GeofencingConfigModel
    id: str
    startsAt: str
    status: Literal["ACTIVE"] = "ACTIVE"
    expiresAt: Optional[str] = None

# --- CloudEvent notification helpers ---

def send_cloudevent(sink: str, event_type: str, subscription: dict, device: dict, area: dict, termination_reason: Optional[str] = None):
    event_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    data = {
        "subscriptionId": subscription["id"],
        "device": device,
        "area": area
    }
    if event_type == "org.camaraproject.geofencing-subscriptions.v0.subscription-ends":
        data["terminationReason"] = termination_reason or "SUBSCRIPTION_EXPIRED"
    event = {
        "id": event_id,
        "source": "urn:nef-emulator",
        "type": event_type,
        "specversion": "1.0",
        "datacontenttype": "application/json",
        "time": now,
        "data": data
    }
    # Print every event sent (for debug/logging)
    print(f"\n[CloudEvent] Sending to {sink}:\n{event}\n")
    try:
        resp = requests.post(sink, json=event, timeout=5)
        print(f"[CloudEvent] Sent! HTTP {resp.status_code}")
        return {"sent": True, "status_code": resp.status_code}
    except Exception as e:
        print(f"[CloudEvent] Failed to send: {e}")
        return {"sent": False, "error": str(e)}

# --- Simple callback endpoint for local testing ---
@app.post("/callback")
async def receive_callback(event: dict):
    print(f"\n[Callback RECEIVED at /callback]:\n{event}\n")
    return {"received": True}

# --- Geofencing Monitor Thread ---

def haversine(lat1, lon1, lat2, lon2):
    from math import radians, cos, sin, sqrt, atan2
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2)**2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def geofencing_monitor():
    while True:
        now = datetime.now(timezone.utc)
        for sub_id, sub in list(geofencing_subscriptions.items()):
            # Check expiration
            expires_at = sub.get("expiresAt")
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if now >= expires_dt:
                    send_cloudevent(
                        sub["sink"],
                        "org.camaraproject.geofencing-subscriptions.v0.subscription-ends",
                        sub,
                        sub["config"]["subscriptionDetail"].get("device"),
                        sub["config"]["subscriptionDetail"]["area"],
                        termination_reason="SUBSCRIPTION_EXPIRED"
                    )
                    sub["status"] = "EXPIRED"
                    del geofencing_subscriptions[sub_id]
                    geofencing_states.pop(sub_id, None)
                    geofencing_events_count.pop(sub_id, None)
                    continue

            # Check max events
            max_events = sub["config"].get("subscriptionMaxEvents")
            if max_events is not None and geofencing_events_count.get(sub_id, 0) >= max_events:
                send_cloudevent(
                    sub["sink"],
                    "org.camaraproject.geofencing-subscriptions.v0.subscription-ends",
                    sub,
                    sub["config"]["subscriptionDetail"].get("device"),
                    sub["config"]["subscriptionDetail"]["area"],
                    termination_reason="MAX_EVENTS_REACHED"
                )
                sub["status"] = "EXPIRED"
                del geofencing_subscriptions[sub_id]
                geofencing_states.pop(sub_id, None)
                geofencing_events_count.pop(sub_id, None)
                continue

            # Get device info
            device = sub["config"]["subscriptionDetail"].get("device")
            if not device or not device.get("networkAccessIdentifier"):
                continue
            supi = device["networkAccessIdentifier"]
            area = sub["config"]["subscriptionDetail"]["area"]
            try:
                res = requests.get(
                    f"{NEF_URL}/api/v1/UEs/{supi}",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if res.status_code != 200:
                    continue
                ue = res.json()
                ue_lat = ue.get("latitude")
                ue_lon = ue.get("longitude")
                if ue_lat is None or ue_lon is None:
                    continue
                distance = haversine(ue_lat, ue_lon, area["center"]["latitude"], area["center"]["longitude"])
                inside = distance <= area["radius"]
                prev_state = geofencing_states.get(sub_id)
                event_type = sub["types"][0]
                # Initial event logic
                if prev_state is None:
                    geofencing_states[sub_id] = "inside" if inside else "outside"
                    if sub["config"].get("initialEvent"):
                        if inside and event_type == "org.camaraproject.geofencing-subscriptions.v0.area-entered":
                            send_cloudevent(sub["sink"], event_type, sub, device, area)
                            geofencing_events_count[sub_id] = geofencing_events_count.get(sub_id, 0) + 1
                        elif not inside and event_type == "org.camaraproject.geofencing-subscriptions.v0.area-left":
                            send_cloudevent(sub["sink"], event_type, sub, device, area)
                            geofencing_events_count[sub_id] = geofencing_events_count.get(sub_id, 0) + 1
                else:
                    # Detect transitions
                    if prev_state == "outside" and inside and event_type == "org.camaraproject.geofencing-subscriptions.v0.area-entered":
                        send_cloudevent(sub["sink"], event_type, sub, device, area)
                        geofencing_events_count[sub_id] = geofencing_events_count.get(sub_id, 0) + 1
                        geofencing_states[sub_id] = "inside"
                    elif prev_state == "inside" and not inside and event_type == "org.camaraproject.geofencing-subscriptions.v0.area-left":
                        send_cloudevent(sub["sink"], event_type, sub, device, area)
                        geofencing_events_count[sub_id] = geofencing_events_count.get(sub_id, 0) + 1
                        geofencing_states[sub_id] = "outside"
            except Exception:
                continue
        time.sleep(3)  # Check every 3 seconds

@app.on_event("startup")
def start_geofencing_monitor():
    threading.Thread(target=geofencing_monitor, daemon=True).start()

# --- Geofencing Endpoints ---

@app.post("/geofencing-subscriptions/v0.4/subscriptions", response_model=GeofencingSubscriptionResponseModel, status_code=201)
async def create_geofencing_subscription(body: GeofencingSubscriptionRequestModel):
    # Validate protocol
    if body.protocol != "HTTP":
        return JSONResponse(
            status_code=400,
            content={
                "status": 400,
                "code": "INVALID_PROTOCOL",
                "message": "Only HTTP is supported."
            }
        )
    # Validate device identifier
    device = body.config.subscriptionDetail.device
    if not device or not device.networkAccessIdentifier:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "MISSING_IDENTIFIER",
                "message": "Só é suportado networkAccessIdentifier (IMSI/SUPI) nesta implementação."
            }
        )
    # Validate area type
    area = body.config.subscriptionDetail.area
    if area.areaType != "CIRCLE":
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "GEOFENCING_SUBSCRIPTIONS.AREA_NOT_COVERED",
                "message": "Só é suportado areaType=CIRCLE."
            }
        )
    # Validate only one event type per subscription
    if len(body.types) != 1:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "MULTIEVENT_SUBSCRIPTION_NOT_SUPPORTED",
                "message": "Multi event types subscription not managed."
            }
        )
    # Validate radius (e.g. min 100)
    if area.radius < 100:
        return JSONResponse(
            status_code=422,
            content={
                "status": 422,
                "code": "GEOFENCING_SUBSCRIPTIONS.INVALID_AREA",
                "message": "The requested area is too small"
            }
        )
    # Simulate subscription creation
    sub_id = str(uuid4())
    starts_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    expires_at = None
    if body.config.subscriptionExpireTime:
        expires_at = body.config.subscriptionExpireTime
    subscription = {
        "protocol": body.protocol,
        "sink": str(body.sink),
        "types": body.types,
        "config": body.config.dict(),
        "id": sub_id,
        "startsAt": starts_at,
        "status": "ACTIVE",
        "expiresAt": expires_at
    }
    geofencing_subscriptions[sub_id] = subscription
    geofencing_events_count[sub_id] = 0
    return subscription

@app.get("/geofencing-subscriptions/v0.4/subscriptions", response_model=List[GeofencingSubscriptionResponseModel])
async def list_geofencing_subscriptions():
    return list(geofencing_subscriptions.values())

@app.get("/geofencing-subscriptions/v0.4/subscriptions/{subscription_id}", response_model=GeofencingSubscriptionResponseModel)
async def get_geofencing_subscription(subscription_id: str):
    sub = geofencing_subscriptions.get(subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub

@app.delete("/geofencing-subscriptions/v0.4/subscriptions/{subscription_id}", status_code=204)
async def delete_geofencing_subscription(subscription_id: str):
    sub = geofencing_subscriptions.get(subscription_id)
    if sub:
        send_cloudevent(
            sub["sink"],
            "org.camaraproject.geofencing-subscriptions.v0.subscription-ends",
            sub,
            sub["config"]["subscriptionDetail"].get("device"),
            sub["config"]["subscriptionDetail"]["area"],
            termination_reason="SUBSCRIPTION_DELETED"
        )
        del geofencing_subscriptions[subscription_id]
        geofencing_states.pop(subscription_id, None)
        geofencing_events_count.pop(subscription_id, None)
        return
    raise HTTPException(status_code=404, detail="Subscription not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9999)