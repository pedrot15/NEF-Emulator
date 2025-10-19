# Device Location APIs - Architecture Documentation

## Table of Contents
- [Phase 1: NEF Emulator Environment](#phase-1-nef-emulator-environment)
  - [Architecture Overview](#architecture-overview)
  - [Location Retrieval Flow](#location-retrieval-flow)
  - [Location Verification Flow](#location-verification-flow)
  - [Data Flow Diagram](#data-flow-diagram)
- [Phase 2: Real-World 5G Network](#phase-2-real-world-5g-network)
  - [Real 5G Network Architecture](#real-5g-network-architecture)
  - [Real-World Location Retrieval](#real-world-location-retrieval)
  - [Real-World Geofencing with Events](#real-world-geofencing-with-events)
  - [Network Function Interactions](#network-function-interactions)
  - [Positioning Methods](#positioning-methods-in-real-5g)
- [Key Differences](#key-differences)
- [API Endpoints Summary](#api-endpoints-summary)

---

## Phase 1: NEF Emulator Environment

### Architecture Overview

```mermaid
graph TB
    subgraph "External Application"
        APP[Application Server<br/>e.g., Location-based Service]
    end

    subgraph "NEF Emulator - Docker Container"
        subgraph "CAMARA APIs /camaraAPI"
            LR[Location Retrieval<br/>POST /location-retrieval/v0.4/retrieve]
            LV[Location Verification<br/>POST /location-verification/v1/location/verify]
            HEALTH[Health Check<br/>GET /health]
        end
        
        subgraph "Authentication"
            AUTH[JWT Authentication<br/>Bearer Token]
        end
        
        subgraph "Database Layer"
            POSTGRES[(PostgreSQL<br/>UE Data)]
            MONGO[(MongoDB<br/>Subscriptions)]
        end
    end

    APP -->|1. Login| AUTH
    AUTH -->|2. Token| APP
    APP -->|3. Request Location<br/>+ Bearer Token| LR
    APP -->|4. Verify Location<br/>+ Bearer Token| LV
    LR -->|5. Query UE| POSTGRES
    LV -->|6. Query UE| POSTGRES
    POSTGRES -->|7. UE Data<br/>lat, lon, supi| LR
    POSTGRES -->|8. UE Data| LV
    LR -->|9. Location Response| APP
    LV -->|10. Verification Result| APP

    style APP fill:#e1f5ff
    style LR fill:#c3e88d
    style LV fill:#c3e88d
    style POSTGRES fill:#ffb3ba
    style AUTH fill:#ffffba
```

### Location Retrieval Flow

```mermaid
sequenceDiagram
    participant App as Application Server
    participant NEF as NEF Emulator<br/>(FastAPI)
    participant Auth as Authentication
    participant DB as PostgreSQL<br/>(UE Database)
    
    Note over App,DB: Phase 1: NEF Emulator Environment
    
    App->>NEF: POST /api/v1/login/access-token<br/>{username, password}
    NEF->>Auth: Validate credentials
    Auth-->>NEF: User validated
    NEF-->>App: 200 OK<br/>{access_token: "eyJhbG..."}
    
    Note over App,DB: Location Retrieval Request
    
    App->>NEF: POST /camaraAPI/api/v1/location-retrieval/v0.4/retrieve<br/>Header: Authorization: Bearer eyJhbG...<br/>Body: {device: {networkAccessIdentifier: "202010000000001"}}
    NEF->>Auth: Verify JWT token
    Auth-->>NEF: Token valid, user_id: 1
    
    NEF->>NEF: Validate request<br/>- Check maxAge<br/>- Check maxSurface<br/>- Check networkAccessIdentifier
    
    NEF->>DB: SELECT * FROM ue<br/>WHERE supi = '202010000000001'
    DB-->>NEF: UE {<br/>  supi: "202010000000001",<br/>  latitude: 37.999071,<br/>  longitude: 23.818063,<br/>  owner_id: 1<br/>}
    
    NEF->>NEF: Calculate response<br/>- lastLocationTime: now()<br/>- area: CIRCLE with radius 100m
    
    NEF-->>App: 200 OK<br/>{<br/>  lastLocationTime: "2025-10-01T22:39:18Z",<br/>  area: {<br/>    areaType: "CIRCLE",<br/>    center: {lat: 37.999071, lon: 23.818063},<br/>    radius: 100<br/>  }<br/>}
    
    Note over App,DB: Location stored in notifications log
```

### Location Verification Flow

```mermaid
sequenceDiagram
    participant App as Application Server
    participant NEF as NEF Emulator<br/>(FastAPI)
    participant Auth as Authentication
    participant DB as PostgreSQL<br/>(UE Database)
    participant Calc as Haversine<br/>Calculator
    
    Note over App,Calc: Phase 1: NEF Emulator Environment
    
    App->>NEF: POST /camaraAPI/api/v1/location-verification/v1/location/verify<br/>Header: Authorization: Bearer token<br/>Body: {<br/>  device: {networkAccessIdentifier: "202010000000001"},<br/>  area: {<br/>    areaType: "CIRCLE",<br/>    center: {lat: 38.0, lon: 23.8},<br/>    radius: 2000<br/>  }<br/>}
    
    NEF->>Auth: Verify JWT token
    Auth-->>NEF: Token valid
    
    NEF->>NEF: Validate request<br/>- Check areaType = CIRCLE<br/>- Check center coordinates<br/>- Check networkAccessIdentifier
    
    NEF->>DB: SELECT * FROM ue<br/>WHERE supi = '202010000000001'
    DB-->>NEF: UE {<br/>  latitude: 37.999071,<br/>  longitude: 23.818063<br/>}
    
    NEF->>Calc: haversine(<br/>  ue_lat: 37.999071,<br/>  ue_lon: 23.818063,<br/>  ref_lat: 38.0,<br/>  ref_lon: 23.8<br/>)
    Calc-->>NEF: distance: 105.32 meters
    
    NEF->>NEF: Compare distance with radius<br/>105.32m <= 2000m = TRUE
    
    NEF-->>App: 200 OK<br/>{<br/>  verificationResult: "TRUE",<br/>  lastLocationTime: "2025-10-01T22:39:18Z",<br/>  distance: 105.32<br/>}
```

### Data Flow Diagram

```mermaid
graph LR
    subgraph "Input"
        REQ[API Request<br/>networkAccessIdentifier:<br/>"202010000000001"]
    end
    
    subgraph "NEF Emulator Processing"
        AUTH[Authentication<br/>Verify Bearer Token]
        VAL[Validation<br/>Check Parameters]
        CRUD[CRUD Layer<br/>crud.ue.get_supi]
        CALC[Calculation<br/>Haversine / Response]
        LOG[Logging<br/>ReportLogging]
    end
    
    subgraph "Storage"
        PG[(PostgreSQL<br/>UE Table)]
        MG[(MongoDB<br/>Notifications)]
    end
    
    subgraph "Output"
        RESP[API Response<br/>Location / Verification]
    end
    
    REQ --> AUTH
    AUTH --> VAL
    VAL --> CRUD
    CRUD --> PG
    PG --> CALC
    CALC --> RESP
    CALC --> LOG
    LOG --> MG
    
    style REQ fill:#e1f5ff
    style RESP fill:#c3e88d
    style PG fill:#ffb3ba
    style MG fill:#ffb3ba
```

---

## Phase 2: Real-World 5G Network

### Real 5G Network Architecture

```mermaid
graph TB
    subgraph "Application Layer"
        APP[Third-Party<br/>Application Server<br/>Location-based Services]
    end
    
    subgraph "5G Core Network (5GC)"
        subgraph "Network Exposure Function"
            NEF[NEF<br/>Network Exposure<br/>Function]
            CAPIF[CAPIF<br/>API Gateway]
        end
        
        subgraph "Network Functions"
            AMF[AMF<br/>Access & Mobility<br/>Management]
            SMF[SMF<br/>Session Management]
            UDM[UDM<br/>Unified Data<br/>Management]
            GMLC[GMLC<br/>Gateway Mobile<br/>Location Center]
            LMF[LMF<br/>Location<br/>Management]
        end
        
        subgraph "Data Network"
            UDR[(UDR<br/>Unified Data<br/>Repository)]
        end
    end
    
    subgraph "Radio Access Network"
        GNB[gNodeB<br/>5G Base Station]
    end
    
    subgraph "User Equipment"
        UE[UE<br/>Mobile Device<br/>SUPI: 202010000000001]
    end
    
    APP -->|1. CAMARA API Request| CAPIF
    CAPIF -->|2. Authenticate & Route| NEF
    NEF -->|3. Location Request| GMLC
    GMLC -->|4. Query Location| LMF
    LMF -->|5. Request Measurement| GNB
    GNB <-->|6. Positioning Protocol| UE
    GNB -->|7. Position Report| LMF
    LMF -->|8. Location Data| GMLC
    GMLC -->|9. Location Response| NEF
    NEF -->|10. CAMARA Response| CAPIF
    CAPIF -->|11. Location Result| APP
    
    NEF -.->|Query Subscriber| UDM
    UDM -.->|Subscriber Data| UDR
    AMF -.->|Registration State| NEF
    SMF -.->|Session Info| NEF

    style APP fill:#e1f5ff
    style NEF fill:#c3e88d
    style GMLC fill:#ffd4a3
    style LMF fill:#ffd4a3
    style UE fill:#d4c5f9
    style GNB fill:#f5c2e7
```

### Real-World Location Retrieval

```mermaid
sequenceDiagram
    participant App as 3rd Party App
    participant CAPIF as CAPIF
    participant NEF as NEF
    participant UDM as UDM
    participant GMLC as GMLC
    participant LMF as LMF
    participant gNB as gNodeB
    participant UE as UE Device
    
    Note over App,UE: Phase 2: Real 5G Network
    
    App->>CAPIF: HTTPS POST /location-retrieval/v0.4/retrieve<br/>{device: {networkAccessIdentifier: "202010000000001"}}<br/>OAuth 2.0 Token
    
    CAPIF->>CAPIF: Validate OAuth token<br/>Check API permissions
    CAPIF->>NEF: Forward Location Request<br/>Internal API (Nnef)
    
    NEF->>NEF: Map networkAccessIdentifier to SUPI<br/>Apply policies & privacy rules
    
    NEF->>UDM: Nudm_UECM_Get<br/>Query UE Context<br/>(SUPI: 202010000000001)
    UDM-->>NEF: UE Context<br/>{registration_state, serving_network,<br/>AMF address}
    
    NEF->>GMLC: Ngmlc_Location_Get<br/>Request UE Location<br/>(SUPI, QoS requirements)
    
    GMLC->>LMF: Nlmf_Location_Determine<br/>Initiate location determination
    
    LMF->>gNB: NG-AP: Location Reporting Control<br/>Request positioning measurements
    
    gNB->>UE: NR Positioning Protocol (NRPPa)<br/>Request position measurements<br/>(e.g., PRS, SRS, RTT)
    
    UE->>UE: Perform measurements<br/>- GNSS (GPS/Galileo)<br/>- 5G NR positioning<br/>- Cell-ID
    
    UE-->>gNB: Positioning measurements<br/>{signal timings, RSRP, GNSS data}
    
    gNB->>gNB: Calculate initial position<br/>using Cell-ID, timing advance
    
    gNB-->>LMF: NG-AP: Location Report<br/>{measurements, estimated position}
    
    LMF->>LMF: Positioning calculation<br/>- Multi-lateration<br/>- Kalman filtering<br/>- Accuracy estimation
    
    LMF-->>GMLC: Position Result<br/>{latitude: 37.999071,<br/>longitude: 23.818063,<br/>accuracy: 10m,<br/>timestamp}
    
    GMLC-->>NEF: Location Response<br/>Ngmlc_Location_Get Response
    
    NEF->>NEF: Format to CAMARA standard<br/>Apply data minimization<br/>Add compliance metadata
    
    NEF-->>CAPIF: CAMARA Location Response
    
    CAPIF-->>App: HTTPS 200 OK<br/>{<br/>  lastLocationTime: "2025-10-01T22:39:18Z",<br/>  area: {<br/>    areaType: "CIRCLE",<br/>    center: {lat: 37.999071, lon: 23.818063},<br/>    radius: 10<br/>  }<br/>}
    
    Note over App,UE: Actual accuracy depends on<br/>positioning method & environment
```

### Real-World Geofencing with Events

```mermaid
sequenceDiagram
    participant App as 3rd Party App
    participant CAPIF as CAPIF
    participant NEF as NEF
    participant GMLC as GMLC
    participant LMF as LMF
    participant AMF as AMF
    
    Note over App,AMF: Phase 2: Real 5G Network with Event Subscription
    
    App->>CAPIF: POST /geofencing-subscriptions/v0.4/subscriptions<br/>{<br/>  sink: "https://app.example.com/callback",<br/>  types: ["area-entered"],<br/>  config: {<br/>    device: {networkAccessIdentifier: "202010..."},<br/>    area: {center: {lat, lon}, radius: 2000}<br/>  }<br/>}
    
    CAPIF->>NEF: Create Monitoring Subscription<br/>Internal Service-based Interface
    
    NEF->>NEF: Validate & transform<br/>to 3GPP Monitoring Event
    
    NEF->>AMF: Namf_EventExposure_Subscribe<br/>Event: LOCATION_REPORT<br/>UE: SUPI 202010...<br/>Reporting: Immediate + Periodic
    
    AMF->>AMF: Create location<br/>monitoring context for UE
    
    AMF-->>NEF: Subscription Created<br/>{subscription_id, correlation_id}
    
    NEF-->>CAPIF: CAMARA Subscription Response<br/>{id, status: "ACTIVE", link}
    
    CAPIF-->>App: 201 Created<br/>{id: "uuid", status: "ACTIVE"}
    
    Note over App,AMF: UE moves and enters geofence area
    
    AMF->>AMF: Detect UE mobility<br/>Registration update / TAU
    
    AMF->>GMLC: Request current location<br/>for monitoring evaluation
    
    GMLC->>LMF: Get precise location
    LMF-->>GMLC: {lat, lon, accuracy}
    GMLC-->>AMF: Location data
    
    AMF->>AMF: Evaluate geofence<br/>Calculate: haversine(UE_pos, fence_center)<br/>Result: distance <= radius → ENTERED
    
    AMF->>NEF: Namf_EventExposure_Notify<br/>{<br/>  event: LOCATION_REPORT,<br/>  SUPI: "202010...",<br/>  location: {lat, lon},<br/>  geofence_status: ENTERED<br/>}
    
    NEF->>NEF: Transform to CAMARA CloudEvent<br/>Apply privacy policies
    
    NEF->>CAPIF: CloudEvent Notification
    
    CAPIF->>App: POST https://app.example.com/callback<br/>CloudEvent:<br/>{<br/>  type: "area-entered",<br/>  data: {<br/>    subscriptionId: "uuid",<br/>    device: {...},<br/>    area: {...}<br/>  }<br/>}
    
    App-->>CAPIF: 204 No Content
    
    Note over App,AMF: Continuous monitoring until<br/>subscription expires or is deleted
```

### Network Function Interactions

```mermaid
graph TB
    subgraph "Application Domain"
        APP[Third-Party Application<br/>Location-based Service]
    end
    
    subgraph "Exposure Layer"
        CAPIF[CAPIF<br/>Common API Framework<br/>- OAuth 2.0<br/>- Rate limiting<br/>- API discovery]
        NEF[NEF<br/>Network Exposure Function<br/>- Policy enforcement<br/>- Privacy filtering<br/>- Protocol translation]
    end
    
    subgraph "Control Plane"
        AMF[AMF<br/>Access & Mobility Management<br/>- UE registration state<br/>- Location tracking<br/>- Event subscriptions]
        
        SMF[SMF<br/>Session Management<br/>- PDU session info<br/>- UE IP address]
        
        UDM[UDM<br/>Unified Data Management<br/>- Subscriber profile<br/>- Location privacy settings<br/>- Service permissions]
    end
    
    subgraph "Location Services"
        GMLC[GMLC<br/>Gateway Mobile Location Center<br/>- Location service interface<br/>- Privacy verification<br/>- Location routing]
        
        LMF[LMF<br/>Location Management Function<br/>- Position calculation<br/>- Assistance data<br/>- Measurement coordination]
    end
    
    subgraph "User Plane"
        UPF[UPF<br/>User Plane Function<br/>- Packet routing<br/>- QoS enforcement]
    end
    
    subgraph "RAN"
        gNB[gNodeB<br/>- Positioning measurements<br/>- Beam management<br/>- Cell-ID]
    end
    
    subgraph "Device"
        UE[UE<br/>User Equipment<br/>- GNSS receiver<br/>- NR positioning<br/>- Measurement reports]
    end
    
    APP <-->|CAMARA APIs<br/>HTTPS/REST| CAPIF
    CAPIF <-->|Service APIs| NEF
    NEF <-->|Nnef| AMF
    NEF <-->|Nnef| SMF
    NEF <-->|Nnef| UDM
    NEF <-->|Nnef| GMLC
    
    GMLC <-->|Nlmf| LMF
    LMF <-->|NG-AP/NRPPa| gNB
    AMF <-->|N1/N2| gNB
    SMF <-->|N4| UPF
    UPF <-->|N3| gNB
    gNB <-->|NR Radio| UE
    
    style APP fill:#e1f5ff
    style CAPIF fill:#c3e88d
    style NEF fill:#c3e88d
    style GMLC fill:#ffd4a3
    style LMF fill:#ffd4a3
    style UE fill:#d4c5f9
```

### Positioning Methods in Real 5G

```mermaid
graph TD
    subgraph "Positioning Methods"
        A[Location Request]
        
        A --> B{Accuracy<br/>Requirement}
        
        B -->|Low<br/>100m-1km| C[Cell-ID Based]
        B -->|Medium<br/>10-100m| D[Enhanced Cell-ID<br/>+ Timing Advance]
        B -->|High<br/>1-10m| E[Multi-RAT<br/>Positioning]
        B -->|Very High<br/><1m| F[GNSS<br/>GPS/Galileo]
        
        C --> G[gNodeB Cell Info]
        D --> H[RTT Measurements]
        E --> I[5G NR PRS<br/>Positioning Reference Signals]
        F --> J[Satellite Signals]
        
        G --> K[LMF Calculation]
        H --> K
        I --> K
        J --> K
        
        K --> L[Position Result<br/>Latitude, Longitude<br/>Accuracy estimate]
    end
    
    style A fill:#e1f5ff
    style L fill:#c3e88d
    style K fill:#ffd4a3
```

---

## Key Differences

| Aspect | Phase 1 (NEF Emulator) | Phase 2 (Real 5G Network) |
|--------|------------------------|---------------------------|
| **Location Source** | Static PostgreSQL database | Real-time positioning (GNSS, NR, Cell-ID) |
| **Accuracy** | Fixed 100m radius | Variable (1m - 1km) based on method |
| **Network Functions** | Single FastAPI application | Multiple 5GC NFs (NEF, AMF, GMLC, LMF, etc.) |
| **Protocols** | HTTP/REST only | Service-based interfaces (SBI), NG-AP, NRPPa |
| **Authentication** | Simple JWT | OAuth 2.0 + CAPIF + Network policies |
| **Real-time Updates** | Thread-based monitoring | Event-based subscriptions via AMF |
| **Privacy** | Basic owner_id check | Multi-layer privacy (UDM policies, NEF filtering, GDPR) |
| **Latency** | ~10-50ms | ~100-500ms (depends on positioning method) |
| **Scalability** | Single container | Distributed microservices |
| **Standards** | CAMARA API spec | CAMARA + 3GPP TS 23.502, 23.273, 38.305 |

---

## API Endpoints Summary

### NEF Emulator Endpoints

#### 1. Location Retrieval
- **Endpoint**: `POST /camaraAPI/api/v1/location-retrieval/v0.4/retrieve`
- **Description**: Returns current device location from database
- **Authentication**: JWT Bearer Token
- **Request Body**:
```json
{
  "device": {
    "networkAccessIdentifier": "202010000000001"
  },
  "maxAge": 60,
  "maxSurface": null
}
```
- **Response**:
```json
{
  "lastLocationTime": "2025-10-01T22:39:18Z",
  "area": {
    "areaType": "CIRCLE",
    "center": {
      "latitude": 37.999071,
      "longitude": 23.818063
    },
    "radius": 100
  }
}
```

#### 2. Location Verification
- **Endpoint**: `POST /camaraAPI/api/v1/location-verification/v1/location/verify`
- **Description**: Verifies if device is within specified area
- **Authentication**: JWT Bearer Token
- **Request Body**:
```json
{
  "device": {
    "networkAccessIdentifier": "202010000000001"
  },
  "area": {
    "areaType": "CIRCLE",
    "center": {
      "latitude": 38.0,
      "longitude": 23.8
    },
    "radius": 2000
  }
}
```
- **Response**:
```json
{
  "verificationResult": "TRUE",
  "lastLocationTime": "2025-10-01T22:39:18Z",
  "distance": 105.32
}
```

#### 3. Health Check
- **Endpoint**: `GET /camaraAPI/api/v1/health`
- **Description**: Returns API health status
- **Authentication**: None required
- **Response**:
```json
{
  "status": "healthy",
  "apis": [
    "Location Retrieval v0.4",
    "Location Verification v1",
    "Geofencing Subscriptions v0.4"
  ],
  "integration": "NEF-Emulator",
  "timestamp": "2025-10-01T22:39:18Z"
}
```

---

## Implementation Details

### NEF Emulator Limitations

1. **Fixed Accuracy**: Always returns 100m radius (NEF-Emulator doesn't calculate actual positioning accuracy)
2. **Database-Only**: Location data comes from PostgreSQL, not real network measurements
3. **CIRCLE Only**: Only supports circular geofence areas (per CAMARA spec simplification)
4. **networkAccessIdentifier Only**: Only supports SUPI/IMSI identifier (no phone number, IP address, etc.)
5. **Thread-Based Monitoring**: Uses Python threading instead of event-driven architecture

### Real 5G Network Capabilities

1. **Dynamic Accuracy**: Varies from sub-meter (GNSS) to kilometer (Cell-ID) based on method
2. **Real-Time Positioning**: Active measurements from UE and gNodeB
3. **Multiple Positioning Methods**:
   - **Cell-ID**: Based on serving cell (100m-1km accuracy)
   - **Enhanced Cell-ID**: + Timing Advance (10-100m)
   - **OTDOA/RTT**: Multi-lateration using multiple gNodeBs (1-10m)
   - **GNSS**: GPS/Galileo/BeiDou integration (sub-meter)
   - **Hybrid**: Combination of methods for optimal accuracy
4. **Privacy & Policy Enforcement**: Multi-layer checks (UDM subscriber settings, NEF policies, GDPR compliance)
5. **Event-Driven**: AMF provides real-time notifications on mobility events

---

## References

### CAMARA Project
- **GitHub**: https://github.com/camaraproject/DeviceLocation
- **API Spec**: Device Location v0.4
- **OpenAPI**: https://github.com/camaraproject/DeviceLocation/blob/main/code/API_definitions/geofencing-subscriptions.yaml

### 3GPP Standards
- **TS 23.502**: Procedures for the 5G System (5GS)
- **TS 23.273**: 5G System (5GS) Location Services (LCS)
- **TS 38.305**: Stage 2 functional specification of User Equipment (UE) positioning in NG-RAN
- **TS 29.522**: 5G System; Network Exposure Function Northbound APIs

### NEF Emulator
- **Repository**: https://github.com/5gasp/NEF-Emulator
- **Documentation**: See `/docs` folder in repository

---

## Usage Examples

### Example 1: Get UE Location

```bash
# 1. Login and get token
curl -X POST "http://192.168.56.131:8888/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin"

# Response: {"access_token": "eyJhbGc...", "token_type": "bearer"}

# 2. Request location
curl -X POST "http://192.168.56.131:8888/camaraAPI/api/v1/location-retrieval/v0.4/retrieve" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "device": {
      "networkAccessIdentifier": "202010000000001"
    }
  }'
```

### Example 2: Verify UE in Area

```bash
curl -X POST "http://192.168.56.131:8888/camaraAPI/api/v1/location-verification/v1/location/verify" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "device": {
      "networkAccessIdentifier": "202010000000001"
    },
    "area": {
      "areaType": "CIRCLE",
      "center": {
        "latitude": 37.999071,
        "longitude": 23.818063
      },
      "radius": 2000
    }
  }'
```

---

## License

This documentation is part of the NEF-Emulator project.

**Last Updated**: October 19, 2025
