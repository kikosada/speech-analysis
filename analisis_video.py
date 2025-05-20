import cv2
from deepface import DeepFace
from collections import Counter


def analizar_emociones_video(ruta_video, frame_rate=1, archivo_salida="resumen_emociones.txt"):
    cap = cv2.VideoCapture(ruta_video)
    emociones_detectadas = []
    frame_count = 0
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30  # Valor por defecto si no se detecta FPS
    frames_to_skip = int(fps * frame_rate)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frames_to_skip == 0:
            try:
                result = DeepFace.analyze(frame, actions=['emotion'], enforce_detection=False)
                emociones_detectadas.append(result['dominant_emotion'])
                print(f"Frame {frame_count}: {result['dominant_emotion']}")
            except Exception as e:
                print(f"Error analizando frame {frame_count}: {e}")
        frame_count += 1
    cap.release()
    resumen = Counter(emociones_detectadas)
    print("\nResumen de emociones detectadas en el video:")
    with open(archivo_salida, "w", encoding="utf-8") as f:
        f.write("Resumen de emociones detectadas en el video:\n")
        for emocion, count in resumen.items():
            linea = f"{emocion}: {count} veces\n"
            print(linea.strip())
            f.write(linea)
    print(f"\nResumen guardado en {archivo_salida}")
    return resumen

# Ejemplo de uso:
if __name__ == "__main__":
    ruta_video = "/Users/kiko/Desktop/desktop2/IMG_0841.MOV"
    analizar_emociones_video(ruta_video) 