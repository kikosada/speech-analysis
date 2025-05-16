# speech_to_text.py
# Script para transcribir y analizar habilidades de persuasión

import assemblyai as aai
import os
import argparse
import time
from collections import defaultdict
from datetime import datetime

def transcribe_audio(file_path: str) -> dict:
    """
    Transcribe el audio identificando los diferentes hablantes.
    """
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("La variable de entorno ASSEMBLYAI_API_KEY no está configurada.")

    aai.settings.api_key = api_key
    transcriber = aai.Transcriber()

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        speech_threshold=0.2
    )

    print("Transcribiendo el audio...")
    transcript = transcriber.transcribe(file_path, config=config)

    while transcript.status != 'completed':
        time.sleep(1)
        transcript = transcriber.get_transcript(transcript.id)

    return transcript

def analizar_habilidades_persuasion(intervenciones: list) -> dict:
    """
    Analiza las habilidades de persuasión según la rúbrica establecida.
    """
    rubrica = {
        "estructura_argumentos": {
            "descripcion": "Organización y claridad de los argumentos",
            "puntuacion": 0,
            "comentarios": [],
            "sugerencias": []
        },
        "evidencia_datos": {
            "descripcion": "Uso de evidencia y datos para respaldar argumentos",
            "puntuacion": 0,
            "comentarios": [],
            "sugerencias": []
        },
        "tono_voz": {
            "descripcion": "Tono y manejo del lenguaje",
            "puntuacion": 0,
            "comentarios": [],
            "sugerencias": []
        },
        "respuesta_objeciones": {
            "descripcion": "Capacidad de responder a objeciones",
            "puntuacion": 0,
            "comentarios": [],
            "sugerencias": []
        },
        "persuasion": {
            "descripcion": "Efectividad general de la persuasión",
            "puntuacion": 0,
            "comentarios": [],
            "sugerencias": []
        }
    }

    texto_completo = " ".join([i["texto"].lower() for i in intervenciones])
    
    # Evaluar estructura de argumentos
    conectores_argumentativos = {
        "principales": [
            # Español
            "por lo tanto", "en consecuencia", "por consiguiente", "así que",
            "en primer lugar", "en segundo lugar", "finalmente", "para concluir",
            "por un lado", "por otro lado", "además", "asimismo",
            "de acuerdo con", "según", "como indica", "como demuestra",
            # Respaldo en inglés
            "therefore", "consequently", "furthermore", "moreover",
            "according to", "as shown by"
        ],
        "secundarios": [
            # Español
            "porque", "ya que", "debido a", "puesto que", "dado que",
            "también", "incluso", "de hecho", "en realidad", "ciertamente",
            "por ejemplo", "como", "tal como", "así como",
            # Respaldo en inglés
            "because", "since", "also", "in fact", "for example"
        ]
    }
    
    estructura_score = 0
    for conector in conectores_argumentativos["principales"]:
        if conector in texto_completo:
            estructura_score += 2
            rubrica["estructura_argumentos"]["comentarios"].append(f"Buen uso del conector '{conector}'")
    
    for conector in conectores_argumentativos["secundarios"]:
        if conector in texto_completo:
            estructura_score += 1
            rubrica["estructura_argumentos"]["comentarios"].append(f"Uso efectivo de '{conector}'")
            
    rubrica["estructura_argumentos"]["puntuacion"] = min(10, estructura_score)
    
    if estructura_score < 5:
        rubrica["estructura_argumentos"]["sugerencias"].extend([
            "Usar más conectores lógicos para estructurar argumentos",
            "Organizar ideas en secuencia: introducción, desarrollo y conclusión",
            "Utilizar transiciones claras entre ideas"
        ])
    
    # Evaluar uso de evidencia
    evidencia_patterns = {
        "datos_numericos": r'\d+(?:\.\d+)?(?:\s*%)?',
        "citas": r'según|de acuerdo|como (dice|indica|señala|menciona|afirma)|' + 
                r'according to|states?|reports?',
        "ejemplos": r'por ejemplo|como|tal como|ilustra|demuestra|' +
                   r'for example|such as|like',
        "estudios": r'estudio|investigación|análisis|encuesta|estadística|informe|' +
                   r'study|research|analysis|survey|statistics'
    }
    
    evidencia_score = 0
    for tipo, patron in evidencia_patterns.items():
        import re
        matches = re.finditer(patron, texto_completo)
        for match in matches:
            evidencia_score += 2.5
            start = max(0, match.start() - 30)
            end = min(len(texto_completo), match.end() + 30)
            contexto = texto_completo[start:end].strip()
            rubrica["evidencia_datos"]["comentarios"].append(f"Buen uso de {tipo}: '{contexto}'")
    
    rubrica["evidencia_datos"]["puntuacion"] = min(10, evidencia_score)
    
    if evidencia_score < 5:
        rubrica["evidencia_datos"]["sugerencias"].extend([
            "Incluir más datos específicos y estadísticas",
            "Citar fuentes confiables",
            "Proporcionar ejemplos concretos",
            "Referenciar estudios o investigaciones relevantes"
        ])

    # Evaluar tono y lenguaje persuasivo
    palabras_persuasivas = {
        "engagement": [
            # Español
            "podemos ver", "imagina", "considera", "piensa en", "fíjate",
            "observa", "reflexiona", "analiza", "veamos", "pensemos",
            # Respaldo en inglés
            "consider", "imagine", "let's", "we can see"
        ],
        "emocional": [
            # Español
            "importante", "crucial", "fundamental", "necesario", "vital",
            "grave", "urgente", "significativo", "esencial", "clave",
            "preocupante", "alarmante", "crítico",
            # Respaldo en inglés
            "important", "crucial", "vital", "necessary"
        ],
        "credibilidad": [
            # Español
            "experto", "comprobado", "demostrado", "verificado", "confiable",
            "evidencia", "prueba", "confirmado", "validado", "respaldado",
            # Respaldo en inglés
            "expert", "proven", "evidence", "verified"
        ],
        "urgencia": [
            # Español
            "ahora", "inmediatamente", "pronto", "urgente", "sin demora",
            "cuanto antes", "no podemos esperar", "es momento de",
            # Respaldo en inglés
            "now", "immediately", "urgent", "cannot wait"
        ],
        "moral": [
            # Español
            "debemos", "tenemos que", "hay que", "es necesario",
            "es correcto", "es incorrecto", "es justo", "es injusto",
            "moral", "ético", "responsabilidad", "deber",
            # Respaldo en inglés
            "should", "must", "right", "wrong", "moral", "ethical"
        ]
    }
    
    tono_score = 0
    for categoria, palabras in palabras_persuasivas.items():
        for palabra in palabras:
            if palabra in texto_completo:
                tono_score += 1.5
                rubrica["tono_voz"]["comentarios"].append(f"Buen uso de lenguaje de {categoria}: '{palabra}'")
    
    rubrica["tono_voz"]["puntuacion"] = min(10, tono_score)
    
    if tono_score < 5:
        rubrica["tono_voz"]["sugerencias"].extend([
            "Usar más palabras que inviten a la reflexión",
            "Incorporar lenguaje emocional apropiado",
            "Utilizar palabras que construyan credibilidad",
            "Emplear términos que transmitan urgencia cuando sea apropiado"
        ])

    # Evaluar respuesta a objeciones y contraargumentos
    patrones_respuesta = {
        "reconocimiento": [
            # Español
            "entiendo", "comprendo", "reconozco", "es cierto que",
            "tienes razón", "es verdad que", "admito que",
            # Respaldo en inglés
            "understand", "recognize", "true that"
        ],
        "contraste": [
            # Español
            "sin embargo", "pero", "aunque", "no obstante",
            "por otro lado", "en cambio", "a pesar de",
            # Respaldo en inglés
            "however", "but", "although", "nevertheless"
        ],
        "concesión": [
            # Español
            "si bien", "aun cuando", "ciertamente",
            "puede ser que", "es posible que",
            # Respaldo en inglés
            "while", "granted", "certainly"
        ],
        "refutación": [
            # Español
            "en realidad", "de hecho", "la verdad es",
            "contrariamente", "por el contrario",
            # Respaldo en inglés
            "actually", "in fact", "contrary to"
        ]
    }
    
    respuesta_score = 0
    for tipo, patrones in patrones_respuesta.items():
        for patron in patrones:
            if patron in texto_completo:
                respuesta_score += 2
                rubrica["respuesta_objeciones"]["comentarios"].append(f"Buen manejo de {tipo}: '{patron}'")
    
    rubrica["respuesta_objeciones"]["puntuacion"] = min(10, respuesta_score)
    
    if respuesta_score < 5:
        rubrica["respuesta_objeciones"]["sugerencias"].extend([
            "Anticipar y abordar más contraargumentos",
            "Reconocer puntos válidos de la oposición",
            "Usar transiciones efectivas al presentar contraargumentos",
            "Proporcionar evidencia al refutar objeciones"
        ])

    # Calcular puntuación general de persuasión con pesos
    pesos = {
        "estructura_argumentos": 0.25,
        "evidencia_datos": 0.3,
        "tono_voz": 0.2,
        "respuesta_objeciones": 0.25
    }
    
    puntuacion_total = sum(
        rubrica[criterio]["puntuacion"] * peso 
        for criterio, peso in pesos.items()
    )
    
    rubrica["persuasion"]["puntuacion"] = round(puntuacion_total, 1)
    
    # Añadir comentarios generales basados en la puntuación total
    if puntuacion_total >= 8:
        rubrica["persuasion"]["comentarios"].append("Excelente capacidad de persuasión")
    elif puntuacion_total >= 6:
        rubrica["persuasion"]["comentarios"].append("Buena capacidad de persuasión con áreas de mejora")
    else:
        rubrica["persuasion"]["comentarios"].append("Necesita mejorar significativamente las habilidades de persuasión")

    return rubrica

def generar_reporte_persuasion(analisis: dict) -> str:
    """
    Genera un reporte detallado de las habilidades de persuasión.
    """
    reporte = []
    
    # Encabezado con formato
    reporte.append("="*70)
    reporte.append(" "*20 + "ANÁLISIS DE HABILIDADES DE PERSUASIÓN")
    reporte.append("="*70 + "\n")

    # Puntuación general con evaluación cualitativa
    puntuacion = analisis['persuasion']['puntuacion']
    reporte.append(f"PUNTUACIÓN GENERAL: {puntuacion}/10")
    
    # Añadir evaluación cualitativa
    if puntuacion >= 8:
        nivel = "EXCELENTE"
    elif puntuacion >= 6:
        nivel = "BUENO"
    else:
        nivel = "NECESITA MEJORA"
    reporte.append(f"Nivel de Desempeño: {nivel}\n")
    
    # Comentarios generales
    if analisis['persuasion']['comentarios']:
        reporte.append("EVALUACIÓN GENERAL:")
        for comentario in analisis['persuasion']['comentarios']:
            reporte.append(f"• {comentario}")
        reporte.append("")
    
    # Desglose detallado por criterio
    reporte.append("ANÁLISIS DETALLADO POR CRITERIO:")
    reporte.append("-"*70)
    
    for criterio, datos in analisis.items():
        if criterio != "persuasion":  # No repetir la puntuación general
            reporte.append(f"\n{datos['descripcion'].upper()}:")
            reporte.append(f"Puntuación: {datos['puntuacion']}/10")
            
            # Mostrar nivel de desempeño en este criterio
            if datos['puntuacion'] >= 8:
                reporte.append("Nivel: Excelente")
            elif datos['puntuacion'] >= 6:
                reporte.append("Nivel: Bueno")
            else:
                reporte.append("Nivel: Necesita mejora")
            
            # Mostrar comentarios positivos
            if datos['comentarios']:
                reporte.append("\nPuntos fuertes:")
                for comentario in datos['comentarios']:
                    reporte.append(f"✓ {comentario}")
            
            # Mostrar sugerencias de mejora
            if datos['sugerencias']:
                reporte.append("\nOportunidades de mejora:")
                for sugerencia in datos['sugerencias']:
                    reporte.append(f"→ {sugerencia}")
            reporte.append("-"*50)

    # Recomendaciones finales
    reporte.append("\nRECOMENDACIONES FINALES:")
    reporte.append("-"*70)
    
    # Identificar áreas más débiles y más fuertes
    puntuaciones = {k: v['puntuacion'] for k, v in analisis.items() if k != 'persuasion'}
    area_mas_fuerte = max(puntuaciones.items(), key=lambda x: x[1])[0]
    area_mas_debil = min(puntuaciones.items(), key=lambda x: x[1])[0]
    
    reporte.append(f"• Punto más fuerte: {analisis[area_mas_fuerte]['descripcion']}")
    reporte.append(f"• Área prioritaria de mejora: {analisis[area_mas_debil]['descripcion']}")
    
    # Sugerencias generales basadas en la puntuación
    if puntuacion < 7:
        reporte.append("\nPasos siguientes recomendados:")
        if puntuacion < 5:
            reporte.append("1. Revisar y aplicar las técnicas básicas de argumentación")
            reporte.append("2. Practicar la estructuración clara de ideas")
            reporte.append("3. Incorporar más evidencias y datos en los argumentos")
            reporte.append("4. Trabajar en el uso de lenguaje persuasivo")
        else:
            reporte.append("1. Enfocarse en mejorar el área más débil identificada")
            reporte.append("2. Incorporar técnicas más avanzadas de persuasión")
            reporte.append("3. Practicar la anticipación y respuesta a contraargumentos")
    
    # Pie del reporte
    reporte.append("\n" + "="*70)
    reporte.append("Fin del análisis | Generado automáticamente")
    reporte.append("="*70)

    return "\n".join(reporte)

def analizar_patrones_persuasivos(texto: str) -> dict:
    """
    Analiza patrones específicos de persuasión en el texto.
    """
    patrones = {
        "logos": {
            "patrones": [
                r"por lo tanto",
                r"en consecuencia",
                r"dado que",
                r"debido a",
                r"como resultado",
                r"\d+(?:\.\d+)?(?:\s*%)?",  # números y porcentajes
                r"según (?:el|la|los|las|un|una)",
                r"de acuerdo (?:al|a la|a los|a las)"
            ],
            "descripcion": "Apelación a la lógica y razón",
            "encontrados": []
        },
        "pathos": {
            "patrones": [
                r"imagina",
                r"piensa en",
                r"siente",
                r"importante",
                r"crucial",
                r"necesario",
                r"preocupa(?:nte)?",
                r"(?:no )?podemos permitir",
                r"debemos?"
            ],
            "descripcion": "Apelación a las emociones",
            "encontrados": []
        },
        "ethos": {
            "patrones": [
                r"(?:como )?experto",
                r"(?:según )?estudios",
                r"investigación(?:es)?",
                r"evidencia",
                r"comprobado",
                r"demostrado",
                r"experiencia",
                r"profesional"
            ],
            "descripcion": "Apelación a la autoridad o credibilidad",
            "encontrados": []
        },
        "kairos": {
            "patrones": [
                r"ahora",
                r"momento",
                r"oportunidad",
                r"(?:no )?podemos esperar",
                r"inmediata(?:mente)?",
                r"urgente",
                r"pronto",
                r"tiempo"
            ],
            "descripcion": "Apelación a la oportunidad o urgencia",
            "encontrados": []
        },
        "reciprocidad": {
            "patrones": [
                r"si (?:tú|usted)",
                r"a cambio",
                r"beneficio mutuo",
                r"ganar-ganar",
                r"colabor(?:ar|ación)",
                r"juntos"
            ],
            "descripcion": "Principio de reciprocidad",
            "encontrados": []
        }
    }
    
    import re
    resultados = {}
    
    for tipo, info in patrones.items():
        encontrados = []
        for patron in info["patrones"]:
            matches = re.finditer(patron, texto.lower())
            for match in matches:
                # Obtener contexto (5 palabras antes y después)
                start = max(0, match.start() - 30)
                end = min(len(texto), match.end() + 30)
                contexto = texto[start:end].strip()
                encontrados.append({
                    "patron": match.group(),
                    "contexto": f"...{contexto}..."
                })
        
        resultados[tipo] = {
            "descripcion": info["descripcion"],
            "frecuencia": len(encontrados),
            "ejemplos": encontrados[:3]  # Limitamos a 3 ejemplos por tipo
        }
    
    return resultados

def procesar_transcripcion(transcript) -> dict:
    """
    Procesa la transcripción y analiza las intervenciones.
    """
    # Separar intervenciones por hablante
    intervenciones_por_hablante = defaultdict(list)
    
    for utterance in transcript.utterances:
        speaker = f"Hablante {utterance.speaker}"
        intervenciones_por_hablante[speaker].append({
            "texto": utterance.text,
            "tiempo": utterance.start
        })
    
    # Analizar cada hablante
    analisis_por_hablante = {}
    for hablante, intervenciones in intervenciones_por_hablante.items():
        texto_completo = " ".join([i["texto"] for i in intervenciones])
        
        # Análisis básico de persuasión
        analisis_basico = analizar_habilidades_persuasion(intervenciones)
        
        # Análisis de patrones persuasivos
        patrones = analizar_patrones_persuasivos(texto_completo)
        
        analisis_por_hablante[hablante] = {
            "analisis_basico": analisis_basico,
            "patrones_persuasivos": patrones
        }
    
    return analisis_por_hablante

def generar_nombre_archivo(archivo_entrada: str, tipo: str = "transcripcion") -> str:
    """
    Genera un nombre de archivo único basado en el archivo de entrada.
    """
    # Obtener el nombre base del archivo sin extensión
    nombre_base = os.path.splitext(os.path.basename(archivo_entrada))[0]
    
    # Añadir timestamp para asegurar unicidad
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Crear nombre de archivo
    return f"{tipo}_{nombre_base}_{timestamp}.txt"

def guardar_transcripcion(texto: str, archivo_entrada: str):
    """
    Guarda la transcripción en un archivo de texto con nombre único.
    """
    # Obtener el directorio actual
    directorio_actual = os.getcwd()
    
    # Generar nombre de archivo
    nombre_base = os.path.splitext(os.path.basename(archivo_entrada))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"transcripcion_{nombre_base}_{timestamp}.txt"
    
    # Ruta completa del archivo
    ruta_completa = os.path.join(directorio_actual, nombre_archivo)
    
    try:
        with open(ruta_completa, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write(f"TRANSCRIPCIÓN: {os.path.basename(archivo_entrada)}\n")
            f.write(f"Fecha y hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*70 + "\n\n")
            f.write(texto)
        print(f"\nTranscripción guardada en: {ruta_completa}")
    except Exception as e:
        print(f"Error al guardar la transcripción: {e}")
        print(f"Intentando guardar en: {ruta_completa}")

def guardar_analisis(texto: str, archivo_entrada: str, hablante: str):
    """
    Guarda el análisis en un archivo de texto con nombre único.
    """
    # Obtener el directorio actual
    directorio_actual = os.getcwd()
    
    # Generar nombre de archivo
    nombre_base = os.path.splitext(os.path.basename(archivo_entrada))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"analisis_{hablante}_{nombre_base}_{timestamp}.txt"
    
    # Ruta completa del archivo
    ruta_completa = os.path.join(directorio_actual, nombre_archivo)
    
    try:
        with open(ruta_completa, 'w', encoding='utf-8') as f:
            f.write(texto)
        print(f"\nAnálisis guardado en: {ruta_completa}")
    except Exception as e:
        print(f"Error al guardar el análisis: {e}")
        print(f"Intentando guardar en: {ruta_completa}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analiza habilidades de persuasión en una conversación"
    )
    parser.add_argument(
        "audio_file",
        help="Ruta al archivo de audio/video"
    )
    args = parser.parse_args()

    try:
        # Transcribir el audio
        transcript = transcribe_audio(args.audio_file)
        
        # Guardar la transcripción completa
        texto_completo = "TRANSCRIPCIÓN PALABRA POR PALABRA\n"
        texto_completo += "="*50 + "\n\n"
        
        for i, utterance in enumerate(transcript.utterances, 1):
            texto_completo += f"{i}. Hablante {utterance.speaker}:\n"
            texto_completo += f"   \"{utterance.text}\"\n\n"
        
        guardar_transcripcion(texto_completo, args.audio_file)
        
        # Analizar la conversación
        print("\nAnalizando habilidades de persuasión...")
        analisis = procesar_transcripcion(transcript)
        
        # Generar y mostrar el reporte para cada hablante
        for hablante, resultados in analisis.items():
            print(f"\nAnálisis para {hablante}:")
            
            # Reporte básico de persuasión
            reporte_basico = generar_reporte_persuasion(resultados["analisis_basico"])
            print(reporte_basico)
            
            # Mostrar análisis de patrones persuasivos
            print("\nANÁLISIS DE PATRONES PERSUASIVOS:")
            print("="*70)
            
            patrones = resultados["patrones_persuasivos"]
            for tipo, info in patrones.items():
                print(f"\n{info['descripcion'].upper()}:")
                print(f"Frecuencia: {info['frecuencia']}")
                if info['ejemplos']:
                    print("Ejemplos encontrados:")
                    for ejemplo in info['ejemplos']:
                        print(f"• {ejemplo['patron']}: {ejemplo['contexto']}")
            
            # Guardar análisis individual
            contenido_completo = reporte_basico + "\n\n" + "ANÁLISIS DE PATRONES PERSUASIVOS\n" + "="*70
            
            for tipo, info in patrones.items():
                contenido_completo += f"\n\n{info['descripcion'].upper()}:"
                contenido_completo += f"\nFrecuencia: {info['frecuencia']}"
                if info['ejemplos']:
                    contenido_completo += "\nEjemplos encontrados:"
                    for ejemplo in info['ejemplos']:
                        contenido_completo += f"\n• {ejemplo['patron']}: {ejemplo['contexto']}"
            
            guardar_analisis(contenido_completo, args.audio_file, hablante.replace(' ', '_'))
            
    except Exception as e:
        print(f"Error durante el procesamiento: {e}")

# Uso:
# 1. Instala la librería de AssemblyAI: pip install assemblyai
# 2. Exporta tu clave de API:
#    export ASSEMBLYAI_API_KEY="TU_API_KEY"
# 3. Ejecuta el script:
#    python speech_to_text.py ruta/audio.mp3
