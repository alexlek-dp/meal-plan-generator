from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import pandas as pd
from ortools.sat.python import cp_model

app = FastAPI()

# Load data at startup
recipe_df = pd.read_csv("recipe_api.csv")

# TODO: Not needed for now
# category_df = pd.read_csv("recipe_categories_202410221917.csv")

# Convert relevant columns to integers
recipe_df["id"] = recipe_df["id"].astype(int)


meal_type_enum_map = {
    "breakfast": 1,
    "lunch": 2,
    "dinner": 3,
    "mid_morning_snack": 4,
    "afternoon_snack": 5,
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
    1: "BREAKFAST",
    2: "MID_MORNING_SNACK",
    3: "LUNCH",
    4: "AFTERNOON_SNACK",
    5: "DINNER",
}


# Input validation model
class MealPlanRequest(BaseModel):
    calories_per_day: float = Field(default=2000, gt=0) 
    carbs_ratio: float = Field(default=0.5, ge=0, le=1)
    fats_ratio: float = Field(default=0.3, ge=0, le=1)
    protein_ratio: float = Field(default=0.2, ge=0, le=1)
    meal_types: List[int] = Field(default=[1, 2, 3])
    days: int = Field(default=7, gt=0, le=14)


# TODO: Implement
def query_food_database():
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

    # Create a binary variable for each recipe on each day
    for day in range(days):
        for _, recipe in selected_recipes.iterrows():
            recipe_vars[(day, recipe["id"])] = model.NewIntVar(
                0, 1, f'recipe_{day}_{recipe["id"]}'
            )

    # Set the calorie bounds
    lower_calorie_bound = int(targets["calories_per_day"]) - 100
    upper_calorie_bound = int(targets["calories_per_day"]) + 100

    # Add constraints for each day to meet calorie and macronutrient targets
    for day in range(days):
        # Calorie constraints for the day
        model.Add(
            sum(
                recipe_vars[(day, r["id"])] * int(r["energy_kcal"])
                for _, r in selected_recipes.iterrows()
            )
            >= lower_calorie_bound
        )
        model.Add(
            sum(
                recipe_vars[(day, r["id"])] * int(r["energy_kcal"])
                for _, r in selected_recipes.iterrows()
            )
            <= upper_calorie_bound
        )

        # Macronutrient constraints for the day
        model.Add(
            sum(
                recipe_vars[(day, r["id"])] * int(r["carbs"])
                for _, r in selected_recipes.iterrows()
            )
            <= targets["carbs"]
        )
        model.Add(
            sum(
                recipe_vars[(day, r["id"])] * int(r["total_fats"])
                for _, r in selected_recipes.iterrows()
            )
            <= targets["fats"]
        )
        model.Add(
            sum(
                recipe_vars[(day, r["id"])] * int(r["protein"])
                for _, r in selected_recipes.iterrows()
            )
            <= targets["protein"]
        )

        # Ensure each meal type has at least one recipe per day
        (
            model.Add(
                sum(recipe_vars[(day, r["id"])] for _, r in selected_recipes.iterrows())
                == len(meal_types)
            )
            if not allow_multiple_dishes
            else model.Add(
                sum(recipe_vars[(day, r["id"])] for _, r in selected_recipes.iterrows())
                >= len(meal_types)
            )
        )

    # Add constraints to ensure unique dishes across all days
    for _, recipe in selected_recipes.iterrows():
        model.Add(sum(recipe_vars[(day, recipe["id"])] for day in range(days)) <= 1)

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            weekly_plan = []
            for day in range(days):
                daily_plan = [
                    {"recipe_id": r["id"], "amount": 1}
                    for _, r in selected_recipes.iterrows()
                    if solver.Value(recipe_vars[(day, r["id"])]) == 1
                ]
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

    for day_num, daily_meals in enumerate(weekly_plan, start=1):
        day_data = {
            "day": day_map.get(day_num, f"DAY_{day_num}"),
            "mealTypes": {
                "breakfast": [],
                "lunch": [],
                "dinner": [],
                "midMorningSnack": [],
                "afternoonSnack": []
            },
            "dailyTotals": {
                "calories": 0,
                "carbs": 0,
                "protein": 0,
                "fats": 0
            }
        }

        meal_type_mapping = {
            "BREAKFAST": "breakfast",
            "LUNCH": "lunch",
            "DINNER": "dinner",
            "MID_MORNING_SNACK": "midMorningSnack",
            "AFTERNOON_SNACK": "afternoonSnack"
        }

        # Process each meal in the day
        for meal_index, meal in enumerate(daily_meals):
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

            meal_type = meal_type_map[user_preferences["meal_types"][meal_index % len(user_preferences["meal_types"])]]
            meal_entry = {
                "recipeId": recipe_id,
                "name": recipe_data["name"],
                "servings": meal["amount"],
                "nutrition": {
                    "calories": calories,
                    "carbs": carbs,
                    "protein": protein,
                    "fats": fats
                }
            }
            day_data["mealTypes"][meal_type_mapping[meal_type]].append(meal_entry)

        # Remove empty meal types
        day_data["mealTypes"] = {k: v for k, v in day_data["mealTypes"].items() if v}
        
        # Calculate deviation from target calories
        day_data["dailyTotals"]["calorieDeviation"] = (
            day_data["dailyTotals"]["calories"] - user_preferences["calories_per_day"]
        )
        
        response["mealPlan"].append(day_data)

    return response
    """
    Format the meal plan into a structured JSON response, grouped by meal type
    """
    if not weekly_plan:
        raise HTTPException(status_code=400, detail="No feasible meal plan found")

    response = {
        "success": True,
        "meal_plan": [],
        "targets": {
            "calories_per_day": user_preferences["calories_per_day"],
            "carbs": user_preferences.get("carbs", 0),
            "protein": user_preferences.get("protein", 0),
            "fats": user_preferences.get("fats", 0)
        }
    }

    for day_num, daily_meals in enumerate(weekly_plan, start=1):
        day_data = {
            "day": day_map.get(day_num, f"DAY_{day_num}"),
            "meal_types": {
                "BREAKFAST": [],
                "LUNCH": [],
                "DINNER": [],
                "MID_MORNING_SNACK": [],
                "AFTERNOON_SNACK": []
            },
            "daily_totals": {
                "calories": 0,
                "carbs": 0,
                "protein": 0,
                "fats": 0
            }
        }

        # Process each meal in the day
        for meal_index, meal in enumerate(daily_meals):
            recipe_id = meal["recipe_id"]
            recipe_data = selected_recipes[selected_recipes["id"] == recipe_id].iloc[0]
            
            # Calculate nutrition for the serving size
            calories = float(recipe_data["energy_kcal"]) * meal["amount"]
            carbs = float(recipe_data["carbs"]) * meal["amount"]
            protein = float(recipe_data["protein"]) * meal["amount"]
            fats = float(recipe_data["total_fats"]) * meal["amount"]

            # Update daily totals
            day_data["daily_totals"]["calories"] += calories
            day_data["daily_totals"]["carbs"] += carbs
            day_data["daily_totals"]["protein"] += protein
            day_data["daily_totals"]["fats"] += fats

            # Create meal entry
            meal_type = meal_type_map[user_preferences["meal_types"][meal_index % len(user_preferences["meal_types"])]]
            meal_entry = {
                "recipe_id": recipe_id,
                "name": recipe_data["name"],
                "servings": meal["amount"],
                "nutrition": {
                    "calories": calories,
                    "carbs": carbs,
                    "protein": protein,
                    "fats": fats
                }
            }
            day_data["meal_types"][meal_type].append(meal_entry)

        # Remove empty meal types
        day_data["meal_types"] = {k: v for k, v in day_data["meal_types"].items() if v}
        
        # Calculate deviation from target calories
        day_data["daily_totals"]["calorie_deviation"] = (
            day_data["daily_totals"]["calories"] - user_preferences["calories_per_day"]
        )
        
        response["meal_plan"].append(day_data)

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
            request.calories_per_day,
            request.carbs_ratio,
            request.fats_ratio,
            request.protein_ratio
        )
        
        # Generate the meal plan
        weekly_plan = generate_meal_plan(
            selected_recipes,
            targets,
            request.days,
            request.meal_types
        )
        
        # Format the response
        response = format_meal_plan(
            weekly_plan,
            {
                "calories_per_day": request.calories_per_day,
                "meal_types": request.meal_types,
                **targets
            },
            selected_recipes
        )
        
        return response

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
