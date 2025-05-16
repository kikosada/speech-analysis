# speech_to_text.py
# Script para convertir audio en texto usando la API de Whisper de OpenAI

import openai
import os
import argparse

def transcribe_audio(file_path: str, model: str = "whisper-1") -> str:
    """
    Transcribe el archivo de audio especificado y devuelve el texto resultante.
    """
    # Obtén la clave de API de OpenAI desde la variable de entorno
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        raise ValueError("La variable de entorno OPENAI_API_KEY no está configurada.")

    with open(file_path, "rb") as audio_file:
        # Llama al endpoint de transcripción de audio
        response = openai.Audio.transcribe(
            model=model,
            file=audio_file
        )
    return response.get("text", "")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transcribe un archivo de audio a texto usando Whisper API"
    )
    parser.add_argument(
        "audio_file",
        help="Ruta al archivo de audio (mp3, wav, m4a, etc.)"
    )
    args = parser.parse_args()

    try:
        texto = transcribe_audio(args.audio_file)
        print("Transcripción:")
        print(texto)
    except Exception as e:
        print(f"Error al transcribir el audio: {e}")

# Uso:
# 1. Instala la librería de OpenAI: pip install openai
# 2. Exporta tu clave de API:
#    export OPENAI_API_KEY="TU_API_KEY"
# 3. Ejecuta el script:
#    python speech_to_text.py ruta/audio.mp3
