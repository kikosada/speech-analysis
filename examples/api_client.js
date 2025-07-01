/**
 * Cliente de ejemplo para la API de Análisis de Presentaciones Empresariales
 * Versión JavaScript para uso en navegador o Node.js
 */

class PresentationAnalysisAPI {
    /**
     * Constructor del cliente API
     * @param {string} baseUrl - URL base de la API
     * @param {string} apiKey - API key para autenticación
     */
    constructor(baseUrl, apiKey) {
        this.baseUrl = baseUrl.replace(/\/$/, ''); // Remover trailing slash
        this.apiKey = apiKey;
        this.headers = {
            'X-API-Key': apiKey,
            'Content-Type': 'application/json'
        };
    }

    /**
     * Verificar estado de la API
     * @returns {Promise<Object>} Estado de la API
     */
    async healthCheck() {
        const response = await fetch(`${this.baseUrl}/health`);
        return await response.json();
    }

    /**
     * Subir y analizar una presentación
     * @param {File} file - Archivo de video
     * @param {string} rfc - RFC de la empresa
     * @param {string} companyName - Nombre de la empresa (opcional)
     * @param {string} presenterName - Nombre del presentador (opcional)
     * @returns {Promise<Object>} Resultado del análisis
     */
    async uploadPresentation(file, rfc, companyName = '', presenterName = '') {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('rfc', rfc);
        formData.append('company_name', companyName);
        formData.append('presenter_name', presenterName);

        const response = await fetch(`${this.baseUrl}/presentations/upload`, {
            method: 'POST',
            headers: {
                'X-API-Key': this.apiKey
            },
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Error en la API: ${response.status} - ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Obtener análisis de una presentación
     * @param {string} rfc - RFC de la empresa
     * @returns {Promise<Object>} Datos de la presentación
     */
    async getPresentation(rfc) {
        const response = await fetch(`${this.baseUrl}/presentations/${rfc}`, {
            headers: this.headers
        });

        if (response.status === 404) {
            throw new Error(`Presentación no encontrada para RFC: ${rfc}`);
        }

        if (!response.ok) {
            throw new Error(`Error en la API: ${response.status} - ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Verificar estado de procesamiento
     * @param {string} rfc - RFC de la empresa
     * @returns {Promise<Object>} Estado de la presentación
     */
    async getPresentationStatus(rfc) {
        const response = await fetch(`${this.baseUrl}/presentations/${rfc}/status`, {
            headers: this.headers
        });
        return await response.json();
    }

    /**
     * Listar presentaciones
     * @param {number} limit - Número máximo de resultados
     * @param {number} offset - Offset para paginación
     * @returns {Promise<Object>} Lista de presentaciones
     */
    async listPresentations(limit = 50, offset = 0) {
        const params = new URLSearchParams({
            limit: limit.toString(),
            offset: offset.toString()
        });

        const response = await fetch(`${this.baseUrl}/presentations?${params}`, {
            headers: this.headers
        });

        if (!response.ok) {
            throw new Error(`Error en la API: ${response.status} - ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Analizar solo un transcript
     * @param {string} transcript - Texto a analizar
     * @returns {Promise<Object>} Análisis del transcript
     */
    async analyzeTranscript(transcript) {
        const response = await fetch(`${this.baseUrl}/analysis/transcript`, {
            method: 'POST',
            headers: this.headers,
            body: JSON.stringify({ transcript })
        });

        if (!response.ok) {
            throw new Error(`Error en la API: ${response.status} - ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Obtener métricas de la API
     * @returns {Promise<Object>} Métricas de la API
     */
    async getMetrics() {
        const response = await fetch(`${this.baseUrl}/metrics`, {
            headers: this.headers
        });

        if (!response.ok) {
            throw new Error(`Error en la API: ${response.status} - ${response.statusText}`);
        }

        return await response.json();
    }
}

// Ejemplo de uso en navegador
async function exampleUsage() {
    // Configuración
    const BASE_URL = 'https://tu-dominio.onrender.com/api/v1'; // Cambiar por tu URL
    const API_KEY = 'tu-api-key-aqui'; // Cambiar por tu API key

    // Crear cliente
    const api = new PresentationAnalysisAPI(BASE_URL, API_KEY);

    try {
        // 1. Verificar estado de la API
        console.log('=== Verificando estado de la API ===');
        const health = await api.healthCheck();
        console.log('Estado:', health.status);
        console.log('Versión:', health.version);
        console.log();

        // 2. Analizar un transcript de ejemplo
        console.log('=== Analizando transcript ===');
        const transcript = `
            Buenos días, hoy les voy a presentar nuestra empresa Tecnología Avanzada S.A.
            Somos una empresa fundada en 2010 que se dedica al desarrollo de software empresarial.
            Nuestra misión es facilitar la transformación digital de las empresas mexicanas.
            Ofrecemos soluciones en gestión de recursos empresariales, CRM y automatización.
            Nuestros valores principales son la innovación, la calidad y el servicio al cliente.
            Hemos logrado implementar más de 500 proyectos exitosos en todo el país.
        `;

        const analysis = await api.analyzeTranscript(transcript);
        console.log('Análisis del transcript:');
        console.log('Puntuación general:', analysis.analysis.scores.overall);
        console.log('Resumen:', analysis.analysis.resumen);
        console.log('Feedback:');
        analysis.analysis.feedback.forEach(feedback => {
            console.log('  -', feedback);
        });
        console.log();

        // 3. Obtener métricas
        console.log('=== Métricas de la API ===');
        const metrics = await api.getMetrics();
        console.log('Total de presentaciones:', metrics.total_presentations);
        console.log('Tamaño total de almacenamiento:', metrics.total_storage_size_mb, 'MB');
        console.log();

        // 4. Listar presentaciones
        console.log('=== Listando presentaciones ===');
        const presentations = await api.listPresentations(5);
        console.log('Total de presentaciones encontradas:', presentations.total);
        presentations.presentations.forEach(presentation => {
            console.log('  - RFC:', presentation.rfc);
            console.log('    Empresa:', presentation.company_name || 'N/A');
            console.log('    Fecha:', presentation.upload_timestamp || 'N/A');
            console.log();
        });

    } catch (error) {
        console.error('Error:', error.message);
    }
}

// Ejemplo de uso con subida de archivo (para navegador)
async function uploadFileExample() {
    const BASE_URL = 'https://tu-dominio.onrender.com/api/v1';
    const API_KEY = 'tu-api-key-aqui';
    const api = new PresentationAnalysisAPI(BASE_URL, API_KEY);

    // Obtener archivo del input file
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Por favor selecciona un archivo');
        return;
    }

    try {
        console.log('Subiendo archivo:', file.name);
        
        const result = await api.uploadPresentation(
            file,
            'ABC123456789',
            'Mi Empresa S.A.',
            'Juan Pérez'
        );

        console.log('Análisis completado:', result.message);
        console.log('Puntuación general:', result.analysis.scores.overall);
        console.log('Transcript:', result.transcript);

        // Mostrar resultados en la UI
        displayResults(result);

    } catch (error) {
        console.error('Error al subir archivo:', error.message);
        alert('Error al subir archivo: ' + error.message);
    }
}

// Función para mostrar resultados en la UI
function displayResults(result) {
    const resultsDiv = document.getElementById('results');
    
    resultsDiv.innerHTML = `
        <h3>Resultados del Análisis</h3>
        <p><strong>Mensaje:</strong> ${result.message}</p>
        <p><strong>Puntuación General:</strong> ${result.analysis.scores.overall}/10</p>
        <h4>Puntuaciones Detalladas:</h4>
        <ul>
            <li>Historia: ${result.analysis.scores.historia}/10</li>
            <li>Misión y Visión: ${result.analysis.scores.mision_vision}/10</li>
            <li>Productos: ${result.analysis.scores.productos}/10</li>
            <li>Valores: ${result.analysis.scores.valores}/10</li>
            <li>Mercado: ${result.analysis.scores.mercado}/10</li>
            <li>Logros: ${result.analysis.scores.logros}/10</li>
        </ul>
        <h4>Feedback:</h4>
        <ul>
            ${result.analysis.feedback.map(feedback => `<li>${feedback}</li>`).join('')}
        </ul>
        <h4>Resumen:</h4>
        <p>${result.analysis.resumen}</p>
        <h4>Transcript:</h4>
        <p>${result.transcript}</p>
    `;
}

// Exportar para uso en módulos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PresentationAnalysisAPI;
}

// Ejecutar ejemplo si estamos en navegador
if (typeof window !== 'undefined') {
    // Crear elementos de ejemplo en la página
    document.addEventListener('DOMContentLoaded', function() {
        const container = document.createElement('div');
        container.innerHTML = `
            <h2>API de Análisis de Presentaciones</h2>
            <div>
                <input type="file" id="fileInput" accept="video/*">
                <button onclick="uploadFileExample()">Subir y Analizar</button>
            </div>
            <div id="results"></div>
        `;
        document.body.appendChild(container);
    });
} 