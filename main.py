import json
import os
import time
import glob
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv # Good for local testing, Heroku will use Config Vars
import sys

# Load environment variables from .env file (for local development)
# On Heroku, these will be set as Config Vars
load_dotenv()

# Get credentials from environment variables
username = os.getenv('EZDERM_USERNAME')
password = os.getenv('EZDERM_PASSWORD')
email_address = os.getenv('EMAIL_ADDRESS')
email_password = os.getenv('EMAIL_PASSWORD')

# Determine the absolute path of the script's directory (less critical on Heroku for this script)
# script_dir = os.path.dirname(os.path.abspath(__file__)) # We'll use /tmp for dynamic files

# Set up download directory - Heroku allows writing to /tmp
download_dir = "/tmp/downloads" # Correct for Heroku's ephemeral filesystem
os.makedirs(download_dir, exist_ok=True)

# Set up Chrome options for Heroku
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
# chrome_options.add_argument("--single-process") # Often not needed with newer Chrome/ChromeDriver

# --- HEROKU CHANGE: Use Chrome binary location provided by buildpack ---
# Heroku buildpacks typically set GOOGLE_CHROME_BIN or place chrome in PATH
chrome_bin_path = os.getenv('GOOGLE_CHROME_BIN')
if chrome_bin_path:
    chrome_options.binary_location = chrome_bin_path
else:
    print("Warning: GOOGLE_CHROME_BIN not set. Relying on Chrome being in PATH.")
# If the buildpack adds Chrome to PATH, binary_location might not be strictly necessary.

# Configure downloads
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True # Corrected from "safeBrowse.enabled"
})

# --- HEROKU CHANGE: Use ChromeDriver path provided by buildpack or rely on PATH ---
chromedriver_path = os.getenv('CHROMEDRIVER_PATH')
if chromedriver_path:
    print(f"Using CHROMEDRIVER_PATH: {chromedriver_path}")
    service = Service(executable_path=chromedriver_path)
else:
    print("Warning: CHROMEDRIVER_PATH not set. Relying on chromedriver being in PATH.")
    service = Service() # Selenium will try to find chromedriver in PATH

# Client time zone (CST)
cst = pytz.timezone("America/Chicago")

def get_report_period(report_type, today):
    if report_type == "daily":
        return today.strftime("%Y-%m-%d"), f"Daily report for {today.strftime('%Y-%m-%d')}"
    elif report_type == "weekly":
        end_date = today
        start_date = today - timedelta(days=6)
        return f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", \
               f"Weekly report for {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    elif report_type == "monthly":
        first_day_of_current_month = today.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        return last_day_of_previous_month.strftime("%Y-%B"), f"Monthly report for {last_day_of_previous_month.strftime('%B %Y')}"
    else:
        raise ValueError("Invalid report type")

def send_email(subject, html_body, to_email, attachment_path=None):
    msg = MIMEMultipart()
    msg['From'] = email_address
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    if attachment_path:
        with open(attachment_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename={os.path.basename(attachment_path)}'
        )
        msg.attach(part)

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(email_address, email_password)
        server.send_message(msg)

def run_report_generation(report_type):
    # Check if essential credentials are loaded
    if not all([username, password, email_address, email_password]):
        missing_vars = [var for var in ['EZDERM_USERNAME', 'EZDERM_PASSWORD', 'EMAIL_ADDRESS', 'EMAIL_PASSWORD'] if not os.getenv(var)]
        error_msg = f"Critical Error: Missing one or more environment variables: {', '.join(missing_vars)}. Cannot proceed."
        print(error_msg)
        # Attempt to send an email if email_address and email_password are set for admin notification
        if email_address and email_password:
            try:
                send_email("EZDERM Reporter - CRITICAL CONFIG ERROR", error_msg.replace('\n', '<br>'), "gio@gervainlabs.com")
            except Exception as email_err:
                print(f"Failed to send critical config error email: {email_err}")
        sys.exit(1) # Exit script if config is missing

    driver = None # Initialize driver to None for the finally block
    try:
        print("Initializing Chrome driver...")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("Chrome driver initialized.")

        print("Navigating to EZDERM login page...")
        driver.get("https://pms.ezderm.com/login")

        wait = WebDriverWait(driver, 20) # Increased wait time slightly for Heroku's environment
        print("Locating username field...")
        username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        print("Locating password field...")
        password_field = driver.find_element(By.ID, "password")

        print("Entering credentials...")
        username_field.send_keys(username)
        password_field.send_keys(password)

        print("Clicking login button...")
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']")))
        login_button.click()

        print("Checking for dashboard URL...")
        wait.until(EC.url_to_be("https://pms.ezderm.com/dashboard"))
        print("Login successful! Landed on dashboard: ", driver.current_url)

        print("Navigating to Custom Reports page...")
        driver.get("https://pms.ezderm.com/customReports")

        report_titles = {
            "daily": "Daily Signed Off Appointments",
            "weekly": "Weekly Signed Off Appointments",
            "monthly": "Monthly Signed Off Appointments"
        }
        report_title = report_titles[report_type]
        print(f"Locating {report_title} report...")
        report_div = wait.until(EC.element_to_be_clickable(
            (By.XPATH, f"//div[contains(@class, 'styles_ChildItem__llCUk') and contains(text(), '{report_title}')]")
        ))
        report_div.click()

        print("Generating CSV...")
        csv_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "[data-pendo='button-generate-csv']")
        ))
        csv_button.click()

        print("Waiting for CSV download...")
        # More robust download wait
        time_to_wait = 20  # seconds
        time_counter = 0
        csv_file = None
        while time_counter < time_to_wait:
            csv_files = glob.glob(os.path.join(download_dir, "*.csv"))
            if csv_files:
                csv_file = sorted(csv_files, key=os.path.getmtime, reverse=True)[0]
                break
            time.sleep(1)
            time_counter += 1
        
        if not csv_file:
            all_files_in_download_dir = glob.glob(os.path.join(download_dir, "*"))
            print(f"Debug: Files in download dir ({download_dir}): {all_files_in_download_dir}")
            raise Exception(f"CSV file not found in downloads folder ({download_dir}) after {time_to_wait} seconds.")
        print(f"CSV downloaded: {csv_file}")

        print("Processing CSV...")
        providers = {
            'Kayela Asplund, NP': 0,
            'Samantha Conklin, NP': 0,
            'Jonathan Hayward, PA': 0
        }
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or not row[0]:
                    continue
                cell = row[0].strip()
                for provider_name in providers: # Renamed 'provider' to 'provider_name' to avoid conflict
                    if provider_name in cell:
                        try:
                            count_str = cell.split(":")[-1].strip()
                            count = int(count_str)
                            providers[provider_name] = count
                        except (ValueError, IndexError) as parse_error:
                            print(f"Warning: Could not parse count for {provider_name} in row: '{cell}'. Error: {parse_error}")

        today = datetime.now(cst)
        period, period_text = get_report_period(report_type, today)
        
        subject_prefix = f"Lilly Derm {report_type.capitalize()} Appointment Report"
        if report_type == "daily":
            subject = f"{subject_prefix} - {today.strftime('%Y-%m-%d')}"
        elif report_type == "weekly":
            start_date_for_subject = today - timedelta(days=6)
            subject = f"{subject_prefix} - {start_date_for_subject.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}"
        elif report_type == "monthly":
            prev_month_obj = today.replace(day=1) - timedelta(days=1)
            subject = f"{subject_prefix} - {prev_month_obj.strftime('%Y-%B')}"
        else:
            subject = f"{subject_prefix} - {period}"

        html_body = f"""
        <html><body><p>Hey Tony,</p><p>{period_text}</p><p><strong>Appointment counts:</strong></p><ul>
        """
        for provider_name, count in providers.items(): # Renamed 'provider'
            html_body += f"<li><b>{provider_name}:</b> {count} Completed Appointments</li>"
        html_body += "</ul><p>This is an automated report.</p></body></html>"

        # Sending to your email for testing, change to tony@lillydermmd.com for production
        target_email = os.getenv("REPORT_RECIPIENT_EMAIL", "tony@lillydermmd.com") # Default to your email
        send_email(subject, html_body, target_email, csv_file)
        print(f"Email sent successfully to {target_email}!")

        print(f"Deleting CSV file: {csv_file}...")
        os.remove(csv_file)
        print("CSV file deleted.")

    except Exception as e:
        error_subject = "EZDERM Reporter Error (Heroku)"
        error_message_detail = str(e)
        current_url_info = "\nDriver not initialized or URL not available"
        page_source_info = "\nPage source not available"

        if driver: # Check if driver was initialized
            try:
                current_url_info = f"\n\nCurrent URL: {driver.current_url}"
            except:
                current_url_info = "\nCould not retrieve current URL from driver."
            try:
                page_source_info = f"\nPage source snippet (first 1000 chars): {driver.page_source[:1000]}"
            except:
                page_source_info = "\nCould not retrieve page source from driver."
            
            # --- HEROKU CHANGE: Screenshot path to /tmp ---
            error_screenshot_path = "/tmp/error.png"
            try:
                driver.save_screenshot(error_screenshot_path)
                print(f"Screenshot saved as {error_screenshot_path}")
                # Note: Accessing this screenshot from Heroku directly is hard.
                # It's mainly for logs if you could somehow retrieve it or if the error message is descriptive enough.
            except Exception as screenshot_error:
                print(f"Failed to save screenshot: {screenshot_error}")
        
        error_body_html = f"An error occurred during the EZDERM report generation on Heroku:<br><pre>{error_message_detail}</pre>"
        error_body_html += current_url_info.replace('\n', '<br>')
        error_body_html += page_source_info.replace('\n', '<br>')
        
        print(f"Error: {error_message_detail}")
        print(error_body_html) # For Heroku logs (CloudWatch equivalent)
        
        admin_email = os.getenv("ADMIN_EMAIL", "gio@gervainlabs.com") # Default to your email
        if email_address and email_password: # Check if email sending is possible
            try:
                send_email(error_subject, error_body_html, admin_email)
                print(f"Error notification sent to {admin_email}.")
            except Exception as email_error:
                print(f"CRITICAL: Failed to send error notification email: {email_error}")
        else:
            print("Cannot send error email: EMAIL_ADDRESS or EMAIL_PASSWORD not set.")
        raise # Re-raise for Heroku to log the failure
    finally:
        if driver:
            print("Closing browser...")
            driver.quit()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        report_type_arg = sys.argv[1].lower()
    else:
        print("Report type (daily, weekly, monthly) argument missing. Defaulting to 'daily'.")
        report_type_arg = 'daily'

    if report_type_arg not in ["daily", "weekly", "monthly"]:
        print(f"Error: Invalid report type '{report_type_arg}'. Must be 'daily', 'weekly', or 'monthly'.")
        sys.exit(1)

    try:
        print(f"Starting {report_type_arg.capitalize()} report generation process on Heroku...")
        run_report_generation(report_type_arg)
        print(f'{report_type_arg.capitalize()} report processed successfully.')
    except Exception as main_exception:
        print(f"Critical error during {report_type_arg} report generation: {main_exception}")
        sys.exit(1) # Indicate failure