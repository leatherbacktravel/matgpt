import json
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://leatherbacktravel.github.io/matgpt/"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1440,1000")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 30)
results = {"url": URL}

try:
    driver.get(URL)
    wait.until(lambda d: d.title == "Leatherback Licensing Atlas")
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Overview")

    results["title"] = driver.title
    results["overview_h1"] = driver.find_element(By.CSS_SELECTOR, "h1").text
    results["metric_cards"] = len(driver.find_elements(By.CSS_SELECTOR, ".metric-card"))
    results["overview_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))

    driver.find_element(By.CSS_SELECTOR, '#side-nav [data-route="candidates"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Licensing candidates")
    results["candidate_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))

    driver.find_elements(By.CSS_SELECTOR, "tbody tr")[0].click()
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".drawer")) == 1)
    results["drawer_title"] = driver.find_element(By.CSS_SELECTOR, ".drawer h2").text
    driver.find_element(By.CSS_SELECTOR, '.drawer [data-close-drawer]').click()

    driver.find_element(By.CSS_SELECTOR, '#side-nav [data-route="sources"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Source universe")
    results["source_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))

    driver.find_element(By.CSS_SELECTOR, '#side-nav [data-route="review"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Review queue")
    results["review_cards"] = len(driver.find_elements(By.CSS_SELECTOR, ".review-card"))

    driver.save_screenshot("/tmp/licensing-atlas-verification.png")

    severe = [entry for entry in driver.get_log("browser") if entry.get("level") == "SEVERE"]
    results["severe_console_errors"] = severe

    assert results["metric_cards"] == 4, results
    assert results["candidate_rows"] == 50, results
    assert results["source_rows"] == 94, results
    assert results["drawer_title"] == "National Trust", results
    assert results["review_cards"] == 50, results
    assert not severe, results

    results["ok"] = True
    print(json.dumps(results, indent=2))
finally:
    driver.quit()
