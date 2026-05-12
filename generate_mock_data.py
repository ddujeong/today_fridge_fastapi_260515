import datetime
import random

now = datetime.datetime.now()
sql_statements = [
    "-- Delete existing mock data to prevent duplicates if run multiple times",
    "DELETE FROM today_fridge.meal WHERE user_id = 1;",
    "DELETE FROM today_fridge.day_nutrition WHERE user_id = 1;",
    ""
]

# Generate day_nutrition for the last 30 days
sql_statements.append("-- 30 Days of Daily Nutrition Summaries")
for i in range(30):
    date = now - datetime.timedelta(days=i)
    # realistic values for a healthy adult
    cals = random.uniform(1900, 2400)
    carbs = random.uniform(220, 300)
    protein = random.uniform(70, 110)
    fat = random.uniform(55, 85)
    sugar = random.uniform(25, 45)
    sodium = random.uniform(1800, 2400)
    chol = random.uniform(150, 250)
    
    stmt = f"INSERT INTO today_fridge.day_nutrition (user_id, date, total_calories, total_carbs, total_protein, total_fat, total_sugar, total_sodium, total_cholesterol) VALUES (1, '{date.strftime('%Y-%m-%d %H:%M:%S')}', {cals:.2f}, {carbs:.2f}, {protein:.2f}, {fat:.2f}, {sugar:.2f}, {sodium:.2f}, {chol:.2f});"
    sql_statements.append(stmt)

sql_statements.append("")

# Generate meals for the last 30 days
# Using valid recipe_ids found in previous AI responses
valid_recipe_ids = [3962, 3024, 1834, 1835, 1838, 3967, 1841, 1842, 1843, 1844, 1845, 1847, 1848, 1849, 1852, 1854, 1856, 1857, 1858, 1861] 

sql_statements.append("-- 30 Days of Individual Meal Records (3 meals a day)")
for i in range(30):
    date = now - datetime.timedelta(days=i)
    
    # Breakfast (around 8 AM)
    recipe_id = random.choice(valid_recipe_ids)
    consumed_at = date.replace(hour=random.randint(7, 9), minute=random.randint(0, 59))
    stmt = f"INSERT INTO today_fridge.meal (user_id, recipe_nutrition_id, servings, consumed_at, created_at) VALUES (1, {recipe_id}, 1.00, '{consumed_at.strftime('%Y-%m-%d %H:%M:%S')}', '{consumed_at.strftime('%Y-%m-%d %H:%M:%S')}');"
    sql_statements.append(stmt)
    
    # Lunch (around 1 PM)
    recipe_id = random.choice(valid_recipe_ids)
    consumed_at = date.replace(hour=random.randint(12, 14), minute=random.randint(0, 59))
    stmt = f"INSERT INTO today_fridge.meal (user_id, recipe_nutrition_id, servings, consumed_at, created_at) VALUES (1, {recipe_id}, 1.00, '{consumed_at.strftime('%Y-%m-%d %H:%M:%S')}', '{consumed_at.strftime('%Y-%m-%d %H:%M:%S')}');"
    sql_statements.append(stmt)
    
    # Dinner (around 7 PM)
    recipe_id = random.choice(valid_recipe_ids)
    consumed_at = date.replace(hour=random.randint(18, 20), minute=random.randint(0, 59))
    stmt = f"INSERT INTO today_fridge.meal (user_id, recipe_nutrition_id, servings, consumed_at, created_at) VALUES (1, {recipe_id}, 1.00, '{consumed_at.strftime('%Y-%m-%d %H:%M:%S')}', '{consumed_at.strftime('%Y-%m-%d %H:%M:%S')}');"
    sql_statements.append(stmt)

with open("test_meal_data.sql", "w", encoding="utf-8") as f:
    f.write("\n".join(sql_statements))
    
print("Successfully generated test_meal_data.sql")
