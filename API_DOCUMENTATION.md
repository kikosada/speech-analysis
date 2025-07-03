# API Documentation - Análisis de Presentaciones Empresariales

## Descripción General

Esta API permite analizar presentaciones de video empresariales utilizando inteligencia artificial para evaluar la calidad y contenido de las presentaciones.

## Base URL

```
https://tu-dominio.onrender.com/api/v1
```

## Autenticación

La API utiliza autenticación basada en API Key. Incluye el header `X-API-Key` en todas las peticiones:

```
X-API-Key: tu-api-key-aqui
```

## Endpoints

### 1. Verificar Estado de la API

**GET** `/health`

Verifica que la API esté funcionando correctamente.

**Respuesta:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "azure_storage": "connected",
    "azure_speech": "connected",
    "openai": "connected"
  }
}
```

### 2. Obtener Token JWT

**POST** `/auth/token`

Obtiene un token JWT para autenticación (opcional).

**Body:**
```json
{
  "email": "usuario@ejemplo.com"
}
```

**Respuesta:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### 3. Subir y Analizar Presentación

**POST** `/presentations/upload`

Sube un archivo de video y lo analiza automáticamente.

**Headers:**
- `X-API-Key`: Tu API key
- `Content-Type`: `multipart/form-data`

**Body (form-data):**
- `file`: Archivo de video (mp4, webm, avi, mov, mkv)
- `rfc`: RFC de la empresa (obligatorio)
- `company_name`: Nombre de la empresa (opcional)
- `presenter_name`: Nombre del presentador (opcional)

**Respuesta:**
```json
{
  "success": true,
  "presentation_id": "ABC123456789",
  "analysis": {
    "scores": {
      "historia": 8,
      "mision_vision": 7,
      "productos": 9,
      "valores": 8,
      "mercado": 7,
      "logros": 8,
      "overall": 8
    },
    "feedback": [
      "Excelente presentación de la empresa",
      "Bien estructurada la información",
      "Podrías mejorar la explicación de productos"
    ],
    "resumen": "Presentación completa que cubre los aspectos principales de la empresa",
    "duracion_estimada": 120
  },
  "transcript": "Buenos días, hoy les voy a presentar nuestra empresa...",
  "message": "Presentación analizada exitosamente"
}
```

### 4. Obtener Análisis de Presentación

**GET** `/presentations/{rfc}`

Obtiene el análisis completo de una presentación por RFC.

**Headers:**
- `X-API-Key`: Tu API key

**Respuesta:**
```json
{
  "rfc": "ABC123456789",
  "company_name": "Mi Empresa S.A.",
  "presenter_name": "Juan Pérez",
  "filename": "presentacion.mp4",
  "transcript": "Buenos días, hoy les voy a presentar...",
  "analysis": {
    "scores": {
      "historia": 8,
      "mision_vision": 7,
      "productos": 9,
      "valores": 8,
      "mercado": 7,
      "logros": 8,
      "overall": 8
    },
    "feedback": [
      "Excelente presentación de la empresa",
      "Bien estructurada la información"
    ],
    "resumen": "Presentación completa que cubre los aspectos principales",
    "duracion_estimada": 120
  },
  "upload_timestamp": "2024-01-15T10:30:00",
  "status": "completed"
}
```

### 5. Verificar Estado de Procesamiento

**GET** `/presentations/{rfc}/status`

Verifica el estado de procesamiento de una presentación.

**Headers:**
- `X-API-Key`: Tu API key

**Respuesta:**
```json
{
  "rfc": "ABC123456789",
  "status": "completed",
  "message": "Presentación procesada exitosamente"
}
```

### 6. Listar Presentaciones

**GET** `/presentations`

Lista todas las presentaciones analizadas.

**Headers:**
- `X-API-Key`: Tu API key

**Query Parameters:**
- `limit`: Número máximo de resultados (default: 50)
- `offset`: Offset para paginación (default: 0)

**Respuesta:**
```json
{
  "presentations": [
    {
      "rfc": "ABC123456789",
      "company_name": "Empresa A",
      "analysis": { ... },
      "upload_timestamp": "2024-01-15T10:30:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 7. Analizar Transcript

**POST** `/analysis/transcript`

Analiza solo un texto sin necesidad de subir archivo.

**Headers:**
- `X-API-Key`: Tu API key
- `Content-Type`: `application/json`

**Body:**
```json
{
  "transcript": "Buenos días, hoy les voy a presentar nuestra empresa..."
}
```

**Respuesta:**
```json
{
  "transcript": "Buenos días, hoy les voy a presentar...",
  "analysis": {
    "scores": {
      "historia": 8,
      "mision_vision": 7,
      "productos": 9,
      "valores": 8,
      "mercado": 7,
      "logros": 8,
      "overall": 8
    },
    "feedback": [
      "Excelente presentación de la empresa"
    ],
    "resumen": "Presentación completa que cubre los aspectos principales",
    "duracion_estimada": 120
  }
}
```

### 8. Obtener Métricas

**GET** `/metrics`

Obtiene métricas de uso de la API.

**Headers:**
- `X-API-Key`: Tu API key

**Respuesta:**
```json
{
  "total_presentations": 150,
  "total_storage_size_mb": 2048.5,
  "api_version": "1.0.0"
}
```

## Códigos de Error

| Código | Descripción |
|--------|-------------|
| 400 | Bad Request - Datos incorrectos o faltantes |
| 401 | Unauthorized - API key inválida |
| 404 | Not Found - Recurso no encontrado |
| 500 | Internal Server Error - Error interno del servidor |

## Ejemplos de Uso

### JavaScript (Fetch)

```javascript
// Subir presentación
const formData = new FormData();
formData.append('file', videoFile);
formData.append('rfc', 'ABC123456789');
formData.append('company_name', 'Mi Empresa');

const response = await fetch('https://tu-dominio.onrender.com/api/v1/presentations/upload', {
  method: 'POST',
  headers: {
    'X-API-Key': 'tu-api-key'
  },
  body: formData
});

const result = await response.json();
console.log(result);
```

### Python (Requests)

```python
import requests

# Subir presentación
url = 'https://tu-dominio.onrender.com/api/v1/presentations/upload'
headers = {'X-API-Key': 'tu-api-key'}

with open('presentacion.mp4', 'rb') as f:
    files = {'file': f}
    data = {
        'rfc': 'ABC123456789',
        'company_name': 'Mi Empresa'
    }
    response = requests.post(url, headers=headers, files=files, data=data)

result = response.json()
print(result)
```

### cURL

```bash
# Subir presentación
curl -X POST \
  https://tu-dominio.onrender.com/api/v1/presentations/upload \
  -H 'X-API-Key: tu-api-key' \
  -F 'file=@presentacion.mp4' \
  -F 'rfc=ABC123456789' \
  -F 'company_name=Mi Empresa'

# Obtener análisis
curl -X GET \
  https://tu-dominio.onrender.com/api/v1/presentations/ABC123456789 \
  -H 'X-API-Key: tu-api-key'
```

## Configuración de Variables de Entorno

Para usar la API, necesitas configurar las siguientes variables de entorno:

```bash
# Azure Storage
AZURE_STORAGE_ACCOUNT_NAME=tu-cuenta
AZURE_STORAGE_ACCOUNT_KEY=tu-clave
AZURE_CONTAINER_NAME=clientai

# Azure Speech Services
AZURE_SPEECH_KEY=tu-clave-speech
AZURE_SPEECH_REGION=eastus

# OpenAI
OPENAI_API_KEY=tu-clave-openai

# API Key para autenticación
API_KEY=la_clave_secreta_de_kiko

# JWT Secret
JWT_SECRET_KEY=tu-jwt-secret
```

## Límites y Restricciones

- **Tamaño máximo de archivo**: 500MB
- **Formatos soportados**: mp4, webm, avi, mov, mkv
- **Límite de presentaciones por consulta**: 50 (configurable)
- **Rate limiting**: No implementado actualmente

## Soporte

Para soporte técnico o preguntas sobre la API, contacta al equipo de desarrollo. 