from flask import Flask, request, send_file, jsonify
import pandas as pd
import json
import os

app = Flask(__name__)

df = pd.read_csv("data/recipe_api.csv", encoding="utf-8")
df["categories"] = df["categories"].astype(str)

MEAL_TYPES = {
    0: "breakfast",
    1: "midMorningSnack",
    2: "lunch",
    3: "afternoonSnack",
    4: "dinner"
}

DAY_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

MEAL_SPLIT = {
    0: 0.20,
    1: 0.10,
    2: 0.35,
    3: 0.10,
    4: 0.25
}

def generate_api_meal_plan(df, target_kcal, carbs_ratio, fat_ratio, protein_ratio, nb_days):
    meal_plan = []
    used_ids = set()

    for i in range(nb_days):
        day_plan = {"day": DAY_NAMES[i], "mealTypes": {}, "dailyTotals": {}}
        totals = {"calories": 0, "carbs": 0, "protein": 0, "fats": 0}

        for cat_id, meal_key in MEAL_TYPES.items():
            meal_target = target_kcal * MEAL_SPLIT[cat_id]
            meal_tolerance = 0.15 * meal_target
            min_kcal, max_kcal = meal_target - meal_tolerance, meal_target + meal_tolerance

            valid = df[df["categories"].str.contains(str(cat_id))].copy()
            valid = valid[~valid["id"].isin(used_ids)]
            valid = valid.sample(frac=1)

            meal_recipes = []
            meal_kcal = 0

            for _, row in valid.iterrows():
                kcal = float(row["energy_kcal"])
                max_serv = int((max_kcal - meal_kcal) // kcal)
                if max_serv <= 0:
                    continue

                servings = min(int(row["servings"]), max_serv)
                if servings <= 0:
                    continue

                total_kcal = servings * kcal
                if meal_kcal + total_kcal > max_kcal:
                    continue

                carbs = row.get("carbs", 0)
                fats = row.get("fat", 0)
                protein = row.get("protein", 0)

                meal_recipes.append({
                    "recipeId": int(row["id"]),
                    "name": row["name"],
                    "servings": round(servings, 2),
                    "nutrition": {
                        "calories": round(total_kcal, 2),
                        "carbs": round(carbs * servings, 2),
                        "protein": round(protein * servings, 2),
                        "fats": round(fats * servings, 2)
                    }
                })

                meal_kcal += total_kcal
                totals["calories"] += total_kcal
                totals["carbs"] += carbs * servings
                totals["protein"] += protein * servings
                totals["fats"] += fats * servings

                used_ids.add(int(row["id"]))

                if meal_kcal >= min_kcal:
                    break

            day_plan["mealTypes"][meal_key] = meal_recipes

        day_plan["dailyTotals"] = {
            "calories": round(totals["calories"], 2),
            "carbs": round(totals["carbs"], 2),
            "protein": round(totals["protein"], 2),
            "fats": round(totals["fats"], 2),
            "calorieDeviation": round(abs(totals["calories"] - target_kcal), 2)
        }

        meal_plan.append(day_plan)

    return {
        "success": True,
        "mealPlan": meal_plan,
        "targets": {
            "caloriesPerDay": round(target_kcal / nb_days, 2),
            "carbs": round((target_kcal * carbs_ratio) / nb_days, 2),
            "protein": round((target_kcal * protein_ratio) / nb_days, 2),
            "fats": round((target_kcal * fat_ratio) / nb_days, 2)
        }
    }

@app.route("/api/generate-meal-plan", methods=["POST"])
def api_generate_meal_plan():
    try:
        data = request.get_json()
        kcal = data["calories"]
        carbs = data["carbs"]
        fats = data["fats"]
        protein = data["protein"]
        days = int(data["days"])

        result = generate_api_meal_plan(
            df,
            target_kcal=kcal,
            carbs_ratio=carbs,
            fat_ratio=fats,
            protein_ratio=protein,
            nb_days=days
        )

        os.makedirs("output", exist_ok=True)
        with open("output/last_week_plan.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/plan")
def serve_json():
    path = "output/last_week_plan.json"
    if os.path.exists(path):
        return send_file(path, as_attachment=False)
    return "Aucun JSON généré", 404

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)

