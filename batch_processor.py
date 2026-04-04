import os
import re
import shutil
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright, expect

from batch_queue import (
    reserve_jobs,
    PROCESSING_DIR,
    PROCESSED_DIR,
    FAILED_DIR,
    ERROR_SCREENSHOTS_DIR,
)

load_dotenv()

BASE_URL = "http://52.140.56.82:6102/login"


def move_processing_job(job: dict, target_dir: Path) -> dict:
    target_dir.mkdir(parents=True, exist_ok=True)

    new_vltd = target_dir / job["vltd_file"].name
    new_backend = target_dir / job["backend_file"].name

    shutil.move(str(job["vltd_file"]), str(new_vltd))
    shutil.move(str(job["backend_file"]), str(new_backend))

    return {
        "chassis_no": job["chassis_no"],
        "vltd_file": new_vltd,
        "backend_file": new_backend,
    }


def login(page, username: str, password: str) -> None:
    page.goto(BASE_URL)

    page.get_by_role("textbox", name="Your Email Address Your Email").fill(username)
    page.get_by_role("textbox", name="Password Password").fill(password)
    page.get_by_role("button", name="Sign in").click()

    expect(page.get_by_role("link", name="Device Utility")).to_be_visible(timeout=20000)


def open_ticket_list(page) -> None:
    page.get_by_role("link", name="Device Utility").click()
    expect(page.get_by_role("link", name="My AIS 140 Tickets")).to_be_visible(timeout=15000)

    page.get_by_role("link", name="My AIS 140 Tickets").click()
    expect(page.get_by_role("searchbox", name="Search and Press Enter")).to_be_visible(timeout=15000)


def search_ticket(page, chassis_no: str) -> None:
    search_box = page.get_by_role("searchbox", name="Search and Press Enter")
    search_box.click()
    search_box.fill(chassis_no)

    search_button = page.locator("button.search-btn")
    expect(search_button).to_be_visible(timeout=15000)
    search_button.click()
    page.get_by_role("img", name="ALL Image").click()
    # expect(page.locator("mat-icon:has-text('visibility')").first).to_be_visible(timeout=15000)


def open_first_ticket(page):
    with page.expect_popup() as popup_info:
        page.locator("mat-icon:has-text('visibility')").first.click()
    ticket_page = popup_info.value
    ticket_page.wait_for_load_state()
    return ticket_page
    

# (page1.get_by_text("Device Fota Status Informationexpand_more")).to_be_visible()
def remove_stage_2_restriction(ticket_page) -> None:
    try:
        opener = ticket_page.get_by_role("button").nth(5)

        # only proceed if this opener button is visible
        if not opener.is_visible():
            print("Stage 2 restriction opener not visible, skipping stage 2 restriction.")
            return

        # If the final removal button is already available, click it.
        if (
            ticket_page.get_by_role("button", name="Remove Stage 2 Restriction").count() > 0
            and ticket_page.get_by_role("button", name="Remove Stage 2 Restriction").first.is_visible()
        ):
            ticket_page.get_by_role("button", name="Remove Stage 2 Restriction").first.click()
            return

        # Try to open the restriction flow (legacy index fallback).
        if ticket_page.get_by_role("button").count() > 5:
            ticket_page.get_by_role("button").nth(5).click()
        else:
            print("Stage 2 restriction opener not found, skipping stage 2 restriction.")
            return

        ticket_page.get_by_role("combobox", name="Reason to Skip Stage 2").locator("svg").click(timeout=3000)
        ticket_page.get_by_text("The device already has the").click()
        ticket_page.get_by_role("button", name="Remove Stage 2 Restriction").click()

    except Exception as e:
        print(f"Stage 2 restriction flow not available / failed ({e}); proceeding with stages.")




def complete_stages(ticket_page) -> None: 
    
    ticket_page.get_by_role("button", name="Mark Stage 1 as Complete").click() 
    ticket_page.get_by_role("button", name="Mark Stage 2 as Complete").click() 
    ticket_page.get_by_role("button", name="Mark Stage 3 as Complete").click() 
    ticket_page.get_by_role("button", name="Mark Stage 4 as Complete").click()


def select_certificate_validity(ticket_page, value: str = "2 Year") -> None:
    ticket_page.get_by_role("combobox", name="Select Certificate Validity").locator("svg").click()
    ticket_page.get_by_role("option", name=value).click()


def upload_file_with_chooser(ticket_page, attach_button_locator, file_path: Path) -> None:
    if not file_path.exists():
        raise FileNotFoundError(f"Missing file: {file_path}")

    with ticket_page.expect_file_chooser() as fc_info:
        attach_button_locator.click()
    file_chooser = fc_info.value
    file_chooser.set_files(str(file_path))


def upload_certificates(ticket_page, vltd_file: Path, backend_file: Path) -> None:
    attach_buttons = ticket_page.get_by_role("button").filter(has_text="attach_file")

    upload_file_with_chooser(ticket_page, attach_buttons.first, vltd_file)
    upload_file_with_chooser(ticket_page, attach_buttons.nth(1), backend_file)


def close_ticket(ticket_page) -> None:
    status_dropdown = ticket_page.get_by_role(
        "combobox",
        name=re.compile(r"Overall Ticket Status", re.I)
    )

    expect(status_dropdown).to_be_visible(timeout=10000)
    status_dropdown.click()
    ticket_page.get_by_text("Ticket Completed and Closed").click()
    ticket_page.get_by_role("button", name="Update Ticket").click()

    # Replace this later with exact success text if you know it
    ticket_page.wait_for_timeout(3000)


def process_one_ticket(page, job: dict) -> None:
    chassis_no = job["chassis_no"]
    vltd_file = job["vltd_file"]
    backend_file = job["backend_file"]

    print(f"Processing chassis: {chassis_no}")

    search_ticket(page, chassis_no)
    ticket_page = open_first_ticket(page)

    try:
        # ticket_page.pause()  # Debug
        # Only attempt Stage 2 restriction removal when the FOTA section exists
        if ticket_page.get_by_text("Device Fota Status Informationexpand_more").count() > 0:
            # Ensure it is visible or at least present
            fota_el = ticket_page.get_by_text("Device Fota Status Informationexpand_more").first
            if fota_el.is_visible():
                remove_stage_2_restriction(ticket_page)
            else:
                print("FOTA section found but not visible; skipping stage 2 restriction removal.")
        else:
            print("FOTA section not found; skipping stage 2 restriction removal.")

        complete_stages(ticket_page)
        select_certificate_validity(ticket_page, "2 Year")
        upload_certificates(ticket_page, vltd_file, backend_file)
        close_ticket(ticket_page)
    finally:
        ticket_page.close()


def run(playwright: Playwright) -> None:
    username = os.getenv("TOOL_USERNAME")
    password = os.getenv("TOOL_PASSWORD")

    if not username or not password:
        raise ValueError("TOOL_USERNAME or TOOL_PASSWORD missing in .env")

    jobs = reserve_jobs(batch_limit=15)

    if not jobs:
        print("No complete jobs available in incoming.")
        return

    ERROR_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reserved {len(jobs)} job(s). Starting one browser session for batch processing.")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        login(page, username, password)
        open_ticket_list(page)

        for job in jobs:
            try:
                process_one_ticket(page, job)
                move_processing_job(job, PROCESSED_DIR)
                print(f"SUCCESS: {job['chassis_no']}")
            except Exception as e:
                print(f"FAILED: {job['chassis_no']} -> {e}")
                page.screenshot(path=str(ERROR_SCREENSHOTS_DIR / f"error_{job['chassis_no']}_main.png"))
                move_processing_job(job, FAILED_DIR)

    finally:
        context.close()
        browser.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
        
        