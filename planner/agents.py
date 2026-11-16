"""Planning steps for the local demo. No LLM or paid API is required.

Body-composition figures use published population formulas. Recipe grams,
nutrition, and store prices are sample data, not verified grocery or diet advice.
Recipe finding and workout planning are local stand-ins until those agents are connected.
"""
import copy
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'data'
RECIPES = json.loads((DATA / 'recipes.json').read_text())
PRICES = json.loads((DATA / 'prices.json').read_text())
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
LB_PER_KG = 2.2046226218
CM_PER_IN = 2.54

# Mifflin–St Jeor activity multipliers, in the order shown on the results table.
ACTIVITIES = [
    ('bmr', 'Basal Metabolic Rate', 1),
    ('sedentary', 'Sedentary', 1.2),
    ('light', 'Light Exercise', 1.375),
    ('moderate', 'Moderate Exercise', 1.55),
    ('heavy', 'Heavy Exercise', 1.725),
    ('athlete', 'Athlete', 1.9),
]
SELECTABLE_ACTIVITIES = {'sedentary', 'light', 'moderate', 'heavy', 'athlete'}

# Protein / fat / carbohydrate percent. 30/35/35 means 30% protein, 35% fat, 35% carbs.
MACRO_SPLITS = [
    ('moderate', 'Moderate Carb', 30, 35, 35),
    ('lower', 'Lower Carb', 40, 40, 20),
    ('higher', 'Higher Carb', 30, 20, 50),
]
GOALS = [
    ('maintenance', 'Maintenance', 1),
    ('cutting', 'Cutting', 0.8),
    ('bulking', 'Bulking', 1.1),
]

LIMITATIONS = [
    'Calorie, ideal-weight, and BMI figures are population formulas, not a medical assessment.',
    'Sample recipes, allergens, and store prices are illustrative.',
    'Recipe portions are fixed, so a day can miss the calorie target. The gap is shown on each day.',
    'Best prices are the lowest sample store for each ingredient, not a live store feed.',
    'Workout templates are a starting point, not a personalized program.',
]


def _number(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError(f'Enter {label}.')
    if isinstance(value, str):
        value = value.strip()
        try:
            value = float(value)
        except ValueError:
            raise ValueError(f'Enter {label} as a number.') from None
    if not isinstance(value, (int, float)):
        raise ValueError(f'Enter {label} as a number.')
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError(f'Enter {label} as a number.')
    return float(value)


def _whole(value, label, low, high):
    number = _number(value, label)
    if abs(number - round(number)) > 1e-9:
        raise ValueError(f'{label} must be a whole number.')
    number = int(round(number))
    if not low <= number <= high:
        raise ValueError(f'{label} must be between {low} and {high}.')
    return number


def _trim(value, places):
    text = f'{value:.{places}f}'
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text


def _display_weight(kg, units):
    if units == 'imperial':
        return int(round(kg * LB_PER_KG))
    return float(f'{kg:.1f}')


def _ideal_formula_kg(gender, height_cm):
    over = height_cm / CM_PER_IN - 60
    if gender == 'male':
        return [
            ('G.J. Hamwi Formula (1964)', 48.0 + 2.7 * over),
            ('B.J. Devine Formula (1974)', 50.0 + 2.3 * over),
            ('J.D. Robinson Formula (1983)', 52.0 + 1.9 * over),
            ('D.R. Miller Formula (1983)', 56.2 + 1.41 * over),
        ]
    return [
        ('G.J. Hamwi Formula (1964)', 45.5 + 2.2 * over),
        ('B.J. Devine Formula (1974)', 45.5 + 2.3 * over),
        ('J.D. Robinson Formula (1983)', 49.0 + 1.7 * over),
        ('D.R. Miller Formula (1983)', 53.1 + 1.36 * over),
    ]


def _macros(calories):
    splits = []
    for split_id, name, protein, fat, carbs in MACRO_SPLITS:
        splits.append({
            'id': split_id,
            'name': name,
            'protein_pct': protein,
            'fat_pct': fat,
            'carb_pct': carbs,
            'protein_g': int(round(calories * (protein / 100) / 4)),
            'fat_g': int(round(calories * (fat / 100) / 9)),
            'carbs_g': int(round(calories * (carbs / 100) / 4)),
        })
    return splits


def _bmi_band(score):
    bands = [
        ('Below 18.5', 'Underweight', score < 18.5),
        ('18.5 – 24.9', 'Normal Weight', 18.5 <= score < 25),
        ('25 – 29.9', 'Overweight', 25 <= score < 30),
        ('30+', 'Obese', score >= 30),
    ]
    category = next(name for _label, name, selected in bands if selected)
    return category, [
        {'label': label, 'category': name, 'selected': selected}
        for label, name, selected in bands
    ]


def assess(raw):
    """Mifflin–St Jeor maintenance calories, ideal weight, BMI, and macros."""
    if not isinstance(raw, dict):
        raise ValueError('Enter your stats first.')
    if isinstance(raw.get('body'), dict):
        raw = raw['body']
    units = raw.get('units')
    if isinstance(units, str):
        units = units.strip().lower()
    if units not in ('metric', 'imperial'):
        raise ValueError('Choose metric or imperial.')
    gender = raw.get('gender')
    if isinstance(gender, str):
        gender = gender.strip().lower()
    if gender not in ('male', 'female'):
        raise ValueError('Choose male or female.')
    age = _whole(raw.get('age'), 'Age', 16, 80)
    activity = raw.get('activity', 'light')
    if isinstance(activity, str):
        activity = activity.strip().lower()
    if activity not in SELECTABLE_ACTIVITIES:
        raise ValueError('Choose sedentary, light, moderate, heavy, or athlete.')

    if units == 'metric':
        weight_kg = _number(raw.get('weight_kg', raw.get('weight')), 'weight')
        height_cm = _number(raw.get('height_cm', raw.get('height')), 'height')
        if not 35 <= weight_kg <= 250:
            raise ValueError('Weight must be between 35 and 250 kg.')
        if not 140 <= height_cm <= 220:
            raise ValueError('Height must be between 140 and 220 cm.')
        weight_label = f'{_trim(weight_kg, 1)} kg'
        height_label = f'{_trim(height_cm, 1)} cm'
    else:
        weight_lb = _number(raw.get('weight_lb', raw.get('weight')), 'weight')
        feet = _whole(raw.get('height_ft'), 'Feet', 4, 7)
        inches = _whole(raw.get('height_in', 0), 'Inches', 0, 11)
        total_inches = feet * 12 + inches
        if not 55 <= total_inches <= 87:
            raise ValueError('Height must be between 4 ft 7 in and 7 ft 3 in.')
        if not 80 <= weight_lb <= 550:
            raise ValueError('Weight must be between 80 and 550 lbs.')
        weight_kg = weight_lb / LB_PER_KG
        height_cm = total_inches * CM_PER_IN
        weight_label = f'{_trim(weight_lb, 1)} lbs'
        height_label = f'{feet} ft {inches} in'

    bmr_exact = 10 * weight_kg + 6.25 * height_cm - 5 * age
    bmr_exact += 5 if gender == 'male' else -161
    bmr = int(round(bmr_exact))
    levels = []
    for activity_id, label, multiplier in ACTIVITIES:
        levels.append({
            'id': activity_id,
            'label': label,
            'multiplier': multiplier,
            'calories': int(round(bmr * multiplier)),
            'selected': activity_id == activity,
        })
    selected = next(level for level in levels if level['selected'])
    maintenance = selected['calories']
    unit = 'lbs' if units == 'imperial' else 'kg'
    formulas = []
    displayed = []
    for name, kg in _ideal_formula_kg(gender, height_cm):
        value = _display_weight(kg, units)
        formulas.append({'name': name, 'kg': float(f'{kg:.2f}'), 'display': value})
        displayed.append(value)
    # Berkhan's simplified height estimate: kilograms at 5% body fat are
    # height in centimeters minus 100. 10% and 15% scale that weight by 1.05 and 1.10.
    base_kg = height_cm - 100
    muscular = {
        'at_5': _display_weight(base_kg, units),
        'at_10': _display_weight(base_kg * 1.05, units),
        'at_15': _display_weight(base_kg * 1.1, units),
        'unit': unit,
    }
    bmi_exact = weight_kg / (height_cm / 100) ** 2
    bmi_score = float(f'{bmi_exact:.1f}')
    category, bands = _bmi_band(bmi_score)
    goals = []
    for goal_id, label, factor in GOALS:
        calories = int(round(maintenance * factor))
        goals.append({
            'id': goal_id,
            'label': label,
            'calories': calories,
            'factor': factor,
            'splits': _macros(calories),
        })
    return {
        'units': units,
        'gender': gender,
        'gender_label': 'Male' if gender == 'male' else 'Female',
        'age': age,
        'activity': activity,
        'activity_label': selected['label'],
        'weight_kg': weight_kg,
        'height_cm': height_cm,
        'weight_label': weight_label,
        'height_label': height_label,
        'bmr': bmr,
        'levels': levels,
        'maintenance': {'daily': maintenance, 'weekly': maintenance * 7},
        'goals': goals,
        'ideal_weight': {
            'low': min(displayed),
            'high': max(displayed),
            'unit': unit,
            'formulas': formulas,
        },
        'bmi': {'score': bmi_score, 'category': category, 'bands': bands},
        'muscular_potential': muscular,
    }


def validate_profile(raw):
    if not isinstance(raw, dict):
        raise ValueError('Profile must be an object.')
    profile = {}
    for key, default, low, high in [('daily_calories', 2000, 500, 9000), ('weekly_budget', 80, 1, 10000)]:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
        profile[key] = value
    profile['diet'] = raw.get('diet', 'any')
    if profile['diet'] not in ['any', 'vegetarian', 'vegan']:
        raise ValueError('Choose any, vegetarian, or vegan.')
    profile['equipment'] = raw.get('equipment', 'home')
    if profile['equipment'] not in ['home', 'gym']:
        raise ValueError('Equipment must be home or gym.')
    profile['goal'] = raw.get('goal', 'maintenance')
    if profile['goal'] not in ('maintenance', 'cutting', 'bulking'):
        raise ValueError('Goal must be maintenance, cutting, or bulking.')
    profile['macro_split'] = raw.get('macro_split', 'moderate')
    if profile['macro_split'] not in ('moderate', 'lower', 'higher'):
        raise ValueError('Choose a macronutrient split.')
    for key in ['allergens', 'workout_days']:
        value = raw.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f'{key} must be a list of strings.')
        profile[key] = list(dict.fromkeys(value))
    if any(day not in DAYS for day in profile['workout_days']):
        raise ValueError('Workout days must be weekday names.')
    if len(profile['workout_days']) > 4:
        raise ValueError('Choose up to four workout days.')
    known = {'milk', 'egg', 'wheat', 'peanut', 'soy'}
    if set(profile['allergens']) - known:
        raise ValueError('Supported demo allergens: milk, egg, wheat, peanut, soy.')
    return profile


def attach_totals(plan):
    plan['daily_totals'] = {}
    for day in DAYS:
        items = [meal['recipe'] for meal in plan['meals'] if meal['day'] == day]
        totals = {key: sum(recipe[key] for recipe in items) for key in ['calories', 'protein_g', 'carbs_g', 'fat_g']}
        totals['target_calories'] = plan['targets'][day]['calories']
        totals['difference_calories'] = totals['calories'] - totals['target_calories']
        plan['daily_totals'][day] = totals
    return plan


class NutritionPlanner:
    def assess(self, raw):
        return assess(raw)

    def run(self, profile):
        # The assessed calorie target stays the same on rest and training days.
        return {
            day: {'calories': profile['daily_calories'], 'training_day': day in profile['workout_days']}
            for day in DAYS
        }


class RecipeFinder:
    def eligible(self, profile, slot, rejected):
        return [recipe for recipe in RECIPES
                if recipe['slot'] == slot
                and (profile['diet'] == 'any' or profile['diet'] in recipe['diets'])
                and not set(recipe['allergens']).intersection(profile['allergens'])
                and recipe['id'] not in rejected]

    def run(self, profile, targets, rejected):
        meals = []
        fractions = {'breakfast': .25, 'lunch': .35, 'dinner': .40}
        for day in DAYS:
            for slot, fraction in fractions.items():
                candidates = self.eligible(profile, slot, rejected)
                if not candidates:
                    raise ValueError(f'No {slot} recipes match these restrictions. Add more recipes or review preferences.')
                ranked = sorted(candidates, key=lambda recipe: abs(recipe['calories'] - targets[day]['calories'] * fraction))
                # Alternate between the two closest recipes to provide basic variety.
                recipe = ranked[DAYS.index(day) % min(2, len(ranked))]
                meals.append({'day': day, 'slot': slot, 'recipe': copy.deepcopy(recipe)})
        return meals


class GroceryConsolidator:
    def run(self, meals):
        totals = {}
        for meal in meals:
            for ingredient, grams in meal['recipe']['ingredients_g'].items():
                totals[ingredient] = totals.get(ingredient, 0) + grams
        return [{'ingredient': name, 'grams': grams} for name, grams in sorted(totals.items())]


class PriceFinder:
    """Pick the lowest sample-store price for each grocery item."""

    def run(self, groceries):
        items = []
        store_costs = {}
        for entry in groceries:
            name = entry['ingredient']
            grams = entry['grams']
            raw_offers = PRICES.get(name)
            if not isinstance(raw_offers, list) or not raw_offers:
                raise ValueError(f'No sample price for {name}.')
            offers = []
            for raw in raw_offers:
                cost = round(grams * raw['usd_per_g'], 2)
                offers.append({'store': raw['store'], 'usd_per_g': raw['usd_per_g'], 'estimated_cost': cost})
            offers.sort(key=lambda offer: (offer['estimated_cost'], offer['store']))
            best = offers[0]
            for offer in offers:
                offer['best'] = offer is best
                store_costs[offer['store']] = round(store_costs.get(offer['store'], 0) + offer['estimated_cost'], 2)
            items.append({
                'ingredient': name,
                'grams': grams,
                'best_store': best['store'],
                'estimated_cost': best['estimated_cost'],
                'offers': offers,
            })
        one_stop = [
            {'store': store, 'estimated_cost': cost}
            for store, cost in sorted(store_costs.items(), key=lambda item: (item[1], item[0]))
        ]
        return {
            'items': items,
            'cherry_pick_total': round(sum(item['estimated_cost'] for item in items), 2),
            'one_stop': one_stop,
        }


class BudgetOptimizer:
    def run(self, profile, groceries, meals):
        total = round(sum(item['estimated_cost'] for item in groceries), 2)
        suggestions = []
        if total > profile['weekly_budget']:
            suggestions.append('This list is over the weekly budget at the best prices. Raise the budget or veto a meal and price the list again.')
        # Report feasibility honestly; never silently replace approved meals.
        return {
            'estimated_total': total,
            'budget': profile['weekly_budget'],
            'within_budget': total <= profile['weekly_budget'],
            'suggestions': suggestions,
        }


class WorkoutPlanner:
    def run(self, profile):
        home = ['Chair squat', 'Wall push-up', 'Glute bridge', 'Bird dog']
        gym = ['Goblet squat', 'Chest press machine', 'Seated row', 'Bird dog']
        return [{
            'day': day,
            'type': 'Introductory full-body template',
            'exercises': home if profile['equipment'] == 'home' else gym,
            'notes': 'Demo template: choose a comfortable effort, leave a rest day between sessions, and adapt it with a qualified trainer.',
        } for day in profile['workout_days']]


def plan_recipes(raw_profile, rejected=None, assessment=None):
    profile = validate_profile(raw_profile)
    rejected = list(rejected or [])
    if any(not isinstance(item, str) for item in rejected):
        raise ValueError('Rejected recipes must be ids.')
    targets = NutritionPlanner().run(profile)
    plan = {
        'profile': profile,
        'assessment': assessment,
        'targets': targets,
        'meals': RecipeFinder().run(profile, targets, rejected),
        'workouts': [],
        'rejected_recipe_ids': rejected,
        'groceries': None,
        'budget': None,
        'prices': None,
        'stage': 'recipes',
        'limitations': LIMITATIONS,
    }
    return attach_totals(plan)


def attach_prices(plan):
    prices = PriceFinder().run(GroceryConsolidator().run(plan['meals']))
    plan['prices'] = prices
    plan['groceries'] = [{
        'ingredient': item['ingredient'],
        'grams': item['grams'],
        'estimated_cost': item['estimated_cost'],
    } for item in prices['items']]
    plan['budget'] = BudgetOptimizer().run(plan['profile'], plan['groceries'], plan['meals'])
    plan['stage'] = 'prices'
    return plan


def find_prices(plan):
    if not plan.get('meals'):
        raise ValueError('Find recipes before pricing groceries.')
    return attach_prices(copy.deepcopy(plan))


def plan_workouts(plan, equipment, workout_days):
    if not plan.get('prices'):
        raise ValueError('Find grocery prices before planning workouts.')
    updated = copy.deepcopy(plan)
    raw = dict(updated['profile'])
    raw['equipment'] = equipment
    raw['workout_days'] = workout_days
    updated['profile'] = validate_profile(raw)
    updated['targets'] = NutritionPlanner().run(updated['profile'])
    updated['workouts'] = WorkoutPlanner().run(updated['profile'])
    attach_totals(updated)
    updated['stage'] = 'workouts'
    return updated


def generate(raw_profile, rejected=None):
    plan = plan_recipes(raw_profile, rejected)
    plan = find_prices(plan)
    return plan_workouts(plan, plan['profile']['equipment'], plan['profile']['workout_days'])


def pick_recipe(profile, slot, rejected, day, calories):
    candidates = RecipeFinder().eligible(profile, slot, rejected)
    if not candidates:
        raise ValueError('No replacement remains. Reset preferences or add recipes.')
    fraction = {'breakfast': .25, 'lunch': .35, 'dinner': .40}[slot]
    ranked = sorted(candidates, key=lambda recipe: abs(recipe['calories'] - calories * fraction))
    # Same variety rule as the first pass: alternate the two closest matches.
    return ranked[DAYS.index(day) % min(2, len(ranked))]


def replace_meal(plan, day, slot):
    # Copy first so an unavailable replacement never damages the existing plan.
    updated = copy.deepcopy(plan)
    origin = next((item for item in updated['meals'] if item['day'] == day and item['slot'] == slot), None)
    if origin is None:
        raise ValueError('Meal slot not found.')
    vetoed_id = origin['recipe']['id']
    rejected = list(dict.fromkeys(updated['rejected_recipe_ids'] + [vetoed_id]))
    swaps = [meal for meal in updated['meals'] if meal['recipe']['id'] == vetoed_id]
    choices = [
        pick_recipe(
            updated['profile'], meal['slot'], rejected, meal['day'],
            updated['targets'][meal['day']]['calories'],
        )
        for meal in swaps
    ]
    for meal, recipe in zip(swaps, choices):
        meal['recipe'] = copy.deepcopy(recipe)
    updated['rejected_recipe_ids'] = rejected
    attach_totals(updated)
    if updated.get('prices') is not None:
        attach_prices(updated)
    return updated
