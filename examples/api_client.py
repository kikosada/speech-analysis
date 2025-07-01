#!/usr/bin/env python3
"""
Cliente de ejemplo para la API de Análisis de Presentaciones Empresariales
"""

import requests
import json
import os
from typing import Dict, Any, Optional

class PresentationAnalysisAPI:
    """Cliente para la API de análisis de presentaciones"""
    
    def __init__(self, base_url: str, api_key: str):
        """
        Inicializar el cliente API
        
        Args:
            base_url: URL base de la API (ej: https://tu-dominio.onrender.com/api/v1)
            api_key: API key para autenticación
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-API-Key': api_key,
            'Content-Type': 'application/json'
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Verificar estado de la API"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def upload_presentation(self, 
                          file_path: str, 
                          rfc: str, 
                          company_name: str = "", 
                          presenter_name: str = "") -> Dict[str, Any]:
        """
        Subir y analizar una presentación
        
        Args:
            file_path: Ruta al archivo de video
            rfc: RFC de la empresa
            company_name: Nombre de la empresa (opcional)
            presenter_name: Nombre del presentador (opcional)
        
        Returns:
            Respuesta de la API con el análisis
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        
        url = f"{self.base_url}/presentations/upload"
        
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'rfc': rfc,
                'company_name': company_name,
                'presenter_name': presenter_name
            }
            headers = {'X-API-Key': self.api_key}
            
            response = requests.post(url, headers=headers, files=files, data=data)
            
            if response.status_code != 200:
                raise Exception(f"Error en la API: {response.status_code} - {response.text}")
            
            return response.json()
    
    def get_presentation(self, rfc: str) -> Dict[str, Any]:
        """
        Obtener análisis de una presentación
        
        Args:
            rfc: RFC de la empresa
        
        Returns:
            Datos de la presentación y análisis
        """
        url = f"{self.base_url}/presentations/{rfc}"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 404:
            raise Exception(f"Presentación no encontrada para RFC: {rfc}")
        
        if response.status_code != 200:
            raise Exception(f"Error en la API: {response.status_code} - {response.text}")
        
        return response.json()
    
    def get_presentation_status(self, rfc: str) -> Dict[str, Any]:
        """
        Verificar estado de procesamiento
        
        Args:
            rfc: RFC de la empresa
        
        Returns:
            Estado de la presentación
        """
        url = f"{self.base_url}/presentations/{rfc}/status"
        response = requests.get(url, headers=self.headers)
        return response.json()
    
    def list_presentations(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        Listar presentaciones
        
        Args:
            limit: Número máximo de resultados
            offset: Offset para paginación
        
        Returns:
            Lista de presentaciones
        """
        url = f"{self.base_url}/presentations"
        params = {'limit': limit, 'offset': offset}
        response = requests.get(url, headers=self.headers, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Error en la API: {response.status_code} - {response.text}")
        
        return response.json()
    
    def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        """
        Analizar solo un transcript
        
        Args:
            transcript: Texto a analizar
        
        Returns:
            Análisis del transcript
        """
        url = f"{self.base_url}/analysis/transcript"
        data = {'transcript': transcript}
        response = requests.post(url, headers=self.headers, json=data)
        
        if response.status_code != 200:
            raise Exception(f"Error en la API: {response.status_code} - {response.text}")
        
        return response.json()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de la API"""
        url = f"{self.base_url}/metrics"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code != 200:
            raise Exception(f"Error en la API: {response.status_code} - {response.text}")
        
        return response.json()


def main():
    """Ejemplo de uso del cliente API"""
    
    # Configuración
    BASE_URL = "https://tu-dominio.onrender.com/api/v1"  # Cambiar por tu URL
    API_KEY = "tu-api-key-aqui"  # Cambiar por tu API key
    
    # Crear cliente
    api = PresentationAnalysisAPI(BASE_URL, API_KEY)
    
    try:
        # 1. Verificar estado de la API
        print("=== Verificando estado de la API ===")
        health = api.health_check()
        print(f"Estado: {health['status']}")
        print(f"Versión: {health['version']}")
        print()
        
        # 2. Subir y analizar una presentación
        print("=== Subiendo presentación ===")
        # Descomenta las siguientes líneas para subir un archivo real
        # result = api.upload_presentation(
        #     file_path="presentacion.mp4",
        #     rfc="ABC123456789",
        #     company_name="Mi Empresa S.A.",
        #     presenter_name="Juan Pérez"
        # )
        # print(f"Análisis completado: {result['message']}")
        # print(f"Puntuación general: {result['analysis']['scores']['overall']}")
        # print()
        
        # 3. Analizar un transcript de ejemplo
        print("=== Analizando transcript ===")
        transcript = """
        Buenos días, hoy les voy a presentar nuestra empresa Tecnología Avanzada S.A.
        Somos una empresa fundada en 2010 que se dedica al desarrollo de software empresarial.
        Nuestra misión es facilitar la transformación digital de las empresas mexicanas.
        Ofrecemos soluciones en gestión de recursos empresariales, CRM y automatización.
        Nuestros valores principales son la innovación, la calidad y el servicio al cliente.
        Hemos logrado implementar más de 500 proyectos exitosos en todo el país.
        """
        
        analysis = api.analyze_transcript(transcript)
        print("Análisis del transcript:")
        print(f"Puntuación general: {analysis['analysis']['scores']['overall']}")
        print(f"Resumen: {analysis['analysis']['resumen']}")
        print("Feedback:")
        for feedback in analysis['analysis']['feedback']:
            print(f"  - {feedback}")
        print()
        
        # 4. Obtener métricas
        print("=== Métricas de la API ===")
        metrics = api.get_metrics()
        print(f"Total de presentaciones: {metrics['total_presentations']}")
        print(f"Tamaño total de almacenamiento: {metrics['total_storage_size_mb']} MB")
        print()
        
        # 5. Listar presentaciones (si hay alguna)
        print("=== Listando presentaciones ===")
        presentations = api.list_presentations(limit=5)
        print(f"Total de presentaciones encontradas: {presentations['total']}")
        for presentation in presentations['presentations']:
            print(f"  - RFC: {presentation['rfc']}")
            print(f"    Empresa: {presentation.get('company_name', 'N/A')}")
            print(f"    Fecha: {presentation.get('upload_timestamp', 'N/A')}")
            print()
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main() 