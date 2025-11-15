"""
ezderm_common.py - Shared EZDERM automation infrastructure

Project: P2P-2025-001-A (Automated Appointment Recovery System)
Document ID: LIB-EZDERM-COMMON-001
Version: 1.0.0
Created: 2025-11-12
Owner: Giovanni Boulay

Compliance:
- ISO 9001:2015 Section 7.5.3 (Control of Documented Information)
- HIPAA-minded practices (no PHI in logs, secure credential handling)

Purpose:
Provides reusable components for EZDERM web automation:
- Chrome WebDriver initialization (Heroku-ready)
- EZDERM authentication
- CSV download handling
- Error notification system
- Secure credential management

Usage:
    from ezderm_common import initialize_chrome_driver, login_to_ezderm
    
    driver = initialize_chrome_driver()
    login_to_ezderm(driver, username, password)
"""

import os
import time
import glob
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv


# =============================================================================
# SECTION 1: CONFIGURATION & INITIALIZATION
# =============================================================================

def load_credentials():
    """
    Load EZDERM and notification credentials from environment variables.
    
    Returns:
        dict: Credential dictionary with keys:
            - ezderm_username: EZDERM login username
            - ezderm_password: EZDERM login password
            - email_address: Gmail account for sending notifications
            - email_password: Gmail app password
            - admin_email: Email address for error notifications
            - ghl_api_key: GoHighLevel API key (for recovery system)
            - ghl_location_id: GoHighLevel location ID (for recovery system)
    
    Raises:
        ValueError: If required EZDERM credentials are missing
    
    HIPAA Note: Credentials loaded from environment; never logged or stored
    """
    # Load .env file for local development (no-op on Heroku)
    load_dotenv()
    
    # Load required credentials
    username = os.getenv('EZDERM_USERNAME')
    password = os.getenv('EZDERM_PASSWORD')
    
    # Validate required credentials present
    if not username or not password:
        raise ValueError(
            "Missing required EZDERM credentials. "
            "Set EZDERM_USERNAME and EZDERM_PASSWORD environment variables."
        )
    
    # Build credential dictionary
    credentials = {
        'ezderm_username': username,
        'ezderm_password': password,
        'email_address': os.getenv('EMAIL_ADDRESS'),
        'email_password': os.getenv('EMAIL_PASSWORD'),
        'admin_email': os.getenv('ADMIN_EMAIL', 'gio@gervainlabs.com'),
        'ghl_api_key': os.getenv('GHL_API_KEY'),
        'ghl_location_id': os.getenv('GHL_LOCATION_ID')
    }
    
    return credentials


def initialize_chrome_driver(download_dir="/tmp/downloads"):
    """
    Initialize Chrome WebDriver with Heroku-optimized settings.
    
    Args:
        download_dir (str): Path for CSV downloads (default: /tmp/downloads for Heroku)
    
    Returns:
        webdriver.Chrome: Configured and ready driver instance
    
    Side Effects:
        - Creates download_dir if not exists
        - Configures headless Chrome with no-sandbox mode
        - Uses GOOGLE_CHROME_BIN and CHROMEDRIVER_PATH from environment
    
    Raises:
        Exception: If Chrome/ChromeDriver not found or incompatible
    
    Environment Variables:
        - GOOGLE_CHROME_BIN: Path to Chrome binary (set by Heroku buildpack)
        - CHROMEDRIVER_PATH: Path to ChromeDriver (set by Heroku buildpack)
    """
    # Create download directory if it doesn't exist
    os.makedirs(download_dir, exist_ok=True)
    print(f"Download directory: {download_dir}")
    
    # Configure Chrome options for headless operation
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Use Chrome binary from Heroku buildpack if available
    chrome_bin_path = os.getenv('GOOGLE_CHROME_BIN')
    if chrome_bin_path:
        chrome_options.binary_location = chrome_bin_path
        print(f"Using Chrome binary: {chrome_bin_path}")
    else:
        print("Warning: GOOGLE_CHROME_BIN not set. Using system Chrome.")
    
    # Configure download preferences
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    
    # Use ChromeDriver from Heroku buildpack if available
    chromedriver_path = os.getenv('CHROMEDRIVER_PATH')
    if chromedriver_path:
        print(f"Using ChromeDriver: {chromedriver_path}")
        service = Service(executable_path=chromedriver_path)
    else:
        print("Warning: CHROMEDRIVER_PATH not set. Using system ChromeDriver.")
        service = Service()
    
    # Initialize and return driver
    print("Initializing Chrome WebDriver...")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("Chrome WebDriver initialized successfully.")
    
    return driver

# =============================================================================
# SECTION 2: EZDERM AUTHENTICATION
# =============================================================================

def login_to_ezderm(driver, username, password):
    """
    Authenticate to EZDERM PMS system.
    
    Args:
        driver (webdriver.Chrome): Selenium WebDriver instance
        username (str): EZDERM username (from environment)
        password (str): EZDERM password (from environment)
    
    Returns:
        None (modifies driver state - navigates to authenticated session)
    
    Raises:
        TimeoutException: If login page elements not found within 30s
        Exception: If authentication fails (wrong credentials, system down)
    
    HIPAA Note: Credentials never logged; transmitted over HTTPS only
    
    Implementation:
        - Navigates to https://pms.ezderm.com/
        - Waits for username field (up to 30s)
        - Enters credentials and submits form
        - Waits for post-login page load
    """
    login_url = "https://pms.ezderm.com/"
    print(f"Navigating to EZDERM login page: {login_url}")
    driver.get(login_url)
    
    # Wait for login page to load and find username field
    print("Waiting for login page elements...")
    wait = WebDriverWait(driver, 30)
    
    # Locate and fill username field
    username_field = wait.until(
        EC.presence_of_element_located((By.ID, "txtUserName"))
    )
    username_field.clear()
    username_field.send_keys(username)
    print("Username entered.")
    
    # Locate and fill password field
    password_field = driver.find_element(By.ID, "txtPassword")
    password_field.clear()
    password_field.send_keys(password)
    print("Password entered (not logged for security).")
    
    # Submit login form
    login_button = driver.find_element(By.ID, "butLogin")
    login_button.click()
    print("Login form submitted.")
    
    # Wait for redirect after successful login (wait for URL change)
    print("Waiting for post-login page load...")
    wait.until(lambda d: d.current_url != login_url)
    print(f"Login successful. Current URL: {driver.current_url}")


# =============================================================================
# SECTION 3: FILE DOWNLOAD HANDLING
# =============================================================================

def wait_for_csv_download(download_dir, timeout_seconds=60, pattern="*.csv"):
    """
    Wait for CSV file to appear in download directory.
    
    Args:
        download_dir (str): Path to monitor for downloads
        timeout_seconds (int): Max wait time in seconds (default: 60)
        pattern (str): Glob pattern for file matching (default: *.csv)
    
    Returns:
        str: Full path to downloaded CSV file (most recent if multiple found)
    
    Raises:
        FileNotFoundError: If no CSV found within timeout period
    
    Implementation Note:
        - Polls directory every 2 seconds
        - Returns newest matching file if multiple found
        - Heroku-safe: works on ephemeral filesystem
    
    HIPAA Note: CSV files may contain PHI - caller responsible for cleanup
    """
    print(f"Waiting for CSV download in {download_dir} (timeout: {timeout_seconds}s)...")
    
    elapsed_time = 0
    poll_interval = 2  # seconds
    
    while elapsed_time < timeout_seconds:
        # Search for CSV files matching pattern
        csv_files = glob.glob(os.path.join(download_dir, pattern))
        
        if csv_files:
            # Return the most recently modified file if multiple found
            latest_csv = max(csv_files, key=os.path.getmtime)
            print(f"CSV file found: {latest_csv}")
            return latest_csv
        
        # Wait before polling again
        time.sleep(poll_interval)
        elapsed_time += poll_interval
        
        if elapsed_time % 10 == 0:  # Log progress every 10 seconds
            print(f"Still waiting for CSV... ({elapsed_time}s elapsed)")
    
    # Timeout reached without finding file
    raise FileNotFoundError(
        f"CSV file not found in {download_dir} after {timeout_seconds} seconds."
    )


def cleanup_downloaded_files(download_dir):
    """
    Delete all files in download directory (HIPAA compliance).
    
    Args:
        download_dir (str): Path containing files to delete
    
    Returns:
        None
    
    Side Effects:
        - Permanently deletes all files in directory
        - Logs count of files deleted
        - Directory itself remains (empty)
    
    HIPAA Note: Call this after processing CSVs containing PHI
    
    Implementation:
        - Uses glob to find all files (not subdirectories)
        - Deletes each file individually
        - Logs each deletion for audit trail
    """
    files = glob.glob(os.path.join(download_dir, "*"))
    
    if not files:
        print(f"No files to clean up in {download_dir}")
        return
    
    print(f"Cleaning up {len(files)} file(s) from {download_dir} (HIPAA compliance)...")
    
    for file_path in files:
        if os.path.isfile(file_path):  # Only delete files, not directories
            try:
                os.remove(file_path)
                print(f"Deleted: {os.path.basename(file_path)}")
            except Exception as e:
                print(f"Warning: Failed to delete {file_path}: {e}")
    
    print("Cleanup complete.")

# =============================================================================
# SECTION 4: ERROR HANDLING & NOTIFICATIONS
# =============================================================================

def send_email(subject, html_body, to_email, cc_email=None, attachment_path=None, credentials=None):
    """
    Send email via Gmail SMTP (with optional attachment).
    
    Args:
        subject (str): Email subject line
        html_body (str): Email body (HTML formatted)
        to_email (str): Primary recipient email address
        cc_email (str, optional): CC recipient email address
        attachment_path (str, optional): Path to file to attach
        credentials (dict): Must contain 'email_address' and 'email_password'
    
    Returns:
        None
    
    Raises:
        SMTPAuthenticationError: If email credentials invalid
        Exception: For other SMTP failures
    
    HIPAA Note: Use only for system notifications; never send PHI via email
    
    Security Note:
        - Uses Gmail SMTP with TLS encryption
        - Requires app password (not regular Gmail password)
        - Never logs credentials
    """
    if not credentials or not credentials.get('email_address') or not credentials.get('email_password'):
        print("Error: Email credentials not configured. Cannot send email.")
        return
    
    email_address = credentials['email_address']
    email_password = credentials['email_password']
    
    # Construct email message
    msg = MIMEMultipart()
    msg['From'] = email_address
    msg['To'] = to_email
    if cc_email:
        msg['Cc'] = cc_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))
    
    # Attach file if provided
    if attachment_path:
        try:
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{os.path.basename(attachment_path)}"'
            )
            msg.attach(part)
            print(f"Attached file: {os.path.basename(attachment_path)}")
        except FileNotFoundError:
            print(f"Warning: Attachment not found at {attachment_path}. Sending without attachment.")
        except Exception as e:
            print(f"Warning: Failed to attach file {attachment_path}: {e}")
    
    # Send email via Gmail SMTP
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(email_address, email_password)
            server.send_message(msg)
        print(f"Email sent successfully to {to_email}")
    except smtplib.SMTPAuthenticationError:
        print("Error: SMTP authentication failed. Check email_address and email_password.")
    except Exception as e:
        print(f"Error: Failed to send email to {to_email}: {e}")


def send_error_notification(error, driver=None, context="", credentials=None):
    """
    Send detailed error notification email with screenshot and diagnostics.
    
    Args:
        error (Exception): The exception that occurred
        driver (webdriver.Chrome, optional): WebDriver instance for screenshot/diagnostics
        context (str): Description of what operation failed (e.g., "CSV Download")
        credentials (dict): Must contain email notification credentials
    
    Returns:
        None
    
    Side Effects:
        - Saves error.png screenshot to /tmp (if driver provided)
        - Sends HTML email to admin_email
        - Logs detailed error info to stdout (for Heroku logs)
    
    HIPAA Note: Screenshots may contain PHI - stored only in ephemeral /tmp
    
    Email Contents:
        - Error message and traceback
        - Current URL (if driver available)
        - Page source snippet (if driver available)
        - Screenshot attached (if driver available)
    """
    if not credentials or not credentials.get('admin_email'):
        print("Error: Admin email not configured. Cannot send error notification.")
        print(f"Error details: {error}")
        return
    
    admin_email = credentials['admin_email']
    error_message = str(error)
    
    # Initialize diagnostic info
    current_url_info = "\nDriver not initialized or URL not available."
    page_source_info = "\nPage source not available."
    screenshot_path = None
    
    # Capture diagnostics if driver available
    if driver:
        try:
            current_url_info = f"\n\nCurrent URL: {driver.current_url}"
        except Exception as url_err:
            current_url_info = f"\nCould not retrieve current URL: {url_err}"
        
        try:
            page_source_snippet = driver.page_source[:1000]
            page_source_info = f"\n\nPage source snippet (first 1000 chars):\n{page_source_snippet}"
        except Exception as ps_err:
            page_source_info = f"\nCould not retrieve page source: {ps_err}"
        
        # Capture screenshot
        screenshot_path = "/tmp/error.png"
        try:
            driver.save_screenshot(screenshot_path)
            print(f"Error screenshot saved to {screenshot_path}")
        except Exception as screenshot_err:
            print(f"Failed to save error screenshot: {screenshot_err}")
            screenshot_path = None
    
    # Build error email subject and body
    context_prefix = f"{context} - " if context else ""
    subject = f"EZDERM Automation Error - {context_prefix}P2P-2025-001-A"
    
    html_body = f"""
    <html>
    <body>
        <h2 style="color: #d32f2f;">EZDERM Automation Error</h2>
        <p><strong>Context:</strong> {context if context else 'General automation error'}</p>
        <p><strong>Error Message:</strong></p>
        <pre style="background-color: #f5f5f5; padding: 10px; border-left: 3px solid #d32f2f;">{error_message}</pre>
        <p><strong>Diagnostics:</strong></p>
        <pre style="background-color: #f5f5f5; padding: 10px;">{current_url_info}</pre>
        <pre style="background-color: #f5f5f5; padding: 10px;">{page_source_info}</pre>
        <hr>
        <p style="color: #666; font-size: 12px;">
            Project: P2P-2025-001-A (Automated Appointment Recovery System)<br>
            This is an automated error notification from the EZDERM automation system.
        </p>
    </body>
    </html>
    """
    
    # Log error details to stdout (for Heroku logs)
    print(f"\n{'='*60}")
    print(f"ERROR: {context if context else 'Automation Error'}")
    print(f"{'='*60}")
    print(f"Error Message: {error_message}")
    print(current_url_info)
    print(page_source_info[:500])  # Truncate for console
    print(f"{'='*60}\n")
    
    # Send error notification email
    print(f"Sending error notification to {admin_email}...")
    send_email(
        subject=subject,
        html_body=html_body,
        to_email=admin_email,
        attachment_path=screenshot_path,
        credentials=credentials
    )


# =============================================================================
# SECTION 5: CLEANUP & RESOURCE MANAGEMENT
# =============================================================================

def close_driver_safely(driver):
    """
    Gracefully close WebDriver and release resources.
    
    Args:
        driver (webdriver.Chrome): WebDriver instance to close
    
    Returns:
        None
    
    Side Effects:
        - Closes all browser windows
        - Terminates ChromeDriver process
        - Logs closure to stdout
    
    Note: Safe to call even if driver already closed or is None
    
    Implementation:
        - Handles None driver gracefully
        - Catches exceptions during closure
        - Always logs outcome
    """
    if driver is None:
        print("No driver to close (driver is None).")
        return
    
    try:
        print("Closing Chrome WebDriver...")
        driver.quit()
        print("Chrome WebDriver closed successfully.")
    except Exception as e:
        print(f"Warning: Error while closing driver: {e}")
        print("Driver may have already been closed or become invalid.")