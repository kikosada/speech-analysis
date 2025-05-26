import os
import requests
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from transcriber_base import BaseTranscriber

def analyze_company_knowledge(text: str) -> Tuple[Dict[str, int], List[str]]:
    """
    Analiza el conocimiento sobre la empresa según 6 criterios clave y genera puntuaciones y retroalimentación detallada.
    Args:
        text: Texto de la entrevista
    Returns:
        Tuple[Dict[str, int], List[str]]: Puntuaciones y retroalimentación
    """
    text = text.lower()
    rules = [
        {
            'key': 'historia',
            'name': 'Historia y Orígenes',
            'patterns': ['fundó', 'creó', 'inició', 'comenzó', 'empezó', 'historia', 'origen', 'fundación', 'creación', 'inicio', 'comienzo', 'año', 'desde', 'desarrollo', 'evolución', 'crecimiento'],
            'feedback': 'Demuestra conocimiento de la historia y orígenes de la empresa.'
        },
        {
            'key': 'mision_vision',
            'name': 'Misión y Visión',
            'patterns': ['misión', 'visión', 'propósito', 'objetivo', 'meta', 'aspiración', 'busca', 'quiere', 'desea', 'pretende', 'propone', 'compromiso', 'valores', 'principios', 'filosofía'],
            'feedback': 'Muestra comprensión de la misión, visión y propósito de la empresa.'
        },
        {
            'key': 'productos',
            'name': 'Productos y Servicios',
            'patterns': ['producto', 'servicio', 'solución', 'ofrece', 'proporciona', 'brinda', 'entrega', 'desarrolla', 'crea', 'produce', 'fabrica', 'característica', 'beneficio', 'ventaja', 'diferencial'],
            'feedback': 'Conoce en detalle los productos y servicios que ofrece la empresa.'
        },
        {
            'key': 'valores',
            'name': 'Valores y Cultura',
            'patterns': ['valor', 'cultura', 'ética', 'principio', 'creencia', 'filosofía', 'trabajo en equipo', 'colaboración', 'innovación', 'excelencia', 'calidad', 'integridad', 'respeto', 'compromiso'],
            'feedback': 'Entiende los valores y la cultura organizacional de la empresa.'
        },
        {
            'key': 'mercado',
            'name': 'Mercado y Competencia',
            'patterns': ['mercado', 'industria', 'sector', 'competencia', 'competidor', 'cliente', 'usuario', 'demanda', 'oferta', 'tendencia', 'oportunidad', 'desafío', 'reto', 'posicionamiento', 'cuota de mercado'],
            'feedback': 'Demuestra conocimiento del mercado, competencia y posicionamiento.'
        },
        {
            'key': 'logros',
            'name': 'Logros y Reconocimientos',
            'patterns': ['logro', 'éxito', 'reconocimiento', 'premio', 'certificación', 'hito', 'meta alcanzada', 'objetivo cumplido', 'crecimiento', 'expansión', 'innovación', 'desarrollo', 'avance', 'progreso'],
            'feedback': 'Conoce los logros, reconocimientos y éxitos de la empresa.'
        }
    ]

    scores = {}
    feedback = []
    total_score = 0

    for rule in rules:
        count = sum(1 for pattern in rule['patterns'] if pattern in text)
        # Escalado simple: 0=0, 1=5, 2=8, 3 o más=10
        if count == 0:
            score = 0
            fb = f"{rule['name']}: No se detecta evidencia. {rule['feedback']}"
        elif count == 1:
            score = 5
            fb = f"{rule['name']}: Menciona al menos un aspecto, pero puede profundizar más. {rule['feedback']}"
        elif count == 2:
            score = 8
            fb = f"{rule['name']}: Bien cubierto, pero puede ser aún más detallado. {rule['feedback']}"
        else:
            score = 10
            fb = f"{rule['name']}: Excelente, cubre este aspecto de forma completa. {rule['feedback']}"
        scores[rule['key']] = score
        feedback.append(fb)
        total_score += score

    # Calificación global
    scores['overall'] = round(total_score / len(rules))

    return scores, feedback

def split_questions_answers(text: str, utterances=None):
    """
    Separa el texto en bloques de pregunta y respuesta usando:
    1. Utterances (si existen) para separar por turnos de hablante
    2. Palabras interrogativas al inicio de la oración
    3. Signos de pregunta
    Devuelve una lista de dicts: {'tipo': 'pregunta'/'respuesta', 'texto': ...}
    """
    import re
    bloques = []
    interrogativas = r'^(¿|qu[eéuioá]|por|cómo|cuándo|dónde|quién|cuál|cuánto)\b'
    # 1. Si hay utterances, usar turnos de hablante
    if utterances and isinstance(utterances, list) and len(utterances) > 0:
        for utt in utterances:
            oracion = utt.get('text', '').strip()
            if not oracion:
                continue
            # Detectar pregunta por '?' o palabra interrogativa
            if oracion.endswith('?') or re.match(interrogativas, oracion, re.IGNORECASE):
                bloques.append({'tipo': 'pregunta', 'texto': oracion})
            else:
                bloques.append({'tipo': 'respuesta', 'texto': oracion})
        return bloques
    # 2. Si no hay utterances, usar el texto plano
    oraciones = re.split(r'(?<=[?.!])\s+', text.strip())
    for oracion in oraciones:
        if oracion.strip() == '':
            continue
        if oracion.strip().endswith('?') or re.match(interrogativas, oracion.strip(), re.IGNORECASE):
            bloques.append({'tipo': 'pregunta', 'texto': oracion.strip()})
        else:
            if bloques and bloques[-1]['tipo'] == 'pregunta':
                bloques.append({'tipo': 'respuesta', 'texto': oracion.strip()})
            elif not bloques:
                bloques.append({'tipo': 'respuesta', 'texto': oracion.strip()})
            else:
                # Concatenar a la última respuesta
                if bloques[-1]['tipo'] == 'respuesta':
                    bloques[-1]['texto'] += ' ' + oracion.strip()
                else:
                    bloques.append({'tipo': 'respuesta', 'texto': oracion.strip()})
    return bloques

class AssemblyAITranscriber(BaseTranscriber):
    def __init__(self, api_key: Optional[str] = None, output_dir: str = "."):
        """
        Inicializa el transcriptor de AssemblyAI.
        
        Args:
            api_key: AssemblyAI API key. Si no se proporciona, intentará usar ASSEMBLYAI_API_KEY del entorno.
            output_dir: Directorio donde se guardarán las transcripciones
        """
        self.api_key = api_key or os.getenv("ASSEMBLYAI_API_KEY")
        if not self.api_key:
            raise ValueError("No se encontró API key de AssemblyAI. Proporciona una o configura ASSEMBLYAI_API_KEY")
        
        self.base_url = "https://api.assemblyai.com/v2"
        self.headers = {
            "authorization": self.api_key,
            "content-type": "application/json"
        }
        
        # Crear directorio de salida si no existe
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _validate_audio_file(self, audio_file: str) -> None:
        """
        Valida que el archivo de audio exista y tenga un formato soportado.
        
        Args:
            audio_file: Ruta al archivo de audio
        """
        supported_formats = {'.mp3', '.wav', '.m4a', '.flac', '.mp4', '.webm'}
        path = Path(audio_file)
        
        if not path.exists():
            raise FileNotFoundError(f"No se encontró el archivo: {audio_file}")
        
        if path.suffix.lower() not in supported_formats:
            raise ValueError(f"Formato no soportado. Formatos válidos: {supported_formats}")

    def upload_file(self, audio_file: str) -> str:
        """
        Sube un archivo de audio a AssemblyAI.
        
        Args:
            audio_file: Ruta al archivo de audio
        
        Returns:
            str: URL del archivo subido
        """
        self._validate_audio_file(audio_file)
        print(f"Subiendo archivo: {audio_file}")
        
        upload_endpoint = f"{self.base_url}/upload"
        file_size = Path(audio_file).stat().st_size
        uploaded_bytes = 0
        
        def read_file(filename):
            nonlocal uploaded_bytes
            with open(filename, "rb") as f:
                while True:
                    data = f.read(5242880)  # 5MB chunks
                    if not data:
                        break
                    uploaded_bytes += len(data)
                    progress = (uploaded_bytes / file_size) * 100
                    print(f"Progreso: {progress:.1f}%", end='\r')
                    yield data
        
        try:
            upload_response = requests.post(
                upload_endpoint,
                headers=self.headers,
                data=read_file(audio_file)
            )
            upload_response.raise_for_status()
            print("\nArchivo subido exitosamente!")
            return upload_response.json()["upload_url"]
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Error al subir el archivo: {str(e)}")

    def transcribe(self, audio_path: str, **kwargs) -> dict:
        """
        Transcribe el audio usando AssemblyAI y analiza el conocimiento sobre la empresa.
        Args:
            audio_path: Ruta al archivo de audio
            **kwargs: Parámetros adicionales para la transcripción
        Returns:
            dict: Resultado de la transcripción y análisis
        """
        self._validate_audio_file(audio_path)
        print("Subiendo archivo: {}".format(audio_path))
        upload_url = self.upload_file(audio_path)
        return self.transcribe_from_url(upload_url, **kwargs)

    def transcribe_from_url(self, audio_url: str, **kwargs) -> dict:
        """
        Transcribe el audio usando AssemblyAI y analiza el conocimiento sobre la empresa.
        
        Args:
            audio_url: URL del archivo de audio
            **kwargs: Parámetros adicionales para la transcripción
        
        Returns:
            dict: Resultado de la transcripción y análisis
        """
        print("Iniciando transcripción...")
        
        transcript_endpoint = f"{self.base_url}/transcript"
        
        # Configuración básica
        default_config = {
            "audio_url": audio_url,
            "language_code": "es",
            "speaker_labels": True,
            "speaker_count": 2
        }
        
        # Combinar con kwargs para permitir personalización
        json_data = {**default_config, **kwargs}
        
        try:
            response = requests.post(transcript_endpoint, json=json_data, headers=self.headers)
            response.raise_for_status()
            transcript_id = response.json()["id"]
            
            result = self._wait_for_completion(transcript_id)
            
            # Analizar el conocimiento sobre la empresa
            text = result.get('text', '')
            scores, feedback = analyze_company_knowledge(text)
            
            # Guardar el resultado completo para referencia
            result['scores'] = scores
            result['feedback'] = feedback
            self.save_transcript(result, "transcript.txt")
            
            # Separar preguntas y respuestas usando utterances si existen
            qa_blocks = split_questions_answers(text, result.get('utterances', []))
            
            # Devolver solo lo necesario para el frontend
            return {
                'text': text,
                'scores': scores,
                'feedback': feedback,
                'audio_duration': result.get('audio_duration', 0),
                'utterances': result.get('utterances', []),
                'qa_blocks': qa_blocks
            }
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Error al iniciar la transcripción: {str(e)}")

    def _wait_for_completion(self, transcript_id: str) -> Dict[str, Any]:
        """
        Espera y monitorea el progreso de la transcripción.
        
        Args:
            transcript_id: ID de la transcripción
        
        Returns:
            dict: Resultado de la transcripción
        """
        polling_endpoint = f"{self.base_url}/transcript/{transcript_id}"
        start_time = time.time()
        
        while True:
            try:
                polling_response = requests.get(polling_endpoint, headers=self.headers)
                polling_response.raise_for_status()
                status = polling_response.json()["status"]
                
                if status == "completed":
                    elapsed_time = time.time() - start_time
                    print(f"\nTranscripción completada en {elapsed_time:.1f} segundos")
                    return polling_response.json()
                elif status == "error":
                    raise RuntimeError(f"Transcripción fallida: {polling_response.json()}")
                
                print(f"Estado: {status}...", end='\r')
                time.sleep(3)
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Error al verificar estado: {str(e)}")

    def save_transcript(self, result: Dict[str, Any], audio_file: str) -> None:
        """
        Guarda los resultados de la transcripción en archivos JSON y TXT.
        
        Args:
            result: Resultado de la transcripción
            audio_file: Nombre del archivo de audio original
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = Path(audio_file).stem
        
        # Identificar al vendedor
        seller_text = ""
        if "utterances" in result:
            utterances = result["utterances"]
            speakers_text = {}
            
            # Recopilar texto por hablante
            for utterance in utterances:
                speaker = utterance['speaker']
                if speaker not in speakers_text:
                    speakers_text[speaker] = []
                speakers_text[speaker].append(utterance['text'])
            
            # Identificar al vendedor basado en patrones de venta
            seller_patterns = [
                'te presento', 'les presento', 'presentamos', 
                'beneficio', 'ventaja', 'características',
                'precio', 'cuesta', 'valor', 'oferta',
                'producto', 'servicio', 'solución',
                'comprar', 'adquirir', 'invertir'
            ]
            
            seller_scores = {speaker: 0 for speaker in speakers_text}
            for speaker, texts in speakers_text.items():
                combined_text = ' '.join(texts).lower()
                for pattern in seller_patterns:
                    if pattern in combined_text:
                        seller_scores[speaker] += 1
            
            # El hablante con más patrones de venta es probablemente el vendedor
            if seller_scores:
                seller_speaker = max(seller_scores.items(), key=lambda x: x[1])[0]
                seller_text = ' '.join(speakers_text[seller_speaker])
        else:
            # Si no hay distinción de hablantes, usar todo el texto
            seller_text = result.get('text', '')
        
        # Guardar transcripción completa en JSON
        json_path = self.output_dir / f"{base_name}_{timestamp}_full.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Guardar texto simple
        txt_path = self.output_dir / f"{base_name}_{timestamp}_text.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(result["text"])
        
        # Guardar retroalimentación del conocimiento sobre la empresa
        feedback_path = self.output_dir / f"{base_name}_{timestamp}_feedback.txt"
        with open(feedback_path, 'w', encoding='utf-8') as f:
            f.write("=== RETROALIMENTACIÓN DEL CONOCIMIENTO SOBRE LA EMPRESA ===\n\n")
            
            if "utterances" in result and len(speakers_text) > 1:
                f.write(f"Número de participantes detectados: {len(speakers_text)}\n")
                f.write(f"Analizando el conocimiento sobre la empresa del Hablante {seller_speaker} (identificado como el vendedor)\n\n")
            
            # Inicializar puntuaciones
            scores = {}
            
            # Análisis de duración
            seller_duration = result.get('audio_duration', 0)
            
            f.write("1. DURACIÓN:\n")
            if 60 <= seller_duration <= 90:
                f.write("✓ Excelente duración (entre 60-90 segundos)\n")
                scores['duracion'] = 10
            elif 45 <= seller_duration < 60 or 90 < seller_duration <= 105:
                f.write("⚠ La duración está ligeramente fuera del rango óptimo (60-90 segundos)\n")
                scores['duracion'] = 7
            else:
                f.write("⚠ La duración está muy fuera del rango óptimo (60-90 segundos)\n")
                scores['duracion'] = 4
            f.write(f"   Duración del conocimiento sobre la empresa: {seller_duration:.1f} segundos\n")
            f.write(f"   Puntuación: {scores['duracion']}/10\n\n")
            
            # Análisis de estructura usando solo el texto del vendedor
            text = seller_text.lower() if seller_text else result.get('text', '').lower()
            
            structure_score = 0
            total_checks = 0
            
            # Introducción del conocimiento sobre la empresa
            total_checks += 1
            if any(word in text for word in ['te presento', 'les presento', 'presentamos']):
                f.write("✓ Buena introducción del conocimiento sobre la empresa\n")
                structure_score += 1
            else:
                f.write("⚠ Falta una clara introducción del conocimiento sobre la empresa\n")
            
            # Beneficios y características
            total_checks += 1
            if 'beneficio' in text or 'ventaja' in text:
                f.write("✓ Menciona beneficios específicos\n")
                structure_score += 1
            else:
                f.write("⚠ Podrías enfatizar más los beneficios específicos\n")
            
            # Llamada a la acción
            total_checks += 1
            if any(word in text for word in ['compra', 'adquiere', 'visita', 'contacta']):
                f.write("✓ Incluye llamada a la acción\n")
                structure_score += 1
            else:
                f.write("⚠ Falta una clara llamada a la acción\n")
            
            # Precio
            total_checks += 1
            if any(word in text for word in ['precio', 'cuesta', 'valor', 'inversión', '$']):
                f.write("✓ Menciona información de precio\n")
                structure_score += 1
            else:
                f.write("⚠ No se menciona el precio\n")
            
            scores['estructura'] = (structure_score / total_checks) * 10
            f.write(f"Puntuación de estructura: {scores['estructura']:.1f}/10\n\n")
            
            # Claridad y Ritmo
            f.write("2. CLARIDAD Y RITMO:\n")
            words = text.split()
            words_per_minute = (len(words) / seller_duration) * 60
            f.write(f"- Velocidad del habla: {words_per_minute:.0f} palabras por minuto\n")
            
            if 120 <= words_per_minute <= 150:
                f.write("✓ Velocidad de habla óptima\n")
                scores['ritmo'] = 10
            elif 100 <= words_per_minute < 120 or 150 < words_per_minute <= 170:
                f.write("⚠ Ritmo ligeramente fuera del rango óptimo\n")
                scores['ritmo'] = 7
            else:
                f.write("⚠ Ritmo muy fuera del rango óptimo\n")
                scores['ritmo'] = 4
            f.write(f"Puntuación de ritmo: {scores['ritmo']}/10\n\n")
            
            # Calcular puntuación total
            total_score = sum(scores.values()) / len(scores)
            
            f.write("=== PUNTUACIÓN FINAL ===\n")
            f.write(f"Estructura: {scores['estructura']:.1f}/10\n")
            f.write(f"Ritmo: {scores['ritmo']}/10\n")
            f.write(f"PUNTUACIÓN TOTAL: {total_score:.1f}/10\n\n")
            
            # Recomendaciones basadas en puntuaciones
            f.write("3. RECOMENDACIONES PARA MEJORAR:\n")
            if scores['estructura'] < 8:
                f.write("- Mejora la estructura incluyendo introducción clara, beneficios y llamada a la acción\n")
                f.write("- Asegúrate de mencionar el precio o rango de precios\n")
            if scores['ritmo'] < 8:
                f.write("- Ajusta la velocidad del habla para mantenerla entre 120-150 palabras por minuto\n")
            f.write("- Incluye datos o estadísticas específicas cuando sea posible\n")
            f.write("- Considera añadir una breve historia o ejemplo de uso\n")
            
        print(f"\nRetroalimentación guardada en: {feedback_path}")
        
        # Guardar transcripción por hablante con análisis detallado
        speakers_path = self.output_dir / f"{base_name}_{timestamp}_analysis.txt"
        with open(speakers_path, 'w', encoding='utf-8') as f:
            # Información general
            f.write("=== ANÁLISIS DE LA TRANSCRIPCIÓN ===\n\n")
            f.write(f"Duración: {result.get('audio_duration', 0):.2f} segundos\n")
            f.write(f"Idioma detectado: {result.get('language_code', 'desconocido')}\n\n")
            
            # Análisis de sentimiento
            f.write("=== ANÁLISIS DE SENTIMIENTO ===\n")
            sentiment_results = result.get('sentiment_analysis_results', [])
            if sentiment_results:
                for segment in sentiment_results:
                    f.write(f"\nTexto: {segment.get('text', '')}\n")
                    f.write(f"Sentimiento: {segment.get('sentiment', 'neutral')}\n")
                    confidence = segment.get('confidence', 'unavailable')
                    if confidence != 'unavailable':
                        try:
                            confidence = float(confidence)
                            f.write(f"Confianza: {confidence:.2%}\n")
                        except (ValueError, TypeError):
                            f.write("Confianza: No disponible\n")
                    else:
                        f.write("Confianza: No disponible\n")
            else:
                f.write("No se detectó análisis de sentimiento\n")
            
            # Categorías IAB si están disponibles
            if 'iab_categories_result' in result:
                f.write("\n=== CATEGORÍAS DE CONTENIDO ===\n")
                for category, score in result.get('iab_categories_result', {}).items():
                    try:
                        score = float(score)
                        if score > 0.5:  # Solo mostrar categorías relevantes
                            f.write(f"{category}: {score:.2%}\n")
                    except (ValueError, TypeError):
                        continue
            
            # Transcripción por hablante
            f.write("\n=== TRANSCRIPCIÓN POR HABLANTE ===\n")
            if "utterances" in result:
                for utterance in result["utterances"]:
                    f.write(f"\nHablante {utterance['speaker']}: {utterance['text']}\n")
                    
        print(f"\nAnálisis completo guardado en: {speakers_path}")

def main():
    try:
        # Usar la API key del entorno
        transcriber = AssemblyAITranscriber()
        
        # Solicitar archivo de audio al usuario
        audio_file = input("Ingresa la ruta al archivo de audio: ").strip()
        
        # Subir archivo
        audio_url = transcriber.upload_file(audio_file)
        
        # Realizar transcripción
        result = transcriber.transcribe(audio_file)
        
        # Guardar resultados
        transcriber.save_transcript(result, audio_file)
        
        # Mostrar resumen
        print("\nResumen de la transcripción:")
        print("-" * 50)
        print(f"Duración total: {result.get('audio_duration', 0):.2f} segundos")
        print(f"Número de hablantes: {len(result.get('utterances', []))}")
        print(f"Idioma detectado: {result.get('language_code', 'desconocido')}")
        
        # Mostrar análisis de sentimiento
        if "sentiment_analysis_results" in result:
            print("\nAnálisis de sentimiento:")
            sentiment_results = result["sentiment_analysis_results"]
            if sentiment_results:
                for segment in sentiment_results:
                    print(f"\nTexto: {segment['text']}")
                    print(f"Sentimiento: {segment['sentiment']}")
                    confidence = segment.get('confidence', 'unavailable')
                    if confidence != 'unavailable':
                        try:
                            confidence = float(confidence)
                            print(f"Confianza: {confidence:.2%}")
                        except (ValueError, TypeError):
                            print("Confianza: No disponible")
                    else:
                        print("Confianza: No disponible")
            else:
                print("No se detectó sentimiento en el audio")
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 