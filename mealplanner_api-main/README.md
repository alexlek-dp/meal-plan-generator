Got it. Here's the **entire `README.md`**, clean and complete, all in **one single message** — ready for copy-paste 🚀:

---

````markdown
# 🍽️ MealPlanner API

This project is a Dockerized Flask API that generates weekly meal plans based on your nutritional goals.  
You define your calorie and macro targets (carbs, fats, protein), and it builds a 7-day plan from a recipe dataset.

---

## ✅ Features

- 📅 Generates meal plans for up to 7 days  
- 🍳 Splits each day into 5 meals (breakfast, snack, lunch, dinner, etc.)  
- 📊 Customizable calorie and macro ratio inputs  
- 💾 Saves result to `output/last_week_plan.json`  
- 🐳 Docker-compatible (tested on **Windows 10/11**)

---

## ⚙️ Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows)
- Git (optional, for cloning the repo)

---

## 🚀 Running the API with Docker (on Windows)

### 1️⃣ Clone the repository

```powershell
git clone https://github.com/Zerd00/mealplanner_api.git
cd mealplanner_api
````

### 2️⃣ Build the Docker image

```powershell
docker build -t mealplanner-api .
```

### 3️⃣ Run the Docker container

#### 🔹 Basic run:

```powershell
docker run -d -p 8000:8000 --name mealplanner-api mealplanner-api
```

#### 🔹 Save output to host folder:

```powershell
docker run -p 8000:8000 -v ${PWD}/output:/app/output mealplanner-api
```

---

## 📬 Testing the API (PowerShell)

Use this command to test the API from your terminal:

```powershell
curl -Uri http://localhost:8000/api/generate-meal-plan `
     -Method POST `
     -Headers @{ "Content-Type" = "application/json" } `
     -Body '{"calories": 4000, "carbs": 0.2, "fats": 0.3, "protein": 0.5, "days": 7}'
```

It returns JSON in the terminal and saves the result to:

```
output/last_week_plan.json
```

---

## 📡 API Endpoint Reference

### `POST /api/generate-meal-plan`

**Request JSON:**

```json
{
  "calories": 4000,
  "carbs": 0.2,
  "fats": 0.3,
  "protein": 0.5,
  "days": 7
}
```

**Response fields:**

* `mealPlan`: list of daily meals
* `targets`: expected daily macros
* `dailyTotals`: actual totals per day
* `success`: true/false

---

## 📁 Project Structure

```
mealplanner_api/
├── app.py                  # Main Flask API
├── Dockerfile              # Docker container setup
├── requirements.txt        # Python dependencies
├── data/
│   └── recipe_api.csv      # Dataset of recipes
├── output/
│   └── last_week_plan.json # Generated meal plan (auto-created)
```

---

## 👨‍💻 Author

Made with ❤️ by **Zerd00**
🔗 GitHub: [https://github.com/Zerd00](https://github.com/Zerd00)

---

## 📝 License

MIT License (or any you prefer)

```

---

✅ You're now 100% ready to commit this to GitHub as your official `README.md`.  
If you need help deploying to Render, Fly.io, or want CI/CD (GitHub Actions), just ask.
```
