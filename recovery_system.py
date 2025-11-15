"""
recovery_system.py - EZDERM Appointment Recovery Automation

Project: P2P-2025-001-A (Automated Appointment Recovery System)
Document ID: SYS-RECOVERY-001
Version: 1.0.1
Change Log:
    - 2025-11-13: v1.0.0 - Initial skeleton structure (Steps 5.1-5.2)
    - 2025-11-13: v1.0.1 - Complete implementation (Steps 5.3-5.6)
    Created: 2025-11-13
Created: 2025-11-13
Owner: Giovanni Boulay

Compliance:
- ISO 9001:2015 Section 8.5.2 (Production and Service Provision)
- HIPAA-minded practices (minimal PHI, masked logs, HTTPS only)

Purpose:
Extracts no-show/canceled/rescheduled appointments from EZDERM saved report,
filters valid phone numbers, posts to GoHighLevel CRM for SMS recovery workflow.

Dependencies:
- ezderm_common.py (shared automation infrastructure)
- GoHighLevel Private Integrations API v2.0
- EZDERM saved report: "Recovery-System-Daily"

Execution:
- Local testing: python3 recovery_system.py
- Heroku Scheduler: Daily at 4:30 PM CST
"""

import sys
import os
import csv
import requests
from datetime import datetime
import pytz
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import shared EZDERM automation library
from ezderm_common import (
    load_credentials,
    initialize_chrome_driver,
    login_to_ezderm,
    wait_for_csv_download,
    cleanup_downloaded_files,
    send_error_notification,
    close_driver_safely
)

# Client timezone for scheduling and logging
CST = pytz.timezone("America/Chicago")

def parse_recovery_csv(csv_file_path):
    """
    Parse EZDERM recovery CSV with special handling for summary rows.
    
    EZDERM CSV Structure (from WI 1.1.2):
    - Rows 1-8: Summary information (SKIP)
    - Row 9: Header row (First Name, Last Name, Phone, Date of Birth, etc.)
    - Rows 10+: Appointment data
    - Last row: Totals (contains "Total:" in first column)
    
    Args:
        csv_file_path (str): Path to downloaded CSV file
    
    Returns:
        list: Valid appointment records as dictionaries
                [{'first_name': 'Jane', 'last_name': 'Doe', 'phone': '5551234567', ...}, ...]
    
    HIPAA Note: No PHI logged; only counts reported
    """
    valid_records = []
    skipped_empty_phone = 0
    
    print(f"Parsing CSV: {os.path.basename(csv_file_path)}...")
    
    with open(csv_file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        
        # Skip first 8 summary rows
        for _ in range(8):
            next(reader)
        
        # Row 9 is the header
        header = next(reader)
        print(f"CSV header columns: {len(header)} columns detected")
        
        # Parse data rows
        for row_index, row in enumerate(reader, start=10):  # Start counting from row 10
            # Stop if we hit the totals row
            if row and row[0].strip().startswith("Total:"):
                print(f"Reached totals row at line {row_index}. Stopping parse.")
                break
            
            # Skip empty rows
            if not row or not any(row):
                continue
            
            # Build dictionary from row (assuming standard column order)
            # Column indices based on typical EZDERM export
            try:
                record = {
                    'first_name': row[0].strip() if len(row) > 0 else '',
                    'last_name': row[1].strip() if len(row) > 1 else '',
                    'phone': row[2].strip() if len(row) > 2 else '',
                    'date_of_birth': row[3].strip() if len(row) > 3 else '',
                    'appointment_date': row[4].strip() if len(row) > 4 else '',
                    'appointment_status': row[5].strip() if len(row) > 5 else '',
                }
                
                # Filter: Reject records with empty phone
                if not record['phone']:
                    skipped_empty_phone += 1
                    continue
                
                valid_records.append(record)
                
            except IndexError as e:
                print(f"Warning: Row {row_index} has unexpected format. Skipping. Error: {e}")
                continue
    
    print(f"Parsing complete: {len(valid_records)} valid records, {skipped_empty_phone} skipped (empty phone)")
    
    return valid_records

def post_to_ghl_api(records, credentials):
    """
    Post appointment records to GoHighLevel CRM via Private Integrations API v2.0.
    
    API Endpoint: POST https://services.leadconnectorhq.com/contacts/
    Authentication: Bearer token (GHL_API_KEY)
    
    Args:
        records (list): Appointment records from parse_recovery_csv()
        credentials (dict): Must contain 'ghl_api_key' and 'ghl_location_id'
    
    Returns:
        tuple: (success_count, failure_count)
    
    HIPAA Note: Transmits only necessary fields over HTTPS; no PHI logged
    
    Implementation:
    - Creates/updates contact in GHL using phone as unique identifier
    - Tags contact with "Recovery-Pending" for workflow triggering
    - Handles API errors gracefully (continues on individual failures)
    """
    api_key = credentials.get('ghl_api_key')
    location_id = credentials.get('ghl_location_id')
    
    if not api_key or not location_id:
        print("ERROR: GHL_API_KEY or GHL_LOCATION_ID not configured. Cannot post to GHL.")
        return (0, len(records))
    
    api_url = "https://services.leadconnectorhq.com/contacts/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"  # GHL API version
    }
    
    success_count = 0
    failure_count = 0
    
    print(f"Posting {len(records)} records to GoHighLevel API...")
    
    for index, record in enumerate(records, start=1):
        # Build API payload (minimal PHI - only what's needed for recovery)
        payload = {
            "firstName": record['first_name'],
            "lastName": record['last_name'],
            "phone": record['phone'],
            "locationId": location_id,
            "tags": ["Recovery-Pending", "EZDERM-Import"],
            "customFields": [
                {"key": "appointment_date", "value": record.get('appointment_date', '')},
                {"key": "appointment_status", "value": record.get('appointment_status', '')},
                {"key": "import_date", "value": datetime.now(CST).strftime('%Y-%m-%d')}
            ]
        }
        
        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=10)
            
            if response.status_code in [200, 201]:
                success_count += 1
                if index % 10 == 0:  # Progress log every 10 records
                    print(f"Progress: {index}/{len(records)} posted...")
            else:
                failure_count += 1
                # Log error without PHI (no names/phones in logs)
                print(f"Warning: Record {index} failed. Status {response.status_code}: {response.text[:100]}")
                
        except requests.RequestException as e:
            failure_count += 1
            print(f"Warning: Record {index} failed due to network error: {e}")
            continue
    
    print(f"GHL API posting complete: {success_count} success, {failure_count} failures")
    
    return (success_count, failure_count)

def main():
    """
    Main execution function for recovery system.
    
    Workflow:
    1. Initialize Chrome WebDriver
    2. Login to EZDERM
    3. Navigate to saved report "Recovery-System-Daily"
    4. Generate and download CSV
    5. Parse CSV (skip 8 summary rows, filter empty Phone)
    6. Post valid records to GoHighLevel API
    7. Cleanup CSV (HIPAA compliance)
    
    Returns:
        int: Exit code (0 = success, 1 = failure)
    """
    driver = None
    
    try:
        print(f"[{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S %Z')}] Starting recovery system...")
        
        # Load credentials from environment
        credentials = load_credentials()
        
        # Initialize Chrome driver for Heroku/local compatibility
        download_dir = "/tmp/downloads"
        print(f"Initializing Chrome driver (download dir: {download_dir})...")
        driver = initialize_chrome_driver(download_dir)
        print("Chrome driver initialized.")
        
        # Authenticate to EZDERM PMS
        print("Logging in to EZDERM...")
        login_to_ezderm(driver, credentials['ezderm_username'], credentials['ezderm_password'])
        print("EZDERM login successful.")

        # Navigate to Custom Reports page
        print("Navigating to Custom Reports...")
        driver.get("https://pms.ezderm.com/customReports")
        
        # Locate and click the saved "Recovery-System-Daily" report
        report_title = "Recovery-System-Daily"
        print(f"Locating saved report: '{report_title}'...")
        
        wait = WebDriverWait(driver, 30)
        report_div_xpath = f"//div[contains(@class, 'styles_ChildItem__llCUk') and contains(text(), '{report_title}')]"
        report_div = wait.until(EC.element_to_be_clickable((By.XPATH, report_div_xpath)))
        report_div.click()
        print(f"Clicked on '{report_title}' report.")
        
        # Click "Generate CSV" button
        print("Generating CSV export...")
        csv_button_selector = "[data-pendo='button-generate-csv']"
        csv_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, csv_button_selector)))
        csv_button.click()
        print("CSV generation initiated.")
        
        # Wait for CSV download (using shared library function)
        print(f"Waiting for CSV download to {download_dir}...")
        csv_file_path = wait_for_csv_download(download_dir, timeout_seconds=60)
        print(f"CSV downloaded successfully: {csv_file_path}")
        
        appointment_records = parse_recovery_csv(csv_file_path)
           
        if not appointment_records:
            print("No valid appointment records found. Skipping GHL API posting.")
            cleanup_downloaded_files(download_dir)
            return 0
        
        print(f"Prepared {len(appointment_records)} records for GHL API posting.")
        
        success_count, failure_count = post_to_ghl_api(appointment_records, credentials)
           
        if failure_count > 0:
            print(f"WARNING: {failure_count} records failed to post to GHL. Check logs for details.")
        
        if success_count == 0:
            print("ERROR: No records successfully posted to GHL. Investigation required.")
        
        # Cleanup CSV files (HIPAA compliance - delete PHI from filesystem)
        cleanup_downloaded_files(download_dir)
        
        print("Recovery system completed successfully.")
        return 0
        
    except Exception as e:
        # Detailed error notification with screenshot
        print(f"CRITICAL ERROR: {e}")
        send_error_notification(
            error=e,
            driver=driver,
            context="Recovery System Execution",
            credentials=credentials if 'credentials' in locals() else None
        )
        return 1
        
    finally:
        # Always close driver safely
        close_driver_safely(driver)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)