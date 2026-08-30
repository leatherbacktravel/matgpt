import json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

URL = "https://leatherbacktravel.github.io/matgpt/"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1440,1000")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 60)
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

    driver.execute_script(
        "const input=document.querySelector('[data-score-axis=appropriateness]');"
        "input.value='82';input.dispatchEvent(new Event('input',{bubbles:true}));"
    )
    driver.find_element(By.ID, "drawer-notes").send_keys("Automated live verification")
    Select(driver.find_element(By.ID, "drawer-decision")).select_by_value("approve")
    driver.find_element(By.CSS_SELECTOR, '[data-drawer-action="save-candidate"]').click()
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".drawer")) == 0)
    results["candidate_review_saved"] = len(driver.find_elements(By.XPATH, "//*[normalize-space(text())='Approve']")) > 0

    driver.find_element(By.CSS_SELECTOR, '#side-nav [data-route="sources"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Source universe")
    results["source_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))

    driver.find_element(By.CSS_SELECTOR, '#side-nav [data-route="review"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Review queue")
    results["review_cards_after_approval"] = len(driver.find_elements(By.CSS_SELECTOR, ".review-card"))

    driver.find_element(By.ID, "add-candidate-button").click()
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".modal")) == 1)
    driver.find_element(By.ID, "new-name").send_keys("Automated Test Brand")
    driver.find_element(By.ID, "new-lane").send_keys("Verification")
    driver.find_element(By.ID, "new-route").send_keys("Direct")
    driver.find_element(By.ID, "new-rationale").send_keys("Confirms candidate creation and browser persistence.")
    driver.find_element(By.CSS_SELECTOR, '[data-modal-action="create-candidate"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, ".drawer h2").text == "Automated Test Brand")
    driver.find_element(By.CSS_SELECTOR, '.drawer [data-close-drawer]').click()

    driver.find_element(By.CSS_SELECTOR, '#side-nav [data-route="candidates"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Licensing candidates")
    results["custom_candidate_visible"] = len(driver.find_elements(By.XPATH, "//*[normalize-space(text())='Automated Test Brand']")) > 0

    driver.refresh()
    wait.until(lambda d: d.title == "Leatherback Licensing Atlas")
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Licensing candidates")
    results["local_persistence_after_refresh"] = len(driver.find_elements(By.XPATH, "//*[normalize-space(text())='Automated Test Brand']")) > 0

    driver.find_element(By.CSS_SELECTOR, '#side-nav [data-route="research"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Research run")
    research_url = driver.find_element(By.ID, "research-url")
    research_url.clear()
    research_url.send_keys("https://example.com")
    driver.find_element(By.CSS_SELECTOR, '[data-research-mode="inspect"]').click()
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".run-status.success")) >= 1)
    results["research_result_title"] = driver.find_element(By.CSS_SELECTOR, ".run-status.success .run-head strong").text
    results["research_runner_success"] = "Example Domain" in results["research_result_title"]

    driver.save_screenshot("/tmp/licensing-atlas-verification.png")

    severe = [
        entry for entry in driver.get_log("browser")
        if entry.get("level") == "SEVERE" and "favicon.ico" not in entry.get("message", "")
    ]
    results["severe_console_errors"] = severe

    assert results["metric_cards"] == 4, results
    assert results["candidate_rows"] == 50, results
    assert results["source_rows"] == 94, results
    assert results["drawer_title"] == "National Trust", results
    assert results["candidate_review_saved"], results
    assert results["review_cards_after_approval"] == 49, results
    assert results["custom_candidate_visible"], results
    assert results["local_persistence_after_refresh"], results
    assert results["research_runner_success"], results
    assert not severe, results

    results["ok"] = True
    print(json.dumps(results, indent=2))
finally:
    driver.quit()
