import copy
import unittest
from planner.agents import (
    CM_PER_IN, LB_PER_KG, PRICES, GroceryConsolidator, PriceFinder,
    assess, find_prices, generate, plan_recipes, plan_workouts, replace_meal,
)


def imperial_male():
    return {
        'units': 'imperial',
        'gender': 'male',
        'age': 28,
        'activity': 'light',
        'weight_lb': 155,
        'height_ft': 5,
        'height_in': 8,
    }


class PlannerTests(unittest.TestCase):
    def test_groceries_and_budget(self):
        plan = generate({})
        self.assertEqual(len(plan['meals']), 21)
        self.assertAlmostEqual(plan['budget']['estimated_total'], sum(item['estimated_cost'] for item in plan['groceries']))
        for item in plan['groceries']:
            self.assertEqual(item['grams'], sum(meal['recipe']['ingredients_g'].get(item['ingredient'], 0) for meal in plan['meals']))

    def test_veto_removes_recipe_from_every_day(self):
        plan = generate({})
        monday = next(meal for meal in plan['meals'] if meal['day'] == 'Monday' and meal['slot'] == 'breakfast')
        tuesday = next(meal for meal in plan['meals'] if meal['day'] == 'Tuesday' and meal['slot'] == 'breakfast')
        tuesday['recipe'] = copy.deepcopy(monday['recipe'])
        recipe_id = monday['recipe']['id']
        updated = replace_meal(plan, 'Monday', 'breakfast')
        self.assertNotIn(recipe_id, [meal['recipe']['id'] for meal in updated['meals']])
        self.assertIn(recipe_id, updated['rejected_recipe_ids'])
        monday_after = next(meal for meal in updated['meals'] if meal['day'] == 'Monday' and meal['slot'] == 'breakfast')
        tuesday_after = next(meal for meal in updated['meals'] if meal['day'] == 'Tuesday' and meal['slot'] == 'breakfast')
        self.assertNotEqual(monday_after['recipe']['id'], tuesday_after['recipe']['id'])
        for before, after in zip(plan['meals'], updated['meals']):
            self.assertEqual((before['day'], before['slot']), (after['day'], after['slot']))
            if before['recipe']['id'] == recipe_id:
                self.assertNotEqual(after['recipe']['id'], recipe_id)
            else:
                self.assertEqual(before['recipe'], after['recipe'])

    def test_constraints(self):
        plan = generate({'diet': 'vegan', 'allergens': ['soy'], 'weekly_budget': 1})
        self.assertTrue(all('vegan' in meal['recipe']['diets'] and 'soy' not in meal['recipe']['allergens'] for meal in plan['meals']))
        self.assertFalse(plan['budget']['within_budget'])
        with self.assertRaises(ValueError):
            generate({'diet': 'vegan', 'allergens': ['soy', 'wheat', 'peanut']})

    def test_schedule_and_validation(self):
        plan = generate({'workout_days': ['Monday', 'Wednesday', 'Friday']})
        self.assertEqual(len(plan['workouts']), 3)
        self.assertTrue(plan['targets']['Monday']['training_day'])
        self.assertFalse(plan['targets']['Tuesday']['training_day'])
        with self.assertRaises(ValueError):
            generate({'workout_days': ['Someday']})

    def test_ideal_weight_and_muscular_potential(self):
        result = assess(imperial_male())
        by_name = {formula['name']: formula['display'] for formula in result['ideal_weight']['formulas']}
        self.assertEqual(by_name['G.J. Hamwi Formula (1964)'], 153)
        self.assertEqual(by_name['B.J. Devine Formula (1974)'], 151)
        self.assertEqual(by_name['J.D. Robinson Formula (1983)'], 148)
        self.assertEqual(by_name['D.R. Miller Formula (1983)'], 149)
        self.assertEqual(result['ideal_weight']['low'], 148)
        self.assertEqual(result['ideal_weight']['high'], 153)
        self.assertEqual(result['ideal_weight']['unit'], 'lbs')
        self.assertEqual(result['muscular_potential']['at_5'], 160)
        self.assertEqual(result['muscular_potential']['at_10'], 168)
        self.assertEqual(result['muscular_potential']['at_15'], 176)

    def test_female_ideal_weight(self):
        result = assess({
            'units': 'imperial',
            'gender': 'female',
            'age': 28,
            'activity': 'moderate',
            'weight_lb': 130,
            'height_ft': 5,
            'height_in': 4,
        })
        by_name = {formula['name']: formula['display'] for formula in result['ideal_weight']['formulas']}
        self.assertEqual(by_name['G.J. Hamwi Formula (1964)'], 120)
        self.assertEqual(by_name['B.J. Devine Formula (1974)'], 121)
        self.assertEqual(by_name['J.D. Robinson Formula (1983)'], 123)
        self.assertEqual(by_name['D.R. Miller Formula (1983)'], 129)
        self.assertEqual(result['ideal_weight']['low'], 120)
        self.assertEqual(result['ideal_weight']['high'], 129)
        self.assertTrue(next(level['selected'] for level in result['levels'] if level['id'] == 'moderate'))

    def test_mifflin_activity_and_macros(self):
        result = assess(imperial_male())
        weight_kg = 155 / LB_PER_KG
        height_cm = 68 * CM_PER_IN
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * 28 + 5
        self.assertEqual(result['bmr'], round(bmr))
        by_id = {level['id']: level for level in result['levels']}
        self.assertTrue(by_id['light']['selected'])
        self.assertFalse(by_id['sedentary']['selected'])
        self.assertEqual(by_id['light']['calories'], round(result['bmr'] * 1.375))
        self.assertEqual(result['maintenance']['daily'], by_id['light']['calories'])
        self.assertEqual(result['maintenance']['weekly'], by_id['light']['calories'] * 7)
        self.assertEqual(result['bmi']['score'], float(f'{weight_kg / (height_cm / 100) ** 2:.1f}'))
        self.assertEqual(result['bmi']['category'], 'Normal Weight')
        maintenance = next(goal for goal in result['goals'] if goal['id'] == 'maintenance')
        cutting = next(goal for goal in result['goals'] if goal['id'] == 'cutting')
        bulking = next(goal for goal in result['goals'] if goal['id'] == 'bulking')
        self.assertEqual(maintenance['calories'], result['maintenance']['daily'])
        self.assertEqual(cutting['calories'], round(maintenance['calories'] * 0.8))
        self.assertEqual(bulking['calories'], round(maintenance['calories'] * 1.1))
        moderate = next(split for split in maintenance['splits'] if split['id'] == 'moderate')
        self.assertEqual(moderate['protein_g'], round(maintenance['calories'] * 0.30 / 4))
        self.assertEqual(moderate['fat_g'], round(maintenance['calories'] * 0.35 / 9))
        self.assertEqual(moderate['carbs_g'], round(maintenance['calories'] * 0.35 / 4))

    def test_metric_matches_imperial(self):
        imperial = assess(imperial_male())
        metric = assess({
            'units': 'metric',
            'gender': 'male',
            'age': 28,
            'activity': 'light',
            'weight_kg': 155 / LB_PER_KG,
            'height_cm': 68 * CM_PER_IN,
        })
        self.assertEqual(imperial['bmr'], metric['bmr'])
        self.assertEqual(imperial['maintenance'], metric['maintenance'])
        self.assertEqual(imperial['bmi']['score'], metric['bmi']['score'])
        self.assertEqual(metric['ideal_weight']['unit'], 'kg')
        hamwi = next(formula for formula in metric['ideal_weight']['formulas'] if formula['name'].startswith('G.J. Hamwi'))
        self.assertEqual(hamwi['display'], 69.6)

    def test_rejects_bad_body(self):
        with self.assertRaises(ValueError):
            assess({'units': 'stones', 'gender': 'male', 'age': 30, 'activity': 'light'})
        with self.assertRaises(ValueError):
            assess({'units': 'imperial', 'gender': 'male', 'age': 12, 'activity': 'light', 'weight_lb': 155, 'height_ft': 5, 'height_in': 8})

    def test_price_finder_picks_lowest_offer(self):
        meals = [{'recipe': {'ingredients_g': {'oats': 250, 'chicken': 180}}}]
        priced = PriceFinder().run(GroceryConsolidator().run(meals))
        oats = next(item for item in priced['items'] if item['ingredient'] == 'oats')
        expected = min(PRICES['oats'], key=lambda offer: (offer['usd_per_g'], offer['store']))
        self.assertEqual(oats['best_store'], expected['store'])
        self.assertEqual(oats['estimated_cost'], round(250 * expected['usd_per_g'], 2))
        self.assertLessEqual(priced['cherry_pick_total'], min(store['estimated_cost'] for store in priced['one_stop']))

    def test_recipe_price_and_workout_steps(self):
        result = assess(imperial_male())
        maintenance = next(goal for goal in result['goals'] if goal['id'] == 'maintenance')
        plan = plan_recipes({
            'daily_calories': maintenance['calories'],
            'weekly_budget': 80,
            'goal': 'maintenance',
        }, assessment=result)
        self.assertIsNone(plan['prices'])
        self.assertEqual(plan['workouts'], [])
        with self.assertRaises(ValueError):
            plan_workouts(plan, 'home', ['Monday'])
        priced = find_prices(plan)
        self.assertIsNone(plan['prices'])
        self.assertTrue(priced['prices']['items'])
        for item in priced['prices']['items']:
            self.assertEqual(item['estimated_cost'], min(offer['estimated_cost'] for offer in item['offers']))
        scheduled = plan_workouts(priced, 'gym', ['Monday', 'Wednesday'])
        self.assertEqual(len(scheduled['workouts']), 2)
        self.assertEqual(scheduled['workouts'][0]['exercises'][0], 'Goblet squat')
        self.assertTrue(scheduled['targets']['Monday']['training_day'])
        self.assertFalse(priced['targets']['Monday']['training_day'])


if __name__ == '__main__':
    unittest.main()
