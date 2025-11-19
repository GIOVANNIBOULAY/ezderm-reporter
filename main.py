"""
main.py    EZDERM Report Automation Script
"""


import json
import os
import time
import csv
from datetime import datetime, timedelta
import pytz
import sys
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import shared EZDERM automation library
from ezderm_common import (
    load_credentials,
    initialize_chrome_driver,
    login_to_ezderm,
    safe_click,
    wait_for_csv_download,
    cleanup_downloaded_files,
    send_email,
    send_error_notification,
    close_driver_safely
)

# Note: Selenium imports now handled by ezderm_common
# Note: SMTP/email imports now handled by ezderm_common

# Client time zone (CST/CDT) - used for report scheduling
cst = pytz.timezone("America/Chicago")

def get_report_period(report_type, today_in_cst):
    """
    Determines the reporting period string and text based on the report type and current date.
    Args:
        report_type (str): 'daily', 'weekly', or 'monthly'.
        today_in_cst (datetime): The current datetime object localized to CST/CDT.
    Returns:
        tuple: (period_string, period_text_for_email)
    """
    if report_type == "daily":
        # Daily report is for the current day (today_in_cst)
        return today_in_cst.strftime("%Y-%m-%d"), f"Daily report for {today_in_cst.strftime('%Y-%m-%d')}"
    elif report_type == "weekly":
        # Weekly report covers the last 7 days ending on today_in_cst (which should be a Sunday)
        end_date = today_in_cst
        start_date = end_date - timedelta(days=6) # Assuming Sunday, this goes back to Monday
        return f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", \
               f"Weekly report for {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    elif report_type == "monthly":
        # Monthly report is for the entire previous calendar month
        first_day_of_current_month = today_in_cst.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        return last_day_of_previous_month.strftime("%Y-%B"), f"Monthly report for {last_day_of_previous_month.strftime('%B %Y')}"
    else:
        raise ValueError(f"Invalid report type: {report_type}")

def send_to_zapier(data, credentials):
    """Send processed report data to a Zapier webhook."""
    webhook_url = os.getenv('ZAP_WEBHOOK_URL')
    
    if not webhook_url:
        print("Error: Zapier webhook URL is not configured. Cannot send data.")
        return
    
    try:
        response = requests.post(webhook_url, json=data, timeout=10)
        response.raise_for_status()
        print(f"Data successfully sent to Zapier. Status code: {response.status_code}")
    except requests.RequestException as e:
        print(f"Failed to send data to Zapier: {e}")

def run_report_generation(report_type):
    """
    Main function to log in to EZDERM, download the report,
    process appointment counts, and send the results to a Zapier webhook.
    Args:
        report_type (str): 'daily', 'weekly', or 'monthly'.
    """
    # Check if essential credentials are loaded
    required_env_vars = ['EZDERM_USERNAME', 'EZDERM_PASSWORD', 'ZAP_WEBHOOK_URL']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        error_msg = f"Critical Error: Missing environment variables: {', '.join(missing_vars)}. Cannot proceed."
        print(error_msg)
        admin_email_recipient = os.getenv("ADMIN_EMAIL", "gio@gervainlabs.com") # Default admin email
        if email_address and email_password: # Attempt to notify admin if possible
             send_email("EZDERM Reporter - CRITICAL CONFIG ERROR", error_msg.replace('\n', '<br>'), admin_email_recipient)
        else:
            print("Cannot send admin notification email due to missing sender credentials.")
        sys.exit(1) # Exit script if config is missing

    driver = None # Initialize driver to None for the finally block
    try:
        print(f"Initializing Chrome driver for {report_type} report...")
        # Load credentials from environment
        credentials = load_credentials()
   
        # Initialize Chrome WebDriver
        download_dir = "/tmp/downloads"
        driver = initialize_chrome_driver(download_dir)
        print("Chrome driver initialized.")

        print("Navigating to EZDERM login page: https://pms.ezderm.com/login")
        # Login to EZDERM
        login_to_ezderm(driver, credentials['ezderm_username'], credentials['ezderm_password'])

        print("Navigating to Custom Reports page: https://pms.ezderm.com/customReports")
        driver.get("https://pms.ezderm.com/customReports")

        report_titles = {
            "daily": "Daily Signed Off Appointments",
            "weekly": "Weekly Signed Off Appointments",
            "monthly": "Monthly Signed Off Appointments"
        }
        report_title_to_find = report_titles[report_type]
        print(f"Locating '{report_title_to_find}' report link...")

        report_div_xpath = f"//div[contains(@class, 'styles_ChildItem__llCUk') and contains(text(), '{report_title_to_find}')]"
        safe_click(driver, (By.XPATH, report_div_xpath))
        print(f"Clicked on '{report_title_to_find}'.")

        print("Locating and clicking 'Generate CSV' button...")
        csv_button_selector = "[data-pendo='button-generate-csv']"
        safe_click(driver, (By.CSS_SELECTOR, csv_button_selector))
        print("'Generate CSV' button clicked.")

        print(f"Waiting for CSV file to download to {download_dir}...")
        time_to_wait_for_download = 30  # seconds
        time_counter = 0
        # Wait for CSV download
        downloaded_csv_file = wait_for_csv_download(download_dir, timeout_seconds=60)
        
        print(f"Processing CSV file: {downloaded_csv_file}...")
        # Provider names as per PRD
        providers_counts = {
            'Kayela Asplund, NP': 0,
            'Samantha Conklin, NP': 0,
            'Jonathan Hayward, PA': 0
        }
        with open(downloaded_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            # The script assumes provider counts are in a specific format "Provider Name: Count"
            # PRD mentioned investigating summary rows, this logic parses all rows.
            for row_index, row_data in enumerate(reader):
                if not row_data or not row_data[0]: # Skip empty rows or rows with empty first cell
                    continue
                cell_content = row_data[0].strip()
                for provider_name_key in providers_counts.keys():
                    if provider_name_key in cell_content:
                        try:
                            # Assuming format "Provider Name: Count"
                            count_str = cell_content.split(":")[-1].strip()
                            count = int(count_str)
                            providers_counts[provider_name_key] = count
                            print(f"Found count for {provider_name_key}: {count}")
                        except (ValueError, IndexError) as parse_error:
                            print(f"Warning: Could not parse count for {provider_name_key} in row {row_index+1}: '{cell_content}'. Error: {parse_error}")

        # Determine reporting period details using the current time in CST
        current_time_cst = datetime.now(cst) # Get fresh current time for report metadata
        period_str, period_text_for_email = get_report_period(report_type, current_time_cst)
        
        # Prepare payload for Zapier
        report_data = {
            "report_type": report_type,
            "period": period_str,
            "timestamp": current_time_cst.isoformat(),
            "counts": providers_counts
        }
        print("Sending processed data to Zapier webhook...")
        send_to_zapier(report_data, credentials)

        # Delete CSV for HIPAA compliance
        cleanup_downloaded_files(download_dir)

    except Exception as e:
        error_subject = f"EZDERM Reporter Error (Heroku) - {report_type.capitalize()}"
        error_message_detail = str(e)
        current_url_info = "\nDriver not initialized or URL not available."
        page_source_info = "\nPage source not available."

        if driver: # Check if driver object exists
            try:
                current_url_info = f"\n\nCurrent URL: {driver.current_url}"
            except Exception as url_err:
                current_url_info = f"\nCould not retrieve current URL from driver: {url_err}"
            try:
                page_source_info = f"\nPage source snippet (first 1000 chars):\n{driver.page_source[:1000]}"
            except Exception as ps_err:
                page_source_info = f"\nCould not retrieve page source from driver: {ps_err}"
            
            # Screenshot path for Heroku's ephemeral filesystem
            error_screenshot_path = "/tmp/error.png"
            try:
                driver.save_screenshot(error_screenshot_path)
                print(f"Error screenshot saved to {error_screenshot_path} (ephemeral on Heroku).")
                # Note: Accessing this screenshot from Heroku logs directly is difficult.
                # It's mainly for confirming if screenshot capture works. The error details in email are more critical.
            except Exception as screenshot_error:
                print(f"Failed to save error screenshot: {screenshot_error}")
        
        # Construct error body for email (HTML formatted)
        error_body_html = (f"An error occurred during the EZDERM '{report_type}' report generation on Heroku:<br>"
                           f"<pre>Error: {error_message_detail}</pre>"
                           f"{current_url_info.replace(chr(10), '<br>')}" # Replace newline for HTML
                           f"{page_source_info.replace(chr(10), '<br>')}") # Replace newline for HTML
        
        print(f"Error: {error_message_detail}") # Log raw error to Heroku console
        print(f"Detailed error info for email:\n{error_body_html}") # Log HTML error body for debugging
        
        # Send error notification
        send_error_notification(e, driver, context=f"{report_type.capitalize()} Report", credentials=credentials)
        
        # Clean up resources
        close_driver_safely(driver)

if __name__ == "__main__":
    # This block is executed when the script is run directly (e.g., by Heroku Scheduler)
    if len(sys.argv) > 1:
        report_type_arg = sys.argv[1].lower()
    else:
        # Default to 'daily' if no argument is provided, though Heroku Scheduler should always provide one.
        print("Warning: Report type (daily, weekly, monthly) argument missing. Defaulting to 'daily'.")
        report_type_arg = 'daily'

    # Validate the report_type argument
    if report_type_arg not in ["daily", "weekly", "monthly"]:
        print(f"Error: Invalid report type argument '{report_type_arg}'. Must be 'daily', 'weekly', or 'monthly'.")
        sys.exit(1) # Exit with error code

    # Get the current time in CST for scheduler logic
    # The 'cst' timezone object should be defined globally earlier in the script.
    current_datetime_cst = datetime.now(cst)
    
    proceed_with_report_generation = False # Flag to control execution

    print(f"Scheduler invoked for '{report_type_arg}' report. Current CST time: {current_datetime_cst.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")

    if report_type_arg == "daily":
        # PRD: Daily Report to run every weekday (Monday to Friday).
        # datetime.weekday(): Monday is 0 and Sunday is 6.
        if current_datetime_cst.weekday() < 5: # 0 (Mon), 1 (Tue), 2 (Wed), 3 (Thu), 4 (Fri)
            print(f"Today is {current_datetime_cst.strftime('%A')} (weekday). Proceeding with '{report_type_arg}' report generation.")
            proceed_with_report_generation = True
        else:
            print(f"Today is {current_datetime_cst.strftime('%A')} (weekend). '{report_type_arg}' report runs only on weekdays. Skipping actual report generation.")
    
    elif report_type_arg == "weekly":
        # PRD: Weekly Report to run every Sunday.
        if current_datetime_cst.weekday() == 6: # 6 corresponds to Sunday.
            print(f"Today is Sunday. Proceeding with '{report_type_arg}' report generation.")
            proceed_with_report_generation = True
        else:
            print(f"Today is {current_datetime_cst.strftime('%A')}. '{report_type_arg}' report runs only on Sunday. Skipping actual report generation.")

    elif report_type_arg == "monthly":
        # PRD: Monthly Report to run on the 1st day of every month.
        if current_datetime_cst.day == 1:
            print(f"Today is the 1st of the month. Proceeding with '{report_type_arg}' report generation.")
            proceed_with_report_generation = True
        else:
            print(f"Today is the {current_datetime_cst.day}. '{report_type_arg}' report runs only on the 1st of the month. Skipping actual report generation.")

    if proceed_with_report_generation:
        try:
            print(f"Conditions met. Starting main logic for {report_type_arg.capitalize()} report...")
            run_report_generation(report_type_arg)
            print(f"Successfully completed {report_type_arg.capitalize()} report generation and processing.")
            sys.exit(0) # Indicate successful execution
        except Exception as e:
            # Errors within run_report_generation should be caught and handled there (including email notifications)
            # This catch is a final fallback.
            print(f"Critical unhandled error during {report_type_arg.capitalize()} report execution in __main__: {e}")
            sys.exit(1) # Indicate failure
    else:
        # If not proceeding, the script has already printed a message. Exit gracefully.
        print(f"Skipped full report generation for '{report_type_arg}' as per schedule logic.")
        sys.exit(0) # Indicate successful completion of the scheduler check (even if report was skipped).
