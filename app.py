"""
app.py — Ponto de entrada da aplicação FestasVIP (versão OO).
"""
from flask import Flask
from database import Database
from controllers import cliente_bp, admin_bp

app = Flask(__name__)
app.secret_key = "festas_oo_secret_2024"

# Registra blueprints
app.register_blueprint(cliente_bp)
app.register_blueprint(admin_bp)

if __name__ == "__main__":
    Database.init()
    app.run(debug=True)
