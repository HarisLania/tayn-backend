from django.db import migrations

CATEGORIES = [
    (
        "Standard",
        "standard",
        "Balanced meals with moderate calories and macros for everyday nutrition.",
    ),
    (
        "Low Cal",
        "low-cal",
        "Lighter meals designed for calorie-conscious diets and weight loss.",
    ),
    (
        "Weight Gain",
        "weight-gain",
        "Calorie-dense meals designed to support healthy weight gain.",
    ),
    (
        "Protein Power",
        "protein-power",
        "High-protein meals designed to support muscle growth and recovery.",
    ),
]

# name, description, calories, protein_g
MEALS = {
    "standard": {
        "main": [
            ("Grilled Chicken with Rice", "Grilled chicken breast served with steamed white rice and vegetables.", 520, 35),
            ("Beef Stir Fry", "Sliced beef stir-fried with mixed vegetables in a savory sauce.", 560, 32),
            ("Salmon with Quinoa", "Baked salmon fillet with quinoa and steamed greens.", 540, 34),
            ("Turkey Meatballs & Pasta", "Turkey meatballs in tomato sauce over penne pasta.", 580, 30),
            ("Chicken Fajita Bowl", "Grilled chicken, peppers and onions over seasoned rice.", 550, 33),
            ("Herb Roasted Chicken", "Herb-roasted chicken thigh with roasted potatoes.", 590, 31),
            ("Beef and Vegetable Curry", "Slow-cooked beef curry with mixed vegetables and rice.", 600, 30),
            ("Grilled Fish with Vegetables", "Grilled white fish with a medley of roasted vegetables.", 480, 33),
            ("Chicken Caesar Wrap", "Grilled chicken, romaine and parmesan in a soft tortilla wrap.", 510, 29),
            ("Vegetable Lasagna", "Layered pasta with ricotta, mozzarella and seasonal vegetables.", 530, 24),
        ],
        "snack": [
            ("Mixed Nuts", "A handful of almonds, cashews and walnuts.", 200, 7),
            ("Greek Yogurt with Berries", "Plain Greek yogurt topped with mixed berries.", 180, 12),
            ("Hummus with Veggie Sticks", "Carrot and celery sticks served with hummus.", 190, 6),
            ("Cheese and Crackers", "Sliced cheddar cheese with whole grain crackers.", 220, 9),
            ("Fruit Salad", "A mix of seasonal fresh fruits.", 150, 2),
        ],
        "dessert": [
            ("Chocolate Pudding", "Rich and creamy homemade chocolate pudding.", 260, 4),
            ("Fruit Tart", "Buttery pastry shell topped with custard and fresh fruit.", 300, 4),
            ("Vanilla Ice Cream", "Classic creamy vanilla ice cream scoop.", 250, 3),
            ("Apple Crumble", "Baked apples topped with a crisp oat crumble.", 320, 3),
            ("Rice Pudding", "Creamy rice pudding with a hint of cinnamon.", 240, 5),
        ],
    },
    "low-cal": {
        "main": [
            ("Grilled Chicken Salad", "Grilled chicken breast over mixed greens with light vinaigrette.", 320, 30),
            ("Steamed Fish with Broccoli", "Steamed white fish served with steamed broccoli.", 280, 32),
            ("Zucchini Noodles with Turkey", "Zucchini noodles tossed with lean ground turkey and tomato sauce.", 310, 28),
            ("Cauliflower Rice Stir Fry", "Cauliflower rice stir-fried with chicken and vegetables.", 300, 27),
            ("Egg White Omelette", "Fluffy egg white omelette with spinach and tomatoes.", 220, 24),
            ("Grilled Shrimp Salad", "Grilled shrimp over mixed greens with lemon dressing.", 260, 26),
            ("Chicken Lettuce Wraps", "Seasoned ground chicken wrapped in crisp lettuce leaves.", 290, 25),
            ("Baked Cod with Asparagus", "Baked cod fillet served with roasted asparagus.", 270, 30),
            ("Turkey Lettuce Tacos", "Lean turkey taco filling served in lettuce cups.", 300, 27),
            ("Veggie Soup with Chicken", "Light vegetable broth soup with shredded chicken.", 250, 22),
        ],
        "snack": [
            ("Celery with Light Hummus", "Crisp celery sticks with a light hummus dip.", 90, 3),
            ("Cucumber Slices", "Fresh cucumber slices with a sprinkle of salt.", 50, 1),
            ("Air-Popped Popcorn", "Lightly salted air-popped popcorn.", 100, 3),
            ("Rice Cakes", "Two plain rice cakes.", 70, 1),
            ("Boiled Egg", "A single boiled egg.", 78, 6),
        ],
        "dessert": [
            ("Sugar-Free Jello", "Light sugar-free gelatin dessert.", 20, 1),
            ("Frozen Yogurt Bites", "Bite-sized frozen yogurt covered berries.", 120, 3),
            ("Berry Sorbet", "Refreshing sorbet made from mixed berries.", 110, 1),
            ("Low-Cal Chocolate Mousse", "Light chocolate mousse made with skim milk.", 130, 4),
            ("Baked Apple Slices", "Cinnamon-baked apple slices, no added sugar.", 90, 1),
        ],
    },
    "weight-gain": {
        "main": [
            ("Double Beef Burger with Cheese", "Double beef patty burger with melted cheese and a brioche bun.", 850, 42),
            ("Creamy Chicken Alfredo", "Fettuccine pasta in a rich creamy chicken alfredo sauce.", 820, 38),
            ("Loaded Baked Potato with Beef", "Baked potato loaded with beef, cheese and sour cream.", 780, 35),
            ("Peanut Butter Chicken Stir Fry", "Chicken stir-fried in a creamy peanut butter sauce over rice.", 800, 40),
            ("Beef Lasagna", "Layered pasta with seasoned beef, ricotta and mozzarella.", 830, 38),
            ("Salmon with Creamy Rice", "Pan-seared salmon served over creamy buttered rice.", 760, 36),
            ("Chicken Parmesan with Pasta", "Breaded chicken parmesan over pasta with marinara sauce.", 870, 44),
            ("Pork Chops with Mashed Potatoes", "Pan-fried pork chops with buttery mashed potatoes and gravy.", 810, 39),
            ("Cheesy Beef Burrito Bowl", "Seasoned beef, rice, beans and melted cheese in a bowl.", 790, 37),
            ("Mac and Cheese with Chicken", "Creamy mac and cheese topped with grilled chicken.", 900, 41),
        ],
        "snack": [
            ("Peanut Butter Banana Toast", "Whole grain toast topped with peanut butter and banana.", 400, 12),
            ("Trail Mix", "A calorie-dense mix of nuts, seeds and dried fruit.", 380, 10),
            ("Protein Milkshake", "Whole milk shake blended with protein powder and banana.", 450, 20),
            ("Granola Bar with Nut Butter", "Granola bar spread with extra almond butter.", 350, 9),
            ("Avocado Toast with Egg", "Sourdough toast topped with mashed avocado and a fried egg.", 420, 14),
        ],
        "dessert": [
            ("Peanut Butter Cheesecake", "Rich cheesecake swirled with peanut butter.", 550, 8),
            ("Banana Bread", "Moist homemade banana bread slice.", 480, 6),
            ("Chocolate Brownie", "Fudgy chocolate brownie square.", 520, 7),
            ("Caramel Cookie Dough", "Edible cookie dough drizzled with caramel sauce.", 560, 6),
            ("Nutella Pancakes", "Fluffy pancakes layered and topped with Nutella.", 600, 8),
        ],
    },
    "protein-power": {
        "main": [
            ("Grilled Chicken Breast with Egg Whites", "Grilled chicken breast served with scrambled egg whites.", 480, 55),
            ("Steak with Cottage Cheese", "Lean grilled steak served with a side of cottage cheese.", 550, 50),
            ("Turkey Meatloaf", "Lean turkey meatloaf with a side of steamed vegetables.", 500, 48),
            ("Tuna Steak with Quinoa", "Seared tuna steak served over protein-rich quinoa.", 490, 52),
            ("Protein-Packed Chili", "Ground beef and bean chili loaded with protein.", 520, 45),
            ("Chicken and Egg Fried Rice", "Fried rice with grilled chicken and scrambled eggs.", 540, 46),
            ("Grilled Salmon with Lentils", "Grilled salmon fillet served over seasoned lentils.", 530, 47),
            ("Beef and Bean Bowl", "Lean ground beef with black beans and brown rice.", 560, 49),
            ("Turkey Burger with Extra Cheese", "Lean turkey burger patty topped with double cheese.", 570, 50),
            ("Baked Chicken Thighs with Chickpeas", "Baked chicken thighs served with seasoned chickpeas.", 550, 48),
        ],
        "snack": [
            ("Protein Shake", "Whey protein shake blended with milk.", 200, 25),
            ("Cottage Cheese with Almonds", "Cottage cheese topped with a handful of almonds.", 220, 22),
            ("Boiled Eggs (x3)", "Three boiled eggs for a quick protein boost.", 234, 18),
            ("Beef Jerky", "Lean, high-protein beef jerky strips.", 190, 20),
            ("Greek Yogurt with Protein Powder", "Greek yogurt mixed with a scoop of protein powder.", 230, 28),
        ],
        "dessert": [
            ("Protein Cheesecake", "High-protein cheesecake made with Greek yogurt and whey.", 280, 20),
            ("Protein Brownie", "Fudgy brownie baked with whey protein powder.", 260, 18),
            ("Whey Protein Pudding", "Creamy pudding blended with whey protein.", 240, 22),
            ("Protein Cookie Dough Bites", "Bite-sized edible cookie dough made with protein powder.", 250, 19),
            ("Chocolate Protein Ice Cream", "Chocolate ice cream made with added whey protein.", 270, 21),
        ],
    },
}


def seed_meals(apps, schema_editor):
    Category = apps.get_model("menu", "Category")
    Meal = apps.get_model("menu", "Meal")

    for name, slug, description in CATEGORIES:
        category, _ = Category.objects.get_or_create(
            slug=slug, defaults={"name": name, "description": description}
        )
        for meal_type, meals in MEALS[slug].items():
            for meal_name, meal_description, calories, protein_g in meals:
                Meal.objects.get_or_create(
                    category=category,
                    name=meal_name,
                    meal_type=meal_type,
                    defaults={
                        "description": meal_description,
                        "calories": calories,
                        "protein_g": protein_g,
                    },
                )


def remove_meals(apps, schema_editor):
    Category = apps.get_model("menu", "Category")
    slugs = [slug for _, slug, _ in CATEGORIES]
    Category.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("menu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_meals, remove_meals),
    ]
