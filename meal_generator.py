import pandas as pd
from ortools.sat.python import cp_model

# Load data
food_df = pd.read_csv('/kaggle/input/food-data/food_202410152357.csv')
recipe_df = pd.read_csv('/kaggle/input/d/pernicious07/tolerance/updated_recipe_df.csv')
meal_plan_df = pd.read_csv('/kaggle/input/food-data/meal_plan_202410170111.csv')
category_df = pd.read_csv('/kaggle/input/food-data/recipe_categories_202410221917.csv')

# Convert relevant columns to integers
recipe_df['id'] = recipe_df['id'].astype(int)
category_df['recipe_id'] = category_df['recipe_id'].astype(int)

def get_user_preferences():
    print("Default Values: \nDaily Calorie Target: 6000\nCarb Percentage: 50%\nFat Percentage: 30%\nProtein Percentage: 20%")
    print("Meal Types: BREAKFAST, LUNCH, DINNER, MID_MORNING_SNACK, AFTERNOON_SNACK")
    print("Days: 7\n")
    # User input section
    calories_per_day = float(input("Enter your daily calorie target (leave blank to use default): ") or 6000)
    carbs_ratio = float(input("Enter your carb percentage (leave blank to use default): ") or 0.5)
    fats_ratio = float(input("Enter your fat percentage (leave blank to use default): ") or 0.3)
    protein_ratio = float(input("Enter your protein percentage (leave blank to use default): ") or 0.2)

    # Meal types and intolerances
    meal_type_map = {
        "breakfast": 1, "lunch": 2, "dinner": 3, 
        "mid_morning_snack": 4, "afternoon_snack": 5
    }
    meal_types_input = input("Enter meal types (comma-separated, e.g., breakfast, lunch, dinner): ")
    meal_types = [meal_type_map.get(meal.strip().lower()) for meal in meal_types_input.split(",") if meal_type_map.get(meal.strip().lower())]
    days = int(input("Do you want a one-day or weekly meal plan? (Enter 1 for one day, 7 for weekly, default: 7): ") or 7)
    
    # Intolerance options
    print("\nFood Intolerance Options: Lactose Intolerance, Gluten Intolerance, Soy Intolerance, Nut Allergy, Shellfish Allergy, Egg Allergy, Dairy-Free, Non-Vegan, Vegetarian")
    intolerances_input = input("Enter your food intolerances (comma-separated): ").lower()
    intolerance_column_map = {
        'lactose intolerance': 'Lactose Intolerance', 'gluten intolerance': 'Gluten Intolerance',
        'soy intolerance': 'Soy Intolerance', 'nut allergy': 'Nut Allergy',
        'shellfish allergy': 'Shellfish Allergy', 'egg allergy': 'Egg Allergy',
        'dairy-free': 'Dairy-Free', 'non-vegan': 'Non Vegan', 'vegetarian': 'Vegetarian'
    }
    selected_intolerances = [intolerance_column_map[i.strip()] for i in intolerances_input.split(",") if i.strip() in intolerance_column_map]
    
    return {
        "calories_per_day": calories_per_day,
        "carbs_ratio": carbs_ratio,
        "fats_ratio": fats_ratio,
        "protein_ratio": protein_ratio,
        "meal_types": meal_types,
        "days": days,
        "intolerances": selected_intolerances
    }

def query_food_database(meal_types, intolerances):
    selected_recipes = category_df[category_df['categories'].isin(meal_types)]
    filtered_recipes = recipe_df[recipe_df['id'].isin(selected_recipes['recipe_id'])]
    for intolerance in intolerances:
        filtered_recipes = filtered_recipes[filtered_recipes[intolerance] != 1]  # Exclude recipes with intolerances
    return filtered_recipes

def calculate_macronutrient_targets(calories_per_day, carbs_ratio, fats_ratio, protein_ratio):
    return {
        "calories_per_day": calories_per_day,
        "carbs": int(calories_per_day * carbs_ratio / 4),
        "fats": int(calories_per_day * fats_ratio / 9),
        "protein": int(calories_per_day * protein_ratio / 4)
    }

def generate_meal_plan(selected_recipes, targets, days, meal_types, allow_multiple_dishes=False):
    model = cp_model.CpModel()
    recipe_vars = {}
    
    # Create a binary variable for each recipe on each day
    for day in range(days):
        for _, recipe in selected_recipes.iterrows():
            recipe_vars[(day, recipe['id'])] = model.NewIntVar(0, 1, f'recipe_{day}_{recipe["id"]}')

    # Set the calorie bounds
    lower_calorie_bound = int(targets['calories_per_day']) - 100
    upper_calorie_bound = int(targets['calories_per_day']) + 100

    # Add constraints for each day to meet calorie and macronutrient targets
    for day in range(days):
        # Calorie constraints for the day
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['energy_kcal']) for _, r in selected_recipes.iterrows()) >= lower_calorie_bound
        )
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['energy_kcal']) for _, r in selected_recipes.iterrows()) <= upper_calorie_bound
        )
        
        # Macronutrient constraints for the day
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['carbs']) for _, r in selected_recipes.iterrows()) <= targets['carbs']
        )
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['total_fats']) for _, r in selected_recipes.iterrows()) <= targets['fats']
        )
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['protein']) for _, r in selected_recipes.iterrows()) <= targets['protein']
        )
        
        # Ensure each meal type has at least one recipe per day
        model.Add(
            sum(recipe_vars[(day, r['id'])] for _, r in selected_recipes.iterrows()) == len(meal_types)
        ) if not allow_multiple_dishes else model.Add(
            sum(recipe_vars[(day, r['id'])] for _, r in selected_recipes.iterrows()) >= len(meal_types)
        )

    # Add constraints to ensure unique dishes across all days
    for _, recipe in selected_recipes.iterrows():
        model.Add(
            sum(recipe_vars[(day, recipe['id'])] for day in range(days)) <= 1
        )

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        weekly_plan = []
        for day in range(days):
            daily_plan = [{"recipe_id": r['id'], "amount": 1} for _, r in selected_recipes.iterrows() if solver.Value(recipe_vars[(day, r['id'])]) == 1]
            weekly_plan.append(daily_plan)
        return weekly_plan
    elif not allow_multiple_dishes:
        print("Single-dish meal plan infeasible; attempting multi-dish plan.")
        return generate_meal_plan(selected_recipes, targets, days, meal_types, allow_multiple_dishes=True)
    else:
        print("No feasible meal plan found.")
        return None

def structure_output(weekly_plan, user_preferences):
    if not weekly_plan:
        print("No feasible meal plan found.")
        return

    # Map meal type numbers back to their names
    meal_type_names = {
        1: "BREAKFAST",
        2: "LUNCH",
        3: "DINNER",
        4: "MID_MORNING_SNACK",
        5: "AFTERNOON_SNACK"
    }
    
    print("\nYour Weekly Meal Plan:\n")
    for day_num, meal_plan in enumerate(weekly_plan, start=1):
        print(f"Day {day_num}'s Meal Plan (Target: {user_preferences['calories_per_day']} ± 100 calories):")
        daily_calories = 0

        # Group recipes by meal type for structured output
        meal_groups = {meal_type: [] for meal_type in user_preferences['meal_types']}
        
        # Cycle through meal types correctly for each meal in the plan
        for recipe_index, recipe in enumerate(meal_plan):
            recipe_id = recipe['recipe_id']
            recipe_data = recipe_df[recipe_df['id'] == recipe_id].iloc[0]
            calories = recipe_data['energy_kcal'] * recipe['amount']
            daily_calories += calories
            
            # Use the modulo operator to assign recipes to meal types in order
            meal_type = user_preferences['meal_types'][recipe_index % len(user_preferences['meal_types'])]
            meal_groups[meal_type].append((recipe_data, calories))

        # Calculate deviation from target calories
        deviation = abs(daily_calories - user_preferences['calories_per_day'])
        
        # Display meals grouped by meal type
        for meal_type in user_preferences['meal_types']:
            meal_type_name = meal_type_names[meal_type]
            print(f"\n{meal_type_name}:")
            for recipe_data, calories in meal_groups[meal_type]:
                print(f"- {recipe_data['name']} | Calories: {calories}")
        
        print(f"\nTotal Calories for Day {day_num}: {daily_calories} (Target: {user_preferences['calories_per_day']})")
        print(f"Deviation from Target: {deviation} calories\n")

user_preferences = get_user_preferences()
selected_recipes = query_food_database(user_preferences["meal_types"], user_preferences["intolerances"])
targets = calculate_macronutrient_targets(user_preferences["calories_per_day"], user_preferences["carbs_ratio"], user_preferences["fats_ratio"], user_preferences["protein_ratio"])
weekly_plan = generate_meal_plan(selected_recipes, targets, user_preferences["days"], user_preferences["meal_types"])
structure_output(weekly_plan, user_preferences)
