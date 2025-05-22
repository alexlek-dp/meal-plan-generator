# 1. Image de base Python
FROM python:3.10-slim

# 2. Définir le répertoire de travail
WORKDIR /app

# 3. Copier les fichiers nécessaires
COPY . /app

# 4. Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# 5. Exposer le port 8000
EXPOSE 8000

# 6. Lancer l’application Flask
CMD ["python", "app.py"]
