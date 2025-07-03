from flask import Flask, request, jsonify, render_template, session
import os
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_123')

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
        if 'rfc' in datos:
            session['rfc'] = datos['rfc']
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/cliente_score', methods=['GET'])
def cliente_score():
    try:
        score = random.uniform(5, 10)
        detalles = {
            "presentacion": round(random.uniform(5, 10), 1),
            "claridad": round(random.uniform(5, 10), 1),
            "contenido": round(random.uniform(5, 10), 1)
        }
        
        mensaje = ""
        if score >= 9:
            mensaje = "¡Nos gusta mucho tu empresa! Tu perfil es sólido y muestra una visión clara del negocio. Alguien de nuestro equipo te contactará pronto para conocerte mejor."
        elif score >= 7:
            mensaje = "Tu empresa tiene muy buen potencial. Vemos varios aspectos interesantes que vale la pena explorar. Pronto alguien de nuestro equipo se pondrá en contacto contigo."
        elif score >= 5:
            mensaje = "Gracias por compartir tu información con Crediclub. Hemos detectado algunas áreas con oportunidad de mejora. Te contactaremos para profundizar un poco más y entender mejor tu enfoque."
        else:
            mensaje = "Agradecemos tu interés en Crediclub. Por ahora, necesitamos más información y claridad sobre tu empresa para poder evaluarla adecuadamente. Si lo deseas, puedes reintentar en un mes."

        return jsonify({
            "score": round(score, 1),
            "detalles": detalles,
            "mensaje": mensaje
        })
    except Exception as e:
        app.logger.error(f"Error en cliente_score: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return "ok", 200

if __name__ == '__main__':
    app.run(debug=True) 