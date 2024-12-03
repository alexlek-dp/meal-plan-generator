from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
import pandas as pd
from ortools.sat.python import cp_model

app = FastAPI()

# Load data at startup
recipe_df = pd.read_csv("recipe_api.csv")
# Convert relevant columns to integers
recipe_df["id"] = recipe_df["id"].astype(int)

meal_type_enum_map = {
    "breakfast": 0,
    "lunch": 1,
    "dinner": 2,
    "mid_morning_snack": 3,
    "afternoon_snack": 4,
}

day_map = {
    1: "MONDAY",
    2: "TUESDAY",
    3: "WEDNESDAY",
    4: "THURSDAY",
    5: "FRIDAY",
    6: "SATURDAY",
    7: "SUNDAY",
}

meal_type_map = {
    0: "BREAKFAST",
    1: "MID_MORNING_SNACK",
    2: "LUNCH",
    3: "AFTERNOON_SNACK",
    4: "DINNER",
}

# Input validation model
class MealPlanRequest(BaseModel):
    calories: float = Field(default=2000, gt=0) 
    carbs: float = Field(default=0.5, ge=0, le=1)
    fats: float = Field(default=0.3, ge=0, le=1)
    protein: float = Field(default=0.2, ge=0, le=1)
    types: List[int] = Field(default=[0, 1, 2, 3, 4])
    days: int = Field(default=7, gt=0, le=14)

def query_food_database():
    # CHANGED: Parse meal types for each recipe
    recipe_df['meal_types_set'] = recipe_df['categories'].apply(
        lambda x: set(map(int, x.split(',')))
    )
    return recipe_df

def calculate_macronutrient_targets(
    calories_per_day, carbs_ratio, fats_ratio, protein_ratio
):
    carbs_calories = int(calories_per_day * carbs_ratio)
    fats_calories = int(calories_per_day * fats_ratio)
    protein_calories = int(calories_per_day * protein_ratio)

    return {
        "calories_per_day": calories_per_day,
        "carbs": carbs_calories // 4,
        "fats": fats_calories // 9,
        "protein": protein_calories // 4,
    }

def generate_meal_plan(
    selected_recipes, targets, days, meal_types, allow_multiple_dishes=False
):
    model = cp_model.CpModel()
    recipe_vars = {}

    # CHANGED: Create decision variables for each day, meal_type, and recipe
    for day in range(days):
        for meal_type in meal_types:
            for _, recipe in selected_recipes.iterrows():
                if meal_type in recipe['meal_types_set']:
                    recipe_vars[(day, meal_type, recipe["id"])] = model.NewIntVar(
                        0, 1, f'recipe_{day}_{meal_type}_{recipe["id"]}'
                    )

    # Set the calorie bounds
    lower_calorie_bound = int(targets["calories_per_day"]) - 100
    upper_calorie_bound = int(targets["calories_per_day"]) + 100

    # CHANGED: Add constraints for each day to meet calorie and macronutrient targets
    for day in range(days):
        # Calorie constraints for the day
        total_calories = sum(
            recipe_vars[(day, meal_type, recipe["id"])] * int(recipe["energy_kcal"])
            for meal_type in meal_types
            for _, recipe in selected_recipes.iterrows()
            if (day, meal_type, recipe["id"]) in recipe_vars
        )
        model.Add(total_calories >= lower_calorie_bound)
        model.Add(total_calories <= upper_calorie_bound)

        # Macronutrient constraints for the day
        total_carbs = sum(
            recipe_vars[(day, meal_type, recipe["id"])] * int(recipe["carbs"])
            for meal_type in meal_types
            for _, recipe in selected_recipes.iterrows()
            if (day, meal_type, recipe["id"]) in recipe_vars
        )
        model.Add(total_carbs <= targets["carbs"])

        total_fats = sum(
            recipe_vars[(day, meal_type, recipe["id"])] * int(recipe["total_fats"])
            for meal_type in meal_types
            for _, recipe in selected_recipes.iterrows()
            if (day, meal_type, recipe["id"]) in recipe_vars
        )
        model.Add(total_fats <= targets["fats"])

        total_protein = sum(
            recipe_vars[(day, meal_type, recipe["id"])] * int(recipe["protein"])
            for meal_type in meal_types
            for _, recipe in selected_recipes.iterrows()
            if (day, meal_type, recipe["id"]) in recipe_vars
        )
        model.Add(total_protein <= targets["protein"])

        # CHANGED: Ensure each meal type has at least one recipe per day
        for meal_type in meal_types:
            if not allow_multiple_dishes:
                model.Add(
                    sum(
                        recipe_vars[(day, meal_type, recipe["id"])]
                        for _, recipe in selected_recipes.iterrows()
                        if (day, meal_type, recipe["id"]) in recipe_vars
                    ) == 1
                )
            else:
                model.Add(
                    sum(
                        recipe_vars[(day, meal_type, recipe["id"])]
                        for _, recipe in selected_recipes.iterrows()
                        if (day, meal_type, recipe["id"]) in recipe_vars
                    ) >= 1
                )

    # CHANGED: Add constraints to ensure unique dishes across all days and meal types
    for _, recipe in selected_recipes.iterrows():
        model.Add(
            sum(
                recipe_vars[(day, meal_type, recipe["id"])]
                for day in range(days)
                for meal_type in meal_types
                if (day, meal_type, recipe["id"]) in recipe_vars
            ) <= 1
        )

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        weekly_plan = []
        for day in range(days):
            daily_plan = {}
            for meal_type in meal_types:
                meal_type_recipes = [
                    {"recipe_id": recipe["id"], "amount": 1}
                    for _, recipe in selected_recipes.iterrows()
                    if (day, meal_type, recipe["id"]) in recipe_vars
                    and solver.Value(recipe_vars[(day, meal_type, recipe["id"])]) == 1
                ]
                if meal_type_recipes:
                    meal_type_name = meal_type_map[meal_type]
                    daily_plan[meal_type_name] = meal_type_recipes
            weekly_plan.append(daily_plan)
        return weekly_plan
    elif not allow_multiple_dishes:
        print("Single-dish meal plan infeasible; attempting multi-dish plan.")
        return generate_meal_plan(
            selected_recipes, targets, days, meal_types, allow_multiple_dishes=True
        )
    else:
        print("No feasible meal plan found.")
        return None

def format_meal_plan(weekly_plan: List, user_preferences: dict, selected_recipes: pd.DataFrame) -> dict:
    """
    Format the meal plan into a structured JSON response with camelCase keys
    """
    if not weekly_plan:
        raise HTTPException(status_code=400, detail="No feasible meal plan found")

    response = {
        "success": True,
        "mealPlan": [],
        "targets": {
            "caloriesPerDay": user_preferences["calories_per_day"],
            "carbs": user_preferences.get("carbs", 0),
            "protein": user_preferences.get("protein", 0),
            "fats": user_preferences.get("fats", 0)
        }
    }

    meal_type_mapping = {
        "BREAKFAST": "breakfast",
        "MID_MORNING_SNACK": "midMorningSnack",
        "LUNCH": "lunch",
        "AFTERNOON_SNACK": "afternoonSnack",
        "DINNER": "dinner"
    }

    for day_num, daily_meals in enumerate(weekly_plan, start=1):
        day_data = {
            "day": day_map.get(day_num, f"DAY_{day_num}"),
            "mealTypes": {},
            "dailyTotals": {
                "calories": 0,
                "carbs": 0,
                "protein": 0,
                "fats": 0
            }
        }

        # CHANGED: Process each meal type in the day
        for meal_type_name, meals in daily_meals.items():
            meal_type_key = meal_type_mapping.get(meal_type_name, meal_type_name.lower())
            day_data["mealTypes"][meal_type_key] = []

            for meal in meals:
                recipe_id = meal["recipe_id"]
                recipe_data = selected_recipes[selected_recipes["id"] == recipe_id].iloc[0]

                calories = float(recipe_data["energy_kcal"]) * meal["amount"]
                carbs = float(recipe_data["carbs"]) * meal["amount"]
                protein = float(recipe_data["protein"]) * meal["amount"]
                fats = float(recipe_data["total_fats"]) * meal["amount"]

                # Update daily totals
                day_data["dailyTotals"]["calories"] += calories
                day_data["dailyTotals"]["carbs"] += carbs
                day_data["dailyTotals"]["protein"] += protein
                day_data["dailyTotals"]["fats"] += fats

                # Get meal types for the recipe
                recipe_meal_types = []
                for category in recipe_data["categories"].split(","):
                    recipe_meal_types.append(meal_type_map[int(category)])

                meal_entry = {
                    "recipeId": recipe_id,
                    # "meal_type": recipe_meal_types,
                    "name": recipe_data["name"],
                    "servings": meal["amount"],
                    "nutrition": {
                        "calories": calories,
                        "carbs": carbs,
                        "protein": protein,
                        "fats": fats
                    }
                }
                day_data["mealTypes"][meal_type_key].append(meal_entry)

        # Remove empty meal types
        day_data["mealTypes"] = {k: v for k, v in day_data["mealTypes"].items() if v}

        # Calculate deviation from target calories
        day_data["dailyTotals"]["calorieDeviation"] = (
            day_data["dailyTotals"]["calories"] - user_preferences["calories_per_day"]
        )

        response["mealPlan"].append(day_data)

    return response

@app.get("/health-check")
async def health_check():
    return {"status": "ok"}

@app.post("/api/generate-meal-plan")
async def generate_meal_plan_endpoint(request: MealPlanRequest):
    try:
        # Get recipes from database
        selected_recipes = query_food_database()
        
        # Calculate targets
        targets = calculate_macronutrient_targets(
            request.calories,
            request.carbs,
            request.fats,
            request.protein
        )
        
        # CHANGED: Include meal types in user preferences
        user_preferences = {
            "calories_per_day": request.calories,
            "meal_types": request.types,
            **targets
        }
        
        # Generate the meal plan
        weekly_plan = generate_meal_plan(
            selected_recipes,
            targets,
            request.days,
            request.types
        )
        
        # Format the response
        response = format_meal_plan(
            weekly_plan,
            user_preferences,
            selected_recipes
        )
        
        return response

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
