import os
import tempfile
import subprocess
from PIL import Image
import openai
from config import Config

def extract_frames(video_path, fps=1):
    """
    Extrae 1 frame por segundo del video y devuelve la lista de rutas de los frames extraídos.
    """
    output_dir = tempfile.mkdtemp()
    output_pattern = os.path.join(output_dir, 'frame_%04d.jpg')
    cmd = [
        'ffmpeg', '-i', video_path, '-vf', f'fps={fps}', output_pattern, '-hide_banner', '-loglevel', 'error'
    ]
    subprocess.run(cmd, check=True)
    frames = sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.jpg')])
    return frames

def analyze_frame_with_openai(image_path, api_key):
    """
    Analiza una imagen usando OpenAI Vision y devuelve una lista de elementos detectados.
    """
    client = openai.OpenAI(api_key=api_key)
    prompt = (
        "Analiza la siguiente imagen y responde con una lista breve y ordenada de lo que ves. "
        "Incluye objetos, personas, ambiente (por ejemplo: ordenado, desordenado), y cualquier texto visible. "
        "Responde solo con la lista, sin explicaciones."
    )
    with open(image_path, "rb") as img_file:
        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_file.read().hex()}"}}
                ]}
            ],
            max_tokens=256
        )
        content = response.choices[0].message.content
        # Intentar extraer la lista del contenido
        items = [line.strip('- ').strip() for line in content.split('\n') if line.strip() and not line.lower().startswith('lista')]
        return items

def summarize_vision_results(results_list):
    """
    Unifica y ordena los resultados de todos los frames, eliminando repeticiones.
    """
    summary_set = set()
    for items in results_list:
        for item in items:
            summary_set.add(item)
    return sorted(summary_set)

def analyze_workspace_video(video_path):
    """
    Flujo completo: extrae frames, analiza cada uno y devuelve un resumen unificado.
    """
    api_key = Config.OPENAI_API_KEY
    frames = extract_frames(video_path, fps=1)
    all_results = []
    for frame in frames:
        try:
            items = analyze_frame_with_openai(frame, api_key)
            all_results.append(items)
        except Exception as e:
            print(f"Error analizando frame {frame}: {e}")
    vision_summary = summarize_vision_results(all_results)
    return vision_summary 