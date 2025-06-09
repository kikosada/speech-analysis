# Analizador de Presentaciones (Sales Pitch Analyzer)

Aplicación web y API para analizar presentaciones de ventas usando transcripción automática y análisis inteligente. Permite subir archivos de audio/video, transcribirlos, obtener retroalimentación y puntajes, y gestionar usuarios mediante Google OAuth.

## Características
- Transcripción de audio/video usando Azure Speech
- Análisis automático de conocimiento sobre la empresa
- Puntaje y retroalimentación por rubro
- Gestión de usuarios (asesor/cliente) con Google OAuth
- Almacenamiento seguro en Azure Blob Storage
- API protegida con autenticación

## Estructura del Proyecto
```
Verano/
├── src/
│   ├── app/                # Código principal de la aplicación Flask
│   ├── config/             # Configuración, requirements.txt, gunicorn, etc.
│   ├── templates/          # Plantillas HTML (Jinja2)
│   ├── static/             # Archivos estáticos (imágenes, CSS, JS)
│   ├── docs/               # Documentación y este README
```

## Variables de Entorno Necesarias
- `SECRET_KEY` (para Flask)
- `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` (para OAuth)
- `AZURE_STORAGE_ACCOUNT_NAME`, `AZURE_STORAGE_ACCOUNT_KEY`, `AZURE_CONTAINER_NAME` (para Azure)
- `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` (para transcripción)

Puedes definirlas en tu entorno o en un archivo `.env` (no lo subas a git).

## Instalación y Ejecución Local
1. Clona el repositorio y entra al directorio:
   ```bash
   git clone <tu-repo-url>
   cd Verano
   ```
2. Crea y activa un entorno virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   ```
3. Instala las dependencias:
   ```bash
   pip install -r src/config/requirements.txt
   ```
4. Exporta las variables de entorno necesarias.
5. Ejecuta la app en modo desarrollo:
   ```bash
   PYTHONPATH=. FLASK_APP=src/app/app.py FLASK_ENV=development flask run --port 10000
   ```

## Endpoints Principales
### Health Check
- **GET** `/health`
  - Responde con el estado del servicio.

### Página principal y login
- **GET** `/` — Selector de rol
- **GET** `/login-asesor` — Login para asesores
- **GET** `/login-cliente` — Login para clientes

### Subida y análisis de archivos
- **POST** `/analyze` (requiere login)
  - Sube un archivo de audio/video y devuelve el análisis.
  - Ejemplo en Postman:
    - Método: POST
    - URL: `http://localhost:10000/analyze`
    - Body: form-data, key `file`, tipo archivo

### Gestión de archivos
- **GET** `/api/mis-archivos` (requiere login)
- **GET** `/mis-archivos` (requiere login)
- **GET** `/descargar/<empresa>/<filename>` (requiere login)

### Endpoints para clientes vía API
- **POST** `/api/cliente/upload`
- **GET** `/api/cliente/analysis/<email>`

## Pruebas Automáticas
1. Instala pytest si no está en requirements:
   ```bash
   pip install pytest
   ```
2. Ejecuta las pruebas:
   ```bash
   pytest
   ```

(Próximamente: se agregarán pruebas automáticas básicas en la carpeta `tests/`)

## Despliegue
- Usa los archivos en `src/config/` para configuración en Render, Azure, etc.
- Asegúrate de definir las variables de entorno en el panel del servicio.

## Seguridad
- No subas archivos de credenciales ni `.venv` a git.
- Usa `.gitignore` para excluir archivos sensibles y temporales.

## Licencia
MIT

## Contacto y soporte
Para dudas o soporte, contacta a los responsables del proyecto. 