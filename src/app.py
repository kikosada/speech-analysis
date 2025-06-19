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
            mensaje = "¡Felicidades! Tu perfil es excepcional para Crediclub. Nos impresiona tu experiencia y visión clara del negocio. Nuestro equipo se pondrá en contacto contigo muy pronto para discutir las excelentes oportunidades de colaboración."
        elif score >= 7:
            mensaje = "¡Excelente potencial! Tu perfil muestra una sólida base para colaborar con Crediclub. Valoramos tu experiencia y tenemos interés en explorar juntos las posibilidades. Pronto te contactaremos para profundizar en los detalles."
        elif score >= 5:
            mensaje = "Gracias por tu interés en Crediclub. Hemos identificado áreas donde podríamos trabajar juntos para fortalecer la propuesta. Te contactaremos para discutir cómo podemos ayudarte a alcanzar tus objetivos."
        else:
            mensaje = "Agradecemos tu acercamiento a Crediclub. Para poder evaluar mejor tu propuesta, necesitaríamos más información sobre tu experiencia y objetivos. Nuestro equipo te contactará para programar una conversación más detallada."

        return jsonify({
            "score": round(score, 1),
            "detalles": detalles,
            "mensaje": mensaje
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 