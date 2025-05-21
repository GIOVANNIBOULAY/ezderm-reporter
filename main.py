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
from dotenv import load_dotenv
import sys

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment variables
username = os.getenv('EZDERM_USERNAME')
password = os.getenv('EZDERM_PASSWORD')
email_address = os.getenv('EMAIL_ADDRESS')
email_password = os.getenv('EMAIL_PASSWORD')

# Determine the absolute path of the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))

# Set up download directory relative to the script
download_dir = os.path.join(script_dir, "downloads")
os.makedirs(download_dir, exist_ok=True)

# Set up Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
# chrome_options.binary_location = "/usr/bin/google-chrome" # Removed, rely on PATH or standard install

# Configure downloads
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safeBrowse.enabled": True
})

# Path to ChromeDriver, assumed to be in the same directory as the script
chromedriver_path = os.path.join(script_dir, "chromedriver")
service = Service(executable_path=chromedriver_path)

# Client time zone (CST)
cst = pytz.timezone("America/Chicago") # [cite: 27]

def get_report_period(report_type, today):
    if report_type == "daily":
        return today.strftime("%Y-%m-%d"), f"Daily report for {today.strftime('%Y-%m-%d')}"
    elif report_type == "weekly":
        end_date = today
        start_date = today - timedelta(days=6)
        return f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", \
               f"Weekly report for {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    elif report_type == "monthly":
        # For monthly report, generate for the previous full month [cite: 16]
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
    msg.attach(MIMEText(html_body, 'html')) # The PRD states plain text[cite: 24], but the original script uses HTML. Keeping HTML.

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

    # Using Gmail's SMTP server [cite: 49]
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(email_address, email_password)
        server.send_message(msg)

def run_report_generation(report_type):
    # Start the browser
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        # Navigate to EZDERM login page
        print("Navigating to EZDERM login page...")
        driver.get("https://pms.ezderm.com/login") # [cite: 9]

        # Wait for the login form to load and enter credentials
        wait = WebDriverWait(driver, 15) # Increased wait time slightly for local potentially slower loads
        print("Locating username field...")
        username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        print("Locating password field...")
        password_field = driver.find_element(By.ID, "password")

        # Enter credentials
        print("Entering credentials...")
        username_field.send_keys(username)
        password_field.send_keys(password)

        # Find and click the login button
        print("Clicking login button...")
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']")))
        login_button.click()

        # Wait for the dashboard URL
        print("Checking for dashboard URL...")
        wait.until(EC.url_to_be("https://pms.ezderm.com/dashboard"))
        print("Login successful! Landed on dashboard: ", driver.current_url)

        # Navigate to Custom Reports page [cite: 10]
        print("Navigating to Custom Reports page...")
        driver.get("https://pms.ezderm.com/customReports")

        # Select report based on type
        report_titles = {
            "daily": "Daily Signed Off Appointments", # [cite: 11]
            "weekly": "Weekly Signed Off Appointments", # [cite: 13]
            "monthly": "Monthly Signed Off Appointments" # [cite: 15]
        }
        report_title = report_titles[report_type]
        print(f"Locating {report_title} report...")
        # Using class from the original script: styles_ChildItem__llCUk. PRD has styles_ChildItem__11CUk [cite: 11, 13, 15]
        report_div = wait.until(EC.element_to_be_clickable(
            (By.XPATH, f"//div[contains(@class, 'styles_ChildItem__llCUk') and contains(text(), '{report_title}')]")
        ))
        report_div.click()

        # Click the Generate CSV button [cite: 17]
        print("Generating CSV...")
        csv_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "[data-pendo='button-generate-csv']")
        ))
        csv_button.click()

        # Wait for the file to download
        print("Waiting for CSV download...")
        time.sleep(10) # Increased sleep time slightly for download robustness
        csv_files = glob.glob(os.path.join(download_dir, "*.csv"))
        if not csv_files:
            # Attempt to find any CSV if the pattern fails, for debugging
            all_files_in_download_dir = glob.glob(os.path.join(download_dir, "*"))
            print(f"Debug: Files in download dir ({download_dir}): {all_files_in_download_dir}")
            raise Exception(f"CSV file not found in downloads folder: {download_dir}")
        csv_file = sorted(csv_files, key=os.path.getmtime, reverse=True)[0] # Get the most recent CSV
        print(f"CSV downloaded: {csv_file}")

        # Process the CSV to extract provider counts [cite: 18]
        print("Processing CSV...")
        providers = {
            'Kayela Asplund, NP': 0, # [cite: 21]
            'Samantha Conklin, NP': 0, # [cite: 21]
            'Jonathan Hayward, PA': 0 # [cite: 21]
        }

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            # PRD suggests investigating summary rows first [cite: 19]
            # Current script logic iterates all rows and parses specific format.
            for row in reader:
                if not row or not row[0]: # Skip empty rows or rows with empty first cell
                    continue
                cell = row[0].strip()
                for provider in providers:
                    if provider in cell:
                        try:
                            # Assuming format "Provider Name: Count"
                            count_str = cell.split(":")[-1].strip()
                            count = int(count_str)
                            providers[provider] = count
                        except (ValueError, IndexError) as parse_error:
                            print(f"Warning: Could not parse count for {provider} in row: '{cell}'. Error: {parse_error}")


        # Get reporting period and email subject
        today = datetime.now(cst)
        period, period_text = get_report_period(report_type, today)
        
        # Construct subject line based on PRD format [cite: 26]
        subject_prefix = f"Lilly Derm {report_type.capitalize()} Appointment Report"
        if report_type == "daily":
            subject = f"{subject_prefix} - {today.strftime('%Y-%m-%d')}"
        elif report_type == "weekly":
            start_date_for_subject = today - timedelta(days=6)
            subject = f"{subject_prefix} - {start_date_for_subject.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}"
        elif report_type == "monthly":
            prev_month_obj = today.replace(day=1) - timedelta(days=1)
            subject = f"{subject_prefix} - {prev_month_obj.strftime('%Y-%B')}" # E.g., 2025-April
        else: # Should not happen due to earlier checks
            subject = f"{subject_prefix} - {period}"


        # Format HTML email body
        html_body = f"""
        <html>
        <body>
        <p>Hey Tony,</p>
        <p>{period_text}</p>
        <p><strong>Appointment counts:</strong></p>
        <ul>
        """ # [cite: 24, 25]
        for provider, count in providers.items():
            html_body += f"<li><b>{provider}:</b> {count} Completed Appointments</li>" # [cite: 22, 25]
        html_body += """
        </ul>
        <p>This is an automated report.</p>
        </body>
        </html>
        """

        # Send email with CSV attachment to primary client [cite: 7, 23]
        send_email(subject, html_body, "gio@gervainlabs.com", csv_file) # [cite: 26]
        print("Email sent successfully to tony@lillydermmd.com!")

        # Delete CSV for HIPAA compliance [cite: 31]
        print(f"Deleting CSV file: {csv_file}...")
        os.remove(csv_file)
        print("CSV file deleted.")

    except Exception as e:
        error_subject = "EZDERM Reporter Error"
        error_message_detail = str(e)
        current_url_info = "\nDriver not initialized or URL not available"
        page_source_info = "\nPage source not available"

        if 'driver' in locals() and driver:
            try:
                current_url_info = f"\n\nCurrent URL: {driver.current_url}"
            except: # Handle cases where driver might exist but current_url is not accessible
                current_url_info = "\nCould not retrieve current URL from driver."
            try:
                page_source_info = f"\nPage source snippet: {driver.page_source[:1000]}" # Increased snippet size
            except:
                page_source_info = "\nCould not retrieve page source from driver."
            
            error_screenshot_path = os.path.join(script_dir, "error.png")
            try:
                driver.save_screenshot(error_screenshot_path)
                print(f"Screenshot saved as {error_screenshot_path}")
            except Exception as screenshot_error:
                print(f"Failed to save screenshot: {screenshot_error}")
        
        error_body = f"An error occurred during the EZDERM report generation:\n{error_message_detail}"
        error_body += current_url_info
        error_body += page_source_info
        
        print(f"Error: {error_message_detail}")
        print(error_body) # For local log
        
        try:
            # Send error notification to system admin [cite: 8, 30]
            send_email(error_subject, error_body.replace('\n', '<br>'), "gio@gervainlabs.com") # Convert newlines to <br> for HTML email
            print("Error notification sent to gio@gervainlabs.com.")
        except Exception as email_error:
            print(f"CRITICAL: Failed to send error notification email: {email_error}")
        raise e # Re-raise for the calling process to know an error occurred
    finally:
        if 'driver' in locals() and driver:
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
        sys.exit(1) # Exit if report type is invalid

    try:
        print(f"Starting {report_type_arg.capitalize()} report generation process...")
        run_report_generation(report_type_arg)
        print(f'{report_type_arg.capitalize()} report processed successfully.')
    except Exception as main_exception:
        # The error should have been logged and emailed by run_report_generation
        # This print is for the console/cron log if the exception propagates here
        print(f"Critical error during {report_type_arg} report generation: {main_exception}")
        sys.exit(1) # Indicate failure to the calling script/cron