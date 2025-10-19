# Functional Tests for NEF NetApp Location APIs

## Test Plan for `/location-retrieval/v0.4/retrieve` and `/location-verification/v1/location/verify`

---

## 1. Location Retrieval API (`/location-retrieval/v0.4/retrieve`)

### ✔ Test Case 1: Retrieve location for a registered UE (happy path)

**Pre-Conditions:**
- The UE exists in the NEF Emulator DB (e.g., SUPI/IMSI: `202010000000001`)
- NetApp is authorized (valid token)

**Actions:**
- Send a POST request to `/location-retrieval/v0.4/retrieve` with:
    ```json
    {
      "device": {
        "networkAccessIdentifier": "202010000000001"
      }
    }
    ```

**Expected Result:**
- 200 OK
- Response body:
    ```json
    {
      "lastLocationTime": "<timestamp>",
      "area": {
        "areaType": "CIRCLE",
        "center": {
          "latitude": <float>,
          "longitude": <float>
        },
        "radius": 100
      }
    }
    ```

---

### ❌ Test Case 2: Retrieve location with missing device identifier

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with:
    ```json
    {
      "device": {}
    }
    ```

**Expected Result:**
- 422 Unprocessable Entity
- Response body:
    ```json
    {
      "status": 422,
      "code": "MISSING_IDENTIFIER",
      "message": "Só é suportado networkAccessIdentifier (IMSI/SUPI) nesta implementação."
    }
    ```

---

### ❌ Test Case 3: Retrieve location for non-existent UE

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with a non-existent SUPI:
    ```json
    {
      "device": {
        "networkAccessIdentifier": "999999999999999"
      }
    }
    ```

**Expected Result:**
- 404 Not Found
- Response body:
    ```json
    {
      "status": 404,
      "code": "LOCATION_RETRIEVAL.DEVICE_NOT_FOUND",
      "message": "The location server is not able to locate the mobile"
    }
    ```

---

### ❌ Test Case 4: Retrieve location with `maxAge=0` (not supported)

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with:
    ```json
    {
      "device": {
        "networkAccessIdentifier": "202010000000001"
      },
      "maxAge": 0
    }
    ```

**Expected Result:**
- 422 Unprocessable Entity
- Response body:
    ```json
    {
      "status": 422,
      "code": "LOCATION_RETRIEVAL.UNABLE_TO_FULFILL_MAX_AGE",
      "message": "Unable to provide expected freshness for location"
    }
    ```

---

### ❌ Test Case 5: Retrieve location with `maxSurface` (not supported)

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with:
    ```json
    {
      "device": {
        "networkAccessIdentifier": "202010000000001"
      },
      "maxSurface": 100
    }
    ```

**Expected Result:**
- 422 Unprocessable Entity
- Response body:
    ```json
    {
      "status": 422,
      "code": "LOCATION_RETRIEVAL.UNABLE_TO_FULFILL_MAX_SURFACE",
      "message": "Unable to provide accurate acceptable surface for location"
    }
    ```

---

### ⛔ Test Case 6: Retrieve location without authentication

**Pre-Conditions:**
- NetApp is NOT authorized (no token or invalid token)

**Actions:**
- Send a POST request as above

**Expected Result:**
- 401 Unauthorized
- Response body:
    ```json
    {
      "status": 401,
      "code": "UNAUTHENTICATED",
      "message": "Token de acesso não disponível."
    }
    ```

---

## 2. Location Verification API (`/location-verification/v1/location/verify`)

### ✔ Test Case 7: Verify location inside area (happy path)

**Pre-Conditions:**
- The UE exists in the NEF Emulator DB and is located within the area
- NetApp is authorized

**Actions:**
- Send a POST request to `/location-verification/v1/location/verify` with:
    ```json
    {
      "device": {
        "networkAccessIdentifier": "202010000000001"
      },
      "area": {
        "areaType": "CIRCLE",
        "center": {
          "latitude": <lat>,
          "longitude": <lon>
        },
        "radius": 100
      }
    }
    ```

**Expected Result:**
- 200 OK
- Response body:
    ```json
    {
      "verificationResult": "TRUE",
      "lastLocationTime": "<timestamp>",
      "distance": <float>
    }
    ```

---

### ✔ Test Case 8: Verify location outside area

**Pre-Conditions:**
- The UE exists in the NEF Emulator DB and is located outside the area
- NetApp is authorized

**Actions:**
- Send a POST request as above, but with a center far from the UE

**Expected Result:**
- 200 OK
- Response body:
    ```json
    {
      "verificationResult": "FALSE",
      "lastLocationTime": "<timestamp>",
      "distance": <float>
    }
    ```

---

### ❌ Test Case 9: Verify location with missing device identifier

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with:
    ```json
    {
      "device": {},
      "area": {
        "areaType": "CIRCLE",
        "center": {
          "latitude": 0,
          "longitude": 0
        },
        "radius": 100
      }
    }
    ```

**Expected Result:**
- 422 Unprocessable Entity
- Response body:
    ```json
    {
      "status": 422,
      "code": "MISSING_IDENTIFIER",
      "message": "Só é suportado networkAccessIdentifier (IMSI/SUPI) nesta implementação."
    }
    ```

---

### ❌ Test Case 10: Verify location with areaType not supported

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with:
    ```json
    {
      "device": {
        "networkAccessIdentifier": "202010000000001"
      },
      "area": {
        "areaType": "POLYGON",
        "center": {
          "latitude": 0,
          "longitude": 0
        },
        "radius": 100
      }
    }
    ```

**Expected Result:**
- 422 Unprocessable Entity
- Response body:
    ```json
    {
      "status": 422,
      "code": "LOCATION_VERIFICATION.AREA_NOT_COVERED",
      "message": "Só é suportado areaType=CIRCLE."
    }
    ```

---

### ❌ Test Case 11: Verify location for non-existent UE

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with a non-existent SUPI

**Expected Result:**
- 404 Not Found
- Response body:
    ```json
    {
      "status": 404,
      "code": "IDENTIFIER_NOT_FOUND",
      "message": "Identificador do dispositivo não encontrado."
    }
    ```

---

### ⛔ Test Case 12: Verify location without authentication

**Pre-Conditions:**
- NetApp is NOT authorized

**Actions:**
- Send a POST request as above

**Expected Result:**
- 401 Unauthorized
- Response body:
    ```json
    {
      "status": 401,
      "code": "UNAUTHENTICATED",
      "message": "Token de acesso não disponível."
    }
    ```

---

### ❌ Test Case 13: Verify location with missing area center

**Pre-Conditions:**
- NetApp is authorized

**Actions:**
- Send a POST request with missing latitude/longitude in area.center

**Expected Result:**
- 422 Unprocessable Entity
- Response body:
    ```json
    {
      "status": 422,
      "code": "LOCATION_VERIFICATION.INVALID_AREA",
      "message": "Latitude e longitude do centro são obrigatórios."
    }
    ```

---

## Notas sobre limitações

- Só é suportado `networkAccessIdentifier` (IMSI/SUPI) como identificador.
- Só é suportado `areaType: "CIRCLE"` e raio fixo na resposta.
- `maxAge` e `maxSurface` não são suportados.
- Não há precisão real nem histórico de localização.
- O token é sempre o mesmo (não há consent real).

---