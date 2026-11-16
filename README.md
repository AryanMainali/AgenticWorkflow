# Weekly Fuel

A dependency-free Python 3.10+ local demo. No API keys, package install, or
internet connection is required. Recipe finding and workout planning are local
stand-ins until those agents are connected.

## Start

1. Open a terminal in this folder.
2. Run `python3 server.py`.
3. Open http://localhost:8000.
4. Stop with Ctrl+C.

If port 8000 is busy, stop the other application first.

## Flow

1. Choose metric or imperial units.
2. Enter age, gender, weight, height, and activity.
3. Review maintenance calories (Mifflin–St Jeor), the other activity levels, an ideal-weight range, BMI, and macros for maintenance, cutting, or bulking.
4. Set a weekly grocery budget. Recipe Finder proposes seven days of meals. Veto a recipe to remove it from every day it appears. Vetoed recipe ids stay out while “remember” is checked.
5. Price Finder compares three sample stores and keeps the lowest price on each ingredient. It also shows the cheapest single-store total.
6. Workout Planner adds a short home or gym template on up to four days.

Preferences and plans live in server memory and disappear on restart. A reload drops the browser session.

## Structure

- `planner/agents.py`: body-stat assessment, NutritionPlanner, RecipeFinder, GroceryConsolidator, PriceFinder, BudgetOptimizer, WorkoutPlanner.
- `data/recipes.json`: nine sample recipes with fixed portions.
- `data/prices.json`: illustrative USD prices per gram at three sample stores.
- `server.py`: local HTTP API and session state.
- `web/index.html`: the six-step page.
- `tests/test_planner.py`: formula, pricing, and workflow checks.

These are deterministic components, not language-model agents. RecipeFinder ranks the sample set and remembers vetoes. PriceFinder picks the lowest listed store price. It does not call a live grocer.

## Tests

Run `python3 -m unittest discover -s tests -v`.

## API

`POST /api/assess`: body stats. `units` is `metric` or `imperial`. `gender` is `male` or `female`. `age` is 16–80. `activity` is `sedentary`, `light`, `moderate`, `heavy`, or `athlete`. Metric uses `weight_kg` and `height_cm`. Imperial uses `weight_lb`, `height_ft`, and `height_in`.

`POST /api/recipes`: `{session_id, remember_preferences, goal, macro_split, weekly_budget, diet, allergens, body}`. `goal` is `maintenance`, `cutting` (20% below maintenance), or `bulking` (10% above). Returns `{session_id, plan}` with meals and no prices yet.

`POST /api/replace`: `{session_id, day, slot}`. Removes that recipe from every day it appears, fills those slots from the remaining matches, and keeps the veto. Reprices the list if prices were already calculated.

`POST /api/prices`: `{session_id}`. Runs Price Finder on the current meals.

`POST /api/workouts`: `{session_id, equipment, workout_days}`. `equipment` is `home` or `gym`. Up to four weekday names. Requires prices first.

## Scope

Sample nutrition and prices are illustrative and are not medical or shopping advice. Ideal weight and BMI are height-and-weight formulas. Workout templates need review and adaptation. Recipe allergens cover only milk, egg, wheat, peanut, and soy, and they do not cover cross-contact. This prototype is for coursework and development, not real dietary or exercise decisions.
