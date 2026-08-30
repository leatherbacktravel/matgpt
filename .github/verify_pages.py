import json
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE = "https://leatherbacktravel.github.io/matgpt/"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1500,1100")
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 90)
results = {"url": BASE}


def fetch_json(path):
    request = urllib.request.Request(BASE + path, headers={"Cache-Control": "no-cache", "User-Agent": "Licensing-Atlas-Verification/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_current_deployment():
    last_heading = ""
    for attempt in range(12):
        driver.get(f"{BASE}?verify={int(time.time())}-{attempt}")
        try:
            WebDriverWait(driver, 20).until(lambda d: d.title == "Leatherback Licensing Atlas")
            WebDriverWait(driver, 20).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "h1")) > 0)
            last_heading = driver.find_element(By.CSS_SELECTOR, "h1").text
            if last_heading == "Licensing-market database":
                return
        except Exception:
            pass
        time.sleep(5)
    raise AssertionError(f"Current database-driven deployment did not become available; last h1={last_heading!r}")


try:
    wait_for_current_deployment()
    wait.until(lambda d: d.find_element(By.ID, "live-dot").get_attribute("class").find("ok") >= 0)

    metadata = fetch_json("database-v3/metadata.json")
    results["metadata"] = {
        key: metadata[key]
        for key in (
            "registered_sources", "sources_complete", "sources_failed", "sources_skipped_gated",
            "pages_captured", "raw_brand_strings", "clean_agencies", "clean_brands",
            "clean_high_confidence_brands", "clean_documented_brands", "clean_relationships",
            "clean_evidence_records", "rejected_or_unresolved_brand_strings",
        )
    }

    results["title"] = driver.title
    results["overview_h1"] = driver.find_element(By.CSS_SELECTOR, "h1").text
    results["metric_cards"] = len(driver.find_elements(By.CSS_SELECTOR, ".metric"))
    results["overview_mentions_raw_count"] = "6,299" in driver.find_element(By.TAG_NAME, "body").text
    results["overview_mentions_clean_count"] = "1,762" in driver.find_element(By.TAG_NAME, "body").text

    driver.find_element(By.CSS_SELECTOR, '#nav [data-route="agencies"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Licensing agencies")
    results["agency_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))
    results["agency_search_present"] = driver.find_element(By.ID, "agency-q").is_displayed()

    driver.find_element(By.CSS_SELECTOR, '#nav [data-route="brands"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Brands & properties")
    results["initial_brand_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))
    brand_search = driver.find_element(By.ID, "brand-q")
    brand_search.send_keys("National Wildlife Federation")
    wait.until(lambda d: len(d.find_elements(By.XPATH, "//tbody//tr[.//*[normalize-space(text())='National Wildlife Federation']]")) == 1)
    results["nwf_search_result"] = True
    driver.find_element(By.XPATH, "//tbody//tr[.//*[normalize-space(text())='National Wildlife Federation']]").click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, ".drawer h1").text == "National Wildlife Federation")
    results["drawer_title"] = driver.find_element(By.CSS_SELECTOR, ".drawer h1").text
    results["drawer_has_source_evidence"] = "Agency evidence" in driver.find_element(By.CSS_SELECTOR, ".drawer").text
    driver.find_element(By.CSS_SELECTOR, ".drawer [data-close]").click()
    wait.until(lambda d: "open" not in d.find_element(By.ID, "drawer-bg").get_attribute("class"))

    driver.find_element(By.CSS_SELECTOR, '#nav [data-route="relationships"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Agency–brand links")
    results["initial_relationship_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))
    relationship_search = driver.find_element(By.ID, "rel-q")
    relationship_search.send_keys("National Wildlife Federation")
    wait.until(lambda d: len(d.find_elements(By.XPATH, "//tbody//tr[.//*[normalize-space(text())='National Wildlife Federation']]")) >= 1)
    results["nwf_relationship_visible"] = True

    driver.find_element(By.CSS_SELECTOR, '#nav [data-route="sources"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Sources & failures")
    results["all_source_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))
    Select(driver.find_element(By.ID, "source-status")).select_by_value("failed")
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "tbody tr")) == metadata["sources_failed"])
    results["failed_source_rows"] = len(driver.find_elements(By.CSS_SELECTOR, "tbody tr"))

    driver.find_element(By.CSS_SELECTOR, '#nav [data-route="database"]').click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "h1").text == "Database")
    db_link = driver.find_element(By.CSS_SELECTOR, 'a[href="database-v3/licensing_database.sqlite"]')
    results["database_link_visible"] = db_link.is_displayed()
    quality_link = driver.find_element(By.CSS_SELECTOR, 'a[href="database-v3/QUALITY_REPORT.md"]')
    results["quality_report_link_visible"] = quality_link.is_displayed()

    head = urllib.request.Request(BASE + "database-v3/licensing_database.sqlite", method="HEAD", headers={"User-Agent": "Licensing-Atlas-Verification/1.0"})
    with urllib.request.urlopen(head, timeout=45) as response:
        results["database_http_status"] = response.status
        results["database_content_length"] = int(response.headers.get("Content-Length", "0"))

    driver.save_screenshot("/tmp/licensing-atlas-verification.png")

    severe = [
        entry for entry in driver.get_log("browser")
        if entry.get("level") == "SEVERE" and "favicon.ico" not in entry.get("message", "")
    ]
    results["severe_console_errors"] = severe

    assert results["overview_h1"] == "Licensing-market database", results
    assert results["metric_cards"] == 6, results
    assert results["overview_mentions_raw_count"], results
    assert results["overview_mentions_clean_count"], results
    assert metadata["registered_sources"] == 94, results
    assert metadata["clean_agencies"] >= 80, results
    assert metadata["clean_brands"] >= 1000, results
    assert metadata["clean_relationships"] >= 1000, results
    assert metadata["clean_evidence_records"] >= 2000, results
    assert metadata["raw_brand_strings"] > metadata["clean_brands"], results
    assert results["agency_rows"] == metadata["clean_agencies"], results
    assert results["initial_brand_rows"] == 300, results
    assert results["drawer_title"] == "National Wildlife Federation", results
    assert results["drawer_has_source_evidence"], results
    assert results["initial_relationship_rows"] == 300, results
    assert results["nwf_relationship_visible"], results
    assert results["all_source_rows"] == metadata["registered_sources"], results
    assert results["failed_source_rows"] == metadata["sources_failed"], results
    assert results["database_link_visible"], results
    assert results["quality_report_link_visible"], results
    assert results["database_http_status"] == 200, results
    assert results["database_content_length"] > 30_000_000, results
    assert not severe, results

    results["ok"] = True
    print(json.dumps(results, indent=2))
finally:
    driver.quit()
