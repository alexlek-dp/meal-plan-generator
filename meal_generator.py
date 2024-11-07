import pandas as pd
from ortools.sat.python import cp_model

# Load your data
# Read data from CSV files to create pandas DataFrames for each required dataset
food_df = pd.read_csv('/kaggle/input/food-data/food_202410152357.csv')
recipe_df = pd.read_csv('/kaggle/input/food-data/recipe_202410162311.csv')
meal_plan_df = pd.read_csv('/kaggle/input/food-data/meal_plan_202410170111.csv')
category_df = pd.read_csv('/kaggle/input/food-data/recipe_categories_202410221917.csv')

# Convert relevant columns to integers for compatibility in operations
recipe_df['id'] = recipe_df['id'].astype(int)
category_df['recipe_id'] = category_df['recipe_id'].astype(int)

# Function to get user preferences for meal planning
def get_user_preferences():
    # Display default values and options for the user
    print("Default Values: \nDaily Calorie Target: 2000\nCarb Percentage: 50%\nFat Percentage: 30%\nProtein Percentage: 20%")
    print("Meal Types: BREAKFAST, LUNCH, DINNER, MID_MORNING_SNACK, AFTERNOON_SNACK")
    print("Days: 7\n")

    # Prompt for calorie target and macronutrient ratios, or use default values if skipped
    calories_per_day = float(input("Enter your daily calorie target (leave blank to skip): ") or 2000)
    carbs_ratio = float(input("Enter your carb percentage (leave blank to skip): ") or 0.5)
    fats_ratio = float(input("Enter your fat percentage (leave blank to skip): ") or 0.3)
    protein_ratio = float(input("Enter your protein percentage (leave blank to skip): ") or 0.2)

    # Define a mapping for meal types to integer values for easy reference later
    meal_type_map = {
        "breakfast": 1,
        "lunch": 2,
        "dinner": 3,
        "mid_morning_snack": 4,
        "afternoon_snack": 5
    }

    # Get user-selected meal types, matching them to the dictionary values
    meal_types_input = input("Enter meal types (comma-separated, e.g., breakfast, lunch, dinner, snack): ")
    meal_types = [meal_type_map.get(meal.strip().lower()) for meal in meal_types_input.split(",") if meal_type_map.get(meal.strip().lower())]

    # If no valid meal types are entered, prompt user to retry
    if not meal_types:
        print("Invalid meal types entered. Please try again.")
        return None

    # Prompt for the duration (one day or weekly plan) and set default meal frequency
    days = int(input("Do you want a one-day or weekly meal plan? (Enter 1 for one day, 7 for weekly, default: 7): ") or 7)
    meal_frequency = int(input("Enter the frequency of meals per day (default: 3): ") or 3)

    # Return all gathered user preferences as a dictionary
    return {
        "calories_per_day": calories_per_day,
        "carbs_ratio": carbs_ratio,
        "fats_ratio": fats_ratio,
        "protein_ratio": protein_ratio,
        "meal_types": meal_types,
        "days": days,
        "meal_frequency": meal_frequency
    }

# Query food database for recipes based on selected meal types
def query_food_database(meal_types):
    # Filter recipes that match the user-selected meal types
    selected_recipes = category_df[category_df['categories'].isin(meal_types)]
    return recipe_df[recipe_df['id'].isin(selected_recipes['recipe_id'])]

# Calculate daily macronutrient targets based on calorie goal and ratios
def calculate_macronutrient_targets(calories_per_day, carbs_ratio, fats_ratio, protein_ratio):
    # Compute macronutrient targets in grams based on calorie intake and nutrient ratios
    carbs_calories = int(calories_per_day * carbs_ratio)
    fats_calories = int(calories_per_day * fats_ratio)
    protein_calories = int(calories_per_day * protein_ratio)

    return {
        "calories_per_day": calories_per_day,
        "carbs": carbs_calories // 4,    # Each gram of carbs provides 4 calories
        "fats": fats_calories // 9,      # Each gram of fat provides 9 calories
        "protein": protein_calories // 4 # Each gram of protein provides 4 calories
    }

# Generate meal plan based on selected recipes, targets, meal frequency, and duration
def generate_meal_plan(selected_recipes, targets, meal_frequency, days):
    # Initialize constraint programming model
    model = cp_model.CpModel()

    # Define decision variables for each day and recipe within the meal frequency range
    recipe_vars = {}
    for day in range(days):
        for _, recipe in selected_recipes.iterrows():
            recipe_vars[(day, recipe['id'])] = model.NewIntVar(0, meal_frequency, f'recipe_{day}_{recipe["id"]}')

    # Define calorie range (±100 calories around the target) to ensure flexibility
    lower_calorie_bound = int(targets['calories_per_day']) - 100
    upper_calorie_bound = int(targets['calories_per_day']) + 100

    # Add constraints for daily calorie and macronutrient intake, and meal frequency
    for day in range(days):
        # Calorie intake constraint for each day
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['energy_kcal']) for _, r in selected_recipes.iterrows()) >= lower_calorie_bound
        )
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['energy_kcal']) for _, r in selected_recipes.iterrows()) <= upper_calorie_bound
        )

        # Macronutrient constraints for each day
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['carbs']) for _, r in selected_recipes.iterrows()) <= targets['carbs']
        )
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['total_fats']) for _, r in selected_recipes.iterrows()) <= targets['fats']
        )
        model.Add(
            sum(recipe_vars[(day, r['id'])] * int(r['protein']) for _, r in selected_recipes.iterrows()) <= targets['protein']
        )

        # Ensure total meals per day meets the desired meal frequency
        model.Add(sum(recipe_vars[(day, r.id)] for r in selected_recipes.itertuples()) == meal_frequency)

    # Objective function: maximize calorie intake close to the target without exceeding limits
    model.Maximize(
        sum(recipe_vars[(day, r['id'])] * int(r['energy_kcal']) for day in range(days) for _, r in selected_recipes.iterrows())
    )

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # Compile a weekly meal plan based on the solution if feasible
    weekly_plan = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        for day in range(days):
            meal_plan = []
            for recipe_id in selected_recipes['id']:
                amount = solver.Value(recipe_vars[(day, recipe_id)])
                if amount > 0:
                    meal_plan.append({
                        'recipe_id': recipe_id,
                        'amount': amount
                    })
            weekly_plan.append(meal_plan)
    else:
        print("No solution found.")
    return weekly_plan

# Display structured meal plan output for each day based on the solution
def structure_output(weekly_plan, user_preferences):
    if not weekly_plan:
        print("No feasible meal plan found.")
        return

    print("\nYour Weekly Meal Plan:\n")
    for day_num, meal_plan in enumerate(weekly_plan, start=1):
        print(f"Day {day_num}'s Meal Plan (Target: {user_preferences['calories_per_day']} ± 100 calories):")
        daily_calories = 0
        for recipe in meal_plan:
            recipe_id = recipe['recipe_id']
            recipe_data = recipe_df[recipe_df['id'] == recipe_id].iloc[0]
            calories = recipe_data['energy_kcal'] * recipe['amount']
            daily_calories += calories
            print(f"  {recipe_data['name']}:")
            print(f"    Calories: {calories}, Carbs: {recipe_data['carbs']}g, Fats: {recipe_data['total_fats']}g, Protein: {recipe_data['protein']}g")
        deviation = daily_calories - user_preferences['calories_per_day']
        print(f"  Total Daily Calories: {daily_calories} (Deviation: {deviation} calories)\n")

# Main function to execute the meal planning process
def main():
    # Retrieve user preferences
    user_preferences = get_user_preferences()
    # Query the database for recipes matching meal types
    selected_recipes = query_food_database(user_preferences['meal_types'])
    # Calculate macronutrient targets based on user preferences
    targets = calculate_macronutrient_targets(user_preferences['calories_per_day'],
                                              user_preferences['carbs_ratio'],
                                              user_preferences['fats_ratio'],
                                              user_preferences['protein_ratio'])
    # Generate the weekly meal plan using constraints and preferences
    weekly_plan = generate_meal_plan(selected_recipes, targets, user_preferences['meal_frequency'], user_preferences['days'])
    # Output the structured meal plan to the user
    structure_output(weekly_plan, user_preferences)

# Entry point of the script
if __name__ == "__main__":
    main()

