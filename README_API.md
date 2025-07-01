# API de Análisis de Presentaciones Empresariales

## Descripción

Esta API permite analizar presentaciones de video empresariales utilizando inteligencia artificial para evaluar la calidad y contenido de las presentaciones. La API está diseñada para ser fácilmente integrable en otras aplicaciones.

## Características Principales

- ✅ **Análisis de Video**: Sube archivos de video y obtén análisis automático
- ✅ **Transcripción**: Conversión automática de audio a texto
- ✅ **Análisis AI**: Evaluación inteligente usando OpenAI GPT-4
- ✅ **Almacenamiento**: Guardado seguro en Azure Blob Storage
- ✅ **API REST**: Endpoints RESTful bien documentados
- ✅ **Autenticación**: Sistema de API keys para seguridad
- ✅ **Métricas**: Estadísticas de uso y almacenamiento

## Instalación y Configuración

### 1. Variables de Entorno

Configura las siguientes variables de entorno en tu servidor:

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
API_KEY=tu-api-key-secreta

# JWT Secret
JWT_SECRET_KEY=tu-jwt-secret

# Otras configuraciones
SECRET_KEY=tu-secret-key
```

### 2. Dependencias

Asegúrate de tener instaladas las siguientes dependencias:

```bash
pip install -r requirements.txt
```

### 3. Despliegue

La API está lista para desplegarse en Render. El archivo `render.yaml` ya está configurado.

## Uso Rápido

### 1. Verificar Estado

```bash
curl https://tu-dominio.onrender.com/api/v1/health
```

### 2. Subir Presentación

```bash
curl -X POST \
  https://tu-dominio.onrender.com/api/v1/presentations/upload \
  -H 'X-API-Key: tu-api-key' \
  -F 'file=@presentacion.mp4' \
  -F 'rfc=ABC123456789' \
  -F 'company_name=Mi Empresa'
```

### 3. Obtener Análisis

```bash
curl -X GET \
  https://tu-dominio.onrender.com/api/v1/presentations/ABC123456789 \
  -H 'X-API-Key: tu-api-key'
```

## Integración en Otras Aplicaciones

### JavaScript/Node.js

```javascript
const api = new PresentationAnalysisAPI('https://tu-dominio.onrender.com/api/v1', 'tu-api-key');

// Subir presentación
const result = await api.uploadPresentation(file, 'ABC123456789', 'Mi Empresa');
console.log('Puntuación:', result.analysis.scores.overall);

// Analizar transcript
const analysis = await api.analyzeTranscript('Texto de la presentación...');
```

### Python

```python
api = PresentationAnalysisAPI('https://tu-dominio.onrender.com/api/v1', 'tu-api-key')

# Subir presentación
result = api.upload_presentation('presentacion.mp4', 'ABC123456789', 'Mi Empresa')
print(f"Puntuación: {result['analysis']['scores']['overall']}")

# Analizar transcript
analysis = api.analyze_transcript('Texto de la presentación...')
```

### PHP

```php
$api = new PresentationAnalysisAPI('https://tu-dominio.onrender.com/api/v1', 'tu-api-key');

// Subir presentación
$result = $api->uploadPresentation('presentacion.mp4', 'ABC123456789', 'Mi Empresa');
echo "Puntuación: " . $result['analysis']['scores']['overall'];
```

## Endpoints Principales

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Estado de la API |
| POST | `/presentations/upload` | Subir y analizar video |
| GET | `/presentations/{rfc}` | Obtener análisis |
| GET | `/presentations/{rfc}/status` | Estado de procesamiento |
| GET | `/presentations` | Listar presentaciones |
| POST | `/analysis/transcript` | Analizar texto |
| GET | `/metrics` | Métricas de uso |

## Estructura de Respuesta

### Análisis de Presentación

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
      "Bien estructurada la información"
    ],
    "resumen": "Presentación completa que cubre los aspectos principales",
    "duracion_estimada": 120
  },
  "transcript": "Buenos días, hoy les voy a presentar...",
  "message": "Presentación analizada exitosamente"
}
```

## Límites y Restricciones

- **Tamaño máximo de archivo**: 500MB
- **Formatos soportados**: mp4, webm, avi, mov, mkv
- **Límite de presentaciones por consulta**: 50 (configurable)
- **Rate limiting**: No implementado actualmente

## Manejo de Errores

La API devuelve códigos de estado HTTP estándar:

- `200`: Éxito
- `400`: Bad Request - Datos incorrectos
- `401`: Unauthorized - API key inválida
- `404`: Not Found - Recurso no encontrado
- `500`: Internal Server Error - Error del servidor

Ejemplo de error:

```json
{
  "error": "API key inválida"
}
```

## Seguridad

- **API Keys**: Todas las peticiones requieren una API key válida
- **Validación de archivos**: Solo se aceptan formatos de video seguros
- **Sanitización**: Los nombres de archivo se sanitizan automáticamente
- **Almacenamiento seguro**: Archivos guardados en Azure Blob Storage

## Monitoreo y Logs

La API incluye logging detallado para:

- Subidas de archivos
- Procesamiento de transcripción
- Llamadas a OpenAI
- Errores y excepciones

Los logs están disponibles en Render Dashboard.

## Soporte y Contacto

Para soporte técnico o preguntas sobre la API:

- Revisa la documentación completa en `API_DOCUMENTATION.md`
- Ejecuta los ejemplos en la carpeta `examples/`
- Contacta al equipo de desarrollo

## Roadmap

Próximas características planificadas:

- [ ] Rate limiting
- [ ] Webhooks para notificaciones
- [ ] Análisis de múltiples idiomas
- [ ] API de administración
- [ ] Dashboard de métricas
- [ ] Exportación de datos 