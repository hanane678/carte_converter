from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import traceback
import json
import os
import uuid

app = Flask(__name__)

# ── Configuration ─────────────────────────────────────────────
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
ALLOWED_EXT = {"xlsx", "xls"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Helpers (Outils logiques) ─────────────────────────────────

def to_hex(value):
    """Convertit en HEX. Gère le décimal pur ou l'hexadécimal déjà écrit."""
    val_str = str(value).strip()
    try:
        # Si c'est un nombre entier (ex: 12345), on le convertit en HEX
        if val_str.isdigit():
            return hex(int(val_str))[2:].upper()
        # Si c'est déjà de l'hexadécimal (ex: 1A3F), on valide le format
        int(val_str, 16)
        return val_str.upper()
    except (ValueError, TypeError):
        raise ValueError(f"Valeur invalide : '{value}'. Doit être un nombre ou de l'HEX.")

def get_ctr_value(val):
    """Convertit le texte ou le chiffre en code CTR (1, 2 ou 3)."""
    mapping = {
        "personnelle": 1,
        "etudiant":    2,
        "abonnement":  3,
    }
    val = str(val).strip().lower()
    
    # Si l'utilisateur a déjà mis 1, 2 ou 3 dans l'Excel
    if val in ["1", "2", "3"]:
        return int(val)
    
    # Sinon on regarde dans le dictionnaire
    if val in mapping:
        return mapping[val]
    
    raise ValueError(f"Type '{val}' inconnu (utilisez: personnelle, etudiant, abonnement ou 1, 2, 3)")

def validate_date(year, month):
    if not (year.isdigit() and len(year) == 4):
        raise ValueError("L'année doit être au format YYYY (ex: 2026)")
    if not (month.isdigit() and len(month) == 2 and 1 <= int(month) <= 12):
        raise ValueError("Le mois doit être au format MM (01 à 12)")

def save_json(data, key):
    """Sauvegarde le JSON avec un nom unique."""
    unique_id = uuid.uuid4().hex[:6]
    filename = f"{key}_{unique_id}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return filename

# ── Routes ────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    """Conversion manuelle via le formulaire."""
    try:
        card_number = request.form.get('card_number', '').strip()
        card_type   = request.form.get('card_type', 'personnelle').strip() # 'card_type' vient du <select> HTML
        year        = request.form.get('year', '').strip()
        month       = request.form.get('month', '').strip()

        if not card_number:
            return jsonify({"error": "Le numéro de carte est requis"}), 400

        validate_date(year, month)

        ns  = to_hex(card_number)
        ctr = get_ctr_value(card_type)
        key = f"{year}{month}"

        result = {key: [{"ns": ns, "ctr": ctr}]}
        filename = save_json(result, key)

        return jsonify({"data": result, "filename": filename})

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Erreur serveur"}), 500

@app.route('/upload', methods=['POST'])
def upload():
    """Conversion par lot via fichier Excel."""
    try:
        file  = request.files.get('file')
        year  = request.form.get('year', '').strip()
        month = request.form.get('month', '').strip()

        if not file or file.filename == '':
            return jsonify({"error": "Aucun fichier sélectionné"}), 400

        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            return jsonify({"error": "Format .xlsx ou .xls requis"}), 400

        validate_date(year, month)

        # Sauvegarde temporaire
        temp_path = os.path.join(UPLOAD_DIR, f"temp_{uuid.uuid4().hex}.xlsx")
        file.save(temp_path)

        # Lecture Excel avec Pandas
        df = pd.read_excel(temp_path)
        df.columns = [str(c).strip().lower() for c in df.columns]

        # Vérification des colonnes NS et CTR
        if 'ns' not in df.columns or 'ctr' not in df.columns:
            return jsonify({"error": f"Colonnes 'ns' et 'ctr' obligatoires. Trouvées: {list(df.columns)}"}), 400

        data = []
        for idx, row in df.iterrows():
            if pd.isna(row['ns']): continue
            
            try:
                ns  = to_hex(row['ns'])
                ctr = get_ctr_value(row['ctr'])
                data.append({"ns": ns, "ctr": ctr})
            except ValueError as e:
                return jsonify({"error": f"Ligne {idx + 2} : {str(e)}"}), 400

        key = f"{year}{month}"
        result = {key: data}
        filename = save_json(result, key)

        # Nettoyage fichier temporaire
        os.remove(temp_path)

        return jsonify({"data": result, "filename": filename})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>')
def download(filename):
    safe_name = os.path.basename(filename)
    path = os.path.join(OUTPUT_DIR, safe_name)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return jsonify({"error": "Fichier introuvable"}), 404

if __name__ == '__main__':
    app.run(debug=True)