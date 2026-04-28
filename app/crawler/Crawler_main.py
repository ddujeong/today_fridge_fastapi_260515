import Crawler_tool
import pandas as pd
from selenium.webdriver.common.by import By

page = 8
target_url = f"https://www.10000recipe.com/recipe/list.html?cat4=63&order=reco&page={page}"
crawler = Crawler_tool.Crawler(target_url=target_url)
crawler.set_target_url(target_url)

page1_elems = {
  "recipe_type": "/html/body/dl/dd/div[1]/table/tbody/tr[1]/td/div/div[1]",
  "recipe_list": "/html/body/dl/dd/ul/ul",
}


def _safe_find_text(parent, by, value, default=""):
  try:
    return parent.find_element(by, value).text.strip()
  except Exception:
    return default


def main():
  recipe_list_per_page = []

  crawler.wait(0.1, 0.3)
  list_url = crawler.target_url
  crawler.ensure_list_page(list_url)

  item_xpath = "./li[contains(@class,'common_sp_list_li')]"
  recipe_items = crawler.get_elem_class("common_sp_list_ul").find_elements(By.XPATH, item_xpath)

  for idx in range(len(recipe_items)):
    crawler.ensure_list_page(list_url)
    current_items = crawler.get_elem_class("common_sp_list_ul").find_elements(By.XPATH, item_xpath)

    if idx >= len(current_items):
      print(f"[MK2] skip index={idx} because current item count is {len(current_items)}")
      continue

    recipe_title_img = None
    recipe_title = ""
    recipe_quantity = ""
    recipe_time = ""
    recipe_difficulty = ""
    recipe_ingredients = []
    recipe_steps = []

    crawler._close_ad_overlays()

    list_url = crawler.current_url()
    clicked = crawler.click(current_items[idx])
    if not clicked:
      print(f"[MK2] skip index={idx} due to click failure")
      continue

    crawler._close_ad_overlays()

    try:
      summary_box = crawler.get_elem_class("view2_summary")
      recipe_title = summary_box.find_element(By.TAG_NAME, "h3").text.strip()
      recipe_quantity = _safe_find_text(summary_box, By.XPATH, ".//div[contains(@class, 'view2_summary_info')]//span[1]")
      recipe_time = _safe_find_text(summary_box, By.XPATH, ".//div[contains(@class, 'view2_summary_info')]//span[2]")
      recipe_difficulty = _safe_find_text(summary_box, By.XPATH, ".//div[contains(@class, 'view2_summary_info')]//span[3]")

      print("title : ", recipe_title)
      print("quantity : ", recipe_quantity)
      print("time : ", recipe_time)
      print("difficulty : ", recipe_difficulty)
    except Exception as e:
      print(f"[WARN] Failed to read summary: {e}")
      try:
        crawler.back(fallback_url=list_url)
      except Exception as back_error:
        print(f"[WARN] back failed after summary error: {back_error}")
      continue

    try:
      ingredient_list = crawler.get_elem_id("divConfirmedMaterialArea").find_elements(By.XPATH, "./ul/li")
      for each in ingredient_list:
        ingredient_name = each.find_element(By.XPATH, "./div").text.strip()
        ingredient_quantity = each.find_element(By.XPATH, "./span").text.strip()
        print(f"ingredient: {ingredient_name}, quantity: {ingredient_quantity}")
        recipe_ingredients.append({
          "name": ingredient_name,
          "quantity": ingredient_quantity,
        })
      print("ingredients : ", recipe_ingredients, "\n")
    except Exception as e:
      print(f"[WARN] Failed to read ingredients: {e}")
      try:
        crawler.back(fallback_url=list_url)
      except Exception as back_error:
        print(f"[WARN] back failed after ingredient error: {back_error}")
      continue

    crawler._close_ad_overlays()

    try:
      recipe_list = crawler.get_elem_id('obx_recipe_step_start').find_elements(By.XPATH, "./div")
      recipe_list = recipe_list[1:]

      for each in recipe_list:
        try:
          step_description = each.find_element(By.XPATH, "./div[1]").text.strip()
          step_image = each.find_element(By.XPATH, "./div[2]/img").get_attribute("src")
          print("step description : ", step_description)
          print("step image : ", step_image)
          recipe_steps.append({
            "description": step_description,
            "image": step_image,
          })
        except Exception:
          break

      print("steps : ", recipe_steps, "\n\n")
    except Exception as e:
      print(f"[WARN] Failed to read steps: {e}")
      try:
        crawler.back(fallback_url=list_url)
      except Exception as back_error:
        print(f"[WARN] back failed after step error: {back_error}")
      continue

    crawler._close_ad_overlays()

    try:
      recipe_title_img = crawler.get_elem_id('main_thumbs').get_attribute("src")
    except Exception as e:
      print(f"[WARN] Failed to get title image: {e}")
      recipe_title_img = None

    recipe = {
      "img": recipe_title_img,
      "title": recipe_title,
      "quantity": recipe_quantity,
      "time": recipe_time,
      "difficulty": recipe_difficulty,
      "ingredients": recipe_ingredients,
      "steps": recipe_steps,
    }
    recipe_list_per_page.append(recipe)

    try:
      crawler.back(fallback_url=list_url)
    except Exception as e:
      print(f"[WARN] back failed: {e}")

    print(f"[MK2] after back url={crawler.current_url()}")
    crawler.dismiss_ads()
    crawler.wait(0.1, 0.3)

  print(recipe_list_per_page)
  pd.DataFrame(recipe_list_per_page).to_csv(f"./recipes_result/recipes{page}.csv", index=False, encoding='utf-8-sig')


if __name__ == "__main__":
  main()
