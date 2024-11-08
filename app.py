from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import pandas as pd
from ortools.sat.python import cp_model

app = FastAPI()

# Load data at startup
recipe_df = pd.read_csv("recipe_202410162311.csv")

# TODO: Not needed for now
# meal_plan_df = pd.read_csv("meal_plan_202410170111.csv")
# food_df = pd.read_csv("food_202410152357.csv")
# category_df = pd.read_csv("recipe_categories_202410221917.csv")

# Convert relevant columns to integers
recipe_df["id"] = recipe_df["id"].astype(int)

# TODO: Not needed for now
# category_df["recipe_id"] = category_df["recipe_id"].astype(int)

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
    # meal_types: List[int] = Field(default=[1, 2, 3])
    days: int = Field(default=7, gt=0, le=14)
    meal_frequency: int = Field(default=3, gt=0, le=6)


# TODO: Delegate these filters to the BE
def query_food_database():
    # selected_recipes = category_df[category_df["categories"].isin(meal_types)]
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


def generate_meal_plan(selected_recipes, targets, meal_frequency, days):
    model = cp_model.CpModel()

    recipe_vars = {}
    for day in range(days):
        for _, recipe in selected_recipes.iterrows():
            recipe_vars[(day, recipe["id"])] = model.NewIntVar(
                0, meal_frequency, f'recipe_{day}_{recipe["id"]}'
            )

    lower_calorie_bound = int(targets["calories_per_day"]) - 100
    upper_calorie_bound = int(targets["calories_per_day"]) + 100

    for day in range(days):
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

        model.Add(
            sum(recipe_vars[(day, r.id)] for r in selected_recipes.itertuples())
            == meal_frequency
        )

    model.Maximize(
        sum(
            recipe_vars[(day, r["id"])] * int(r["energy_kcal"])
            for day in range(days)
            for _, r in selected_recipes.iterrows()
        )
    )

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    weekly_plan = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for day in range(days):
            meal_plan = []
            for recipe_id in selected_recipes["id"]:
                amount = solver.Value(recipe_vars[(day, recipe_id)])
                if amount > 0:
                    meal_plan.append({"recipe_id": recipe_id, "amount": amount})
            weekly_plan.append(meal_plan)
    return weekly_plan


def format_meal_plan(weekly_plan, calories_per_day):
    if not weekly_plan:
        raise HTTPException(status_code=400, detail="No feasible meal plan found")

    formatted_plan = []
    for day_num, meal_plan in enumerate(weekly_plan, start=1):
        daily_meals = []
        daily_calories = 0

        for meal_type_index, recipe in enumerate(meal_plan, start=1):
            recipe_id = recipe["recipe_id"]
            recipe_data = recipe_df[recipe_df["id"] == recipe_id].iloc[0]
            calories = recipe_data["energy_kcal"] * recipe["amount"]
            daily_calories += calories

            daily_meals.append(
                {
                    "id": recipe_id,
                    "name": recipe_data["name"],
                    "servings": recipe["amount"],
                    "mealType": meal_type_map[meal_type_index % len(meal_type_map)],
                    "nutrition": {
                        "calories": float(calories),
                        "carbs": float(recipe_data["carbs"]),
                        "fats": float(recipe_data["total_fats"]),
                        "protein": float(recipe_data["protein"]),
                    },
                }
            )

        formatted_plan.append(
            {
                "day": day_num,
                "meals": daily_meals,
                "totals": {
                    "calories": float(daily_calories),
                    "deviation": float(daily_calories - calories_per_day),
                },
            }
        )

    return formatted_plan


@app.get("/health-check")
async def health_check():
    return {"status": "ok"}


@app.post("/generate-meal-plan")
async def create_meal_plan(request: MealPlanRequest):
    print(request)
    try:
        selected_recipes = query_food_database()
        targets = calculate_macronutrient_targets(
            request.calories_per_day,
            request.carbs_ratio,
            request.fats_ratio,
            request.protein_ratio,
        )
        weekly_plan = generate_meal_plan(
            selected_recipes, targets, request.meal_frequency, request.days
        )

        formatted_plan = format_meal_plan(weekly_plan, request.calories_per_day)

        return {"success": True, "meal_plan": formatted_plan, "targets": targets}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
