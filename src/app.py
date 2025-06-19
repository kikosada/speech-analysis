from flask import Flask, request, jsonify, render_template
import os
import random
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cliente')
def cliente():
    return render_template('cliente.html')

@app.route('/cliente_datos', methods=['POST'])
def cliente_datos():
    try:
        datos = request.json
        # Aquí normalmente guardaríamos los datos
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/cliente_score')
def cliente_score():
    try:
        # Simulación de score
        score = random.uniform(5, 10)
        detalles = {
            "presentacion": round(random.uniform(5, 10), 1),
            "claridad": round(random.uniform(5, 10), 1),
            "contenido": round(random.uniform(5, 10), 1)
        }
        
        mensaje = ""
        if score >= 9:
            mensaje = "¡Excelente presentación! Tu propuesta es muy sólida."
        elif score >= 7:
            mensaje = "Muy buena presentación. Tienes una propuesta interesante."
        elif score >= 5:
            mensaje = "Tu presentación muestra áreas de oportunidad que podemos trabajar juntos."
        else:
            mensaje = "Necesitamos más información para evaluar completamente tu propuesta."

        return jsonify({
            "score": round(score, 1),
            "detalles": detalles,
            "mensaje": mensaje
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 