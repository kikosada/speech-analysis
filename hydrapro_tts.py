import os
from pathlib import Path
from openai import OpenAI
import logging
from typing import Optional
import shutil
from datetime import datetime, timedelta

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FileManager:
    """Clase para gestionar los archivos generados."""
    
    def __init__(self, base_dir: Path):
        """
        Inicializa el gestor de archivos.
        
        Args:
            base_dir: Directorio base donde se crearán los subdirectorios
        """
        self.base_dir = base_dir
        self.audio_dir = base_dir / "audio"
        self.archive_dir = base_dir / "archive"
        
        # Crear directorios si no existen
        self.audio_dir.mkdir(exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)
    
    def archive_old_files(self, days_old: int = 7):
        """
        Mueve archivos antiguos al directorio de archivo.
        
        Args:
            days_old: Número de días para considerar un archivo como antiguo
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        for file_path in self.base_dir.glob("*.txt"):
            if file_path.stat().st_mtime < cutoff_date.timestamp():
                archive_path = self.archive_dir / file_path.name
                shutil.move(str(file_path), str(archive_path))
                logger.info(f"Archivo movido al archivo: {file_path.name}")
    
    def clean_archive(self, max_files: int = 50):
        """
        Limpia el directorio de archivo manteniendo solo los archivos más recientes.
        
        Args:
            max_files: Número máximo de archivos a mantener
        """
        files = list(self.archive_dir.glob("*.txt"))
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        for file_path in files[max_files:]:
            file_path.unlink()
            logger.info(f"Archivo eliminado del archivo: {file_path.name}")

class HydraProTTS:
    """Clase para manejar la generación de audio para el pitch de HydraPro."""
    
    # Voces recomendadas para español, ordenadas por naturalidad para el idioma
    SPANISH_VOICES = {
        "alloy": "Voz neutral y profesional, buena para español",
        "nova": "Voz femenina con buen manejo de entonación española",
        "shimmer": "Voz femenina juvenil, energética",
        "echo": "Voz más profunda, buena para textos formales",
        "fable": "Voz más suave y cálida",
        "onyx": "Voz profunda y autoritativa"
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el cliente de OpenAI y configura los parámetros básicos.
        
        Args:
            api_key: OpenAI API key. Si no se proporciona, intentará usar OPENAI_API_KEY del entorno.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("No se encontró API key de OpenAI. Proporciona una o configura OPENAI_API_KEY")
        
        self.base_dir = Path(__file__).parent / "output"
        self.file_manager = FileManager(self.base_dir)
    
    @classmethod
    def list_spanish_voices(cls):
        """Muestra las voces disponibles y sus descripciones para español."""
        print("\nVoces disponibles para español:")
        print("-" * 50)
        for voice, description in cls.SPANISH_VOICES.items():
            print(f"- {voice}: {description}")
        
    def generate_audio(
        self,
        text: str,
        output_filename: str = "hydrapro_pitch.mp3",
        model: str = "tts-1",
        voice: str = "nova",  # Cambiado a nova por defecto para español
        instructions: Optional[str] = None
    ) -> Path:
        """
        Genera el audio en español a partir del texto proporcionado.
        
        Args:
            text: Texto en español a convertir en audio
            output_filename: Nombre del archivo de salida
            model: Modelo TTS a usar
            voice: Voz a utilizar (recomendado: nova, alloy para español)
            instructions: Instrucciones específicas para el tono y estilo
            
        Returns:
            Path: Ruta al archivo de audio generado
        """
        try:
            if voice not in self.SPANISH_VOICES:
                logger.warning(f"La voz '{voice}' no está en la lista de voces recomendadas para español")
                logger.info("Puedes ver las voces recomendadas usando HydraProTTS.list_spanish_voices()")
            
            output_path = self.file_manager.audio_dir / output_filename
            
            # Validar longitud del texto
            if len(text) > 4096:
                raise ValueError(f"El texto excede el límite de 4096 caracteres: {len(text)}")
            
            logger.info(f"Generando audio en español con voz '{voice}' usando modelo '{model}'")
            
            # Preparar parámetros de la solicitud
            params = {
                "model": model,
                "voice": voice,
                "input": text
            }
            
            # Añadir instrucciones específicas para español si no se proporcionan otras
            if not instructions:
                instructions = "Habla en español con un tono natural y claro, manteniendo la entonación española correcta"
            params["instructions"] = instructions
            
            # Generar y guardar el audio
            client = OpenAI(api_key=self.api_key)
            with client.audio.speech.with_streaming_response.create(**params) as response:
                response.stream_to_file(output_path)
            
            # Archivar archivos antiguos
            self.file_manager.archive_old_files()
            self.file_manager.clean_archive()
            
            logger.info(f"Audio en español generado exitosamente: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error al generar el audio: {str(e)}")
            raise

def main():
    # Mostrar las voces disponibles
    HydraProTTS.list_spanish_voices()
    
    # Texto de venta de HydraPro
    product_pitch = (
        "¡Hola! Te presento HydraPro, la botella inteligente ecológica que cambiará para siempre tu forma de mantenerte hidratado. "
        "Con su acabado en acero inoxidable libre de BPA y un diseño ultraligero, HydraPro combina elegancia y funcionalidad. "
        "Se conecta vía Bluetooth a tu smartphone mediante nuestra app gratuita, donde podrás programar recordatorios personalizados, "
        "consultar tu historial de consumo y comparar tus estadísticas con amigos para motivarte cada día. "
        "Su aislamiento de doble pared mantiene tu bebida fría hasta 24 horas o caliente hasta 12 horas, "
        "mientras que la pantalla LED minimalista te muestra la temperatura en tiempo real y tu progreso diario. "
        "Además, cuenta con un panel solar integrado que recarga la batería con luz natural, "
        "ofreciendo hasta una semana de autonomía sin necesidad de cables. "
        "HydraPro es 100% reciclable y viene en cuatro colores intercambiables para adaptarse a tu estilo. "
        "Incluye garantía extendida de 2 años y acceso a desafíos de hidratación en la comunidad, "
        "así que cada sorbo se convierte en un momento de bienestar y conexión. "
        "Haz de tu salud una prioridad con HydraPro. ¡Tu cuerpo y el planeta te lo agradecerán!"
    )

    try:
        # Crear instancia del generador de TTS
        tts = HydraProTTS()
        
        # Generar el audio con instrucciones específicas para español
        output_file = tts.generate_audio(
            text=product_pitch,
            output_filename="hydrapro_pitch_extended.mp3",
            voice="nova",  # Usando nova que es muy buena para español
            instructions="Habla en español con un tono muy alegre, entusiasta y cercano, como si convencieras a un amigo de un gran descubrimiento, manteniendo una entonación natural en español."
        )
        
        logger.info(f"Proceso completado. Audio guardado en: {output_file}")
        
    except Exception as e:
        logger.error(f"Error en el proceso: {str(e)}")
        raise

if __name__ == "__main__":
    main() 