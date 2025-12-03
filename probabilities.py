# -----------
# Imports
# -----------

import json
import datetime
import random
import os

# ----------------------
# DB Settings
# ----------------------

DATA_FILE = "week_data.json"

# ----------------------
# Main Defs
# ----------------------

def load_week_data():
    if not os.path.exists(DATA_FILE):
        return {"week_number": get_current_week(), "yes_count": 0 }
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if data["week_number"] != get_current_week():
        data = {"week_number": get_current_week(), "yes_count": 0 }
        save_week_data(data)

    return data

def save_week_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
def get_current_week():
    return datetime.date.today().isocalendar().week

def get_today_probabilities():
    weekday = datetime.datetime.today().weekday()
    probabilities = {
        0: (0.80, 0.20),
        1: (0.98, 0.02),
        2: (0.67, 0.33),
        3: (0.99, 0.01),
        4: (0.40, 0.60),
    }

    if weekday not in probabilities:
        return None
    
    return probabilities[weekday]

def roll_with_limit():
    data = load_week_data()

    if data["yes_count"] >= 2:
        return "No (Limite semanal alcanzado)"
    
    day_probs = get_today_probabilities()
    if day_probs is None:
        return "No (Sabados y Domingos prohibidos)"
    
    prob_no, prob_yes = day_probs
    result = random.choices(["No", "Si"], weights=[prob_no, prob_yes])[0]

    if result == "Si":
        data["yes_count"] += 1
        save_week_data(data)
    
    return result

# ----------------------
# End of File
# ----------------------
#? Made by ttsmc
# ----------------------
