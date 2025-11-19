# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**P2P-2025-001-A: Automated Appointment Recovery System**

This project automates two critical workflows for Lilly Dermatology practice:

1. **Appointment Recovery System** (`recovery_system.py`) - Extracts no-show/canceled/rescheduled appointments from EZDERM PMS, posts to GoHighLevel CRM with recovery tags, triggering automated SMS campaigns
2. **Appointment Reporting System** (`main.py`) - Generates daily/weekly/monthly signed-off appointment counts by provider and sends to Zapier webhook

Both systems run on **Heroku Scheduler** as background jobs, use **Selenium WebDriver** for EZDERM web scraping (no API available), and share common infrastructure via `ezderm_common.py`.

## Architecture & Code Structure

### Three-Module Architecture

```
ezderm_common.py     → Shared automation infrastructure (reusable across both systems)
recovery_system.py   → Appointment recovery workflow (4:30 PM CST daily)
main.py             → Report generation workflow (scheduled by report type)
```

### ezderm_common.py - Shared Library

Provides 5 core capabilities reused across both automation scripts:

1. **`load_credentials()`** - Loads all environment variables (EZDERM, email, GHL)
2. **`initialize_chrome_driver(download_dir)`** - Heroku-optimized headless Chrome with custom download directory
3. **`login_to_ezderm(driver, username, password)`** - Authenticates to EZDERM PMS
4. **`wait_for_csv_download(download_dir, timeout_seconds)`** - Polls for CSV download completion
5. **`send_error_notification(error, driver, context, credentials)`** - Sends HTML email with screenshot on failures

**Key Design Pattern**: All automation scripts follow the same structure:
```python
driver = None
try:
    credentials = load_credentials()
    driver = initialize_chrome_driver("/tmp/downloads")
    login_to_ezderm(driver, credentials['ezderm_username'], credentials['ezderm_password'])
    # ... script-specific logic ...
except Exception as e:
    send_error_notification(e, driver, "Context", credentials)
finally:
    close_driver_safely(driver)
```

### recovery_system.py - Recovery Workflow

**Execution**: `python recovery_system.py` (no arguments)

**Critical Implementation Details**:

1. **CSV Parsing Anomaly**: EZDERM exports have **8 summary rows before the header** and **1 total row after data**. The `parse_recovery_csv()` function (line 56) skips first 8 rows and stops at "Total:" row.

2. **Saved Report Dependency**: Navigates to pre-configured EZDERM saved report named **"Recovery-System-Daily"** which must exist with filters: Date Range = "Today", Status = No Show + Canceled + Rescheduled via SMS

3. **GHL API Integration**: Posts to `https://services.leadconnectorhq.com/contacts/` using Private Integrations API v2.0. Tags contacts with `["Recovery-Pending", "EZDERM-Import"]` to trigger SMS workflows.

4. **Phone Validation**: Filters out records with empty phone numbers (SMS is primary recovery channel).

### main.py - Reporting Workflow

**Execution**: `python main.py <report_type>` where `<report_type>` is `daily`, `weekly`, or `monthly`

**Scheduling Logic**: Script validates day-of-week/month before running:
- **daily**: Runs Mon-Fri only (skips weekends)
- **weekly**: Runs Sundays only
- **monthly**: Runs 1st of month only

**Report Processing**: Parses CSV for provider appointment counts (Kayela Asplund, Samantha Conklin, Jonathan Hayward), sends to Zapier webhook at `ZAP_WEBHOOK_URL`.

## Running Locally

### Setup

```bash
# Create virtual environment
python3 -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env  # Create .env file
# Edit .env with actual credentials
```

### Required Environment Variables

```bash
# EZDERM PMS credentials (required for both scripts)
EZDERM_USERNAME=your_username
EZDERM_PASSWORD=your_password

# Recovery System (recovery_system.py)
GHL_API_KEY=your_ghl_private_integration_token
GHL_LOCATION_ID=tApSBFFtY2JiB9hV8LLd

# Reporting System (main.py)
ZAP_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/...

# Error Notifications (optional, both scripts)
EMAIL_ADDRESS=your_gmail@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
ADMIN_EMAIL=gio@gervainlabs.com

# Heroku provides these automatically (do not set locally):
# GOOGLE_CHROME_BIN
# CHROMEDRIVER_PATH
```

### Run Scripts Locally

```bash
# Recovery system
python recovery_system.py

# Report generation (specify type)
python main.py daily
python main.py weekly
python main.py monthly
```

**Local Testing Note**: Headless Chrome may behave differently on macOS vs Heroku Linux. Test with visible browser first:
- Comment out `chrome_options.add_argument("--headless")` in `ezderm_common.py:125`

## Heroku Deployment

### Buildpacks (must be in this order)

```bash
heroku buildpacks:add heroku/python
heroku buildpacks:add heroku-community/chrome-for-testing
heroku buildpacks:add heroku-community/chromedriver
```

### Scheduler Configuration

```bash
# Recovery system - Daily at 4:30 PM CST
python recovery_system.py

# Reporting - Each runs on its own schedule
python main.py daily    # Configured for Mon-Fri at specific time
python main.py weekly   # Configured for Sundays
python main.py monthly  # Configured for 1st of month
```

### Environment Variables

Set via `heroku config:set`:

```bash
heroku config:set EZDERM_USERNAME=xxx
heroku config:set EZDERM_PASSWORD=xxx
heroku config:set GHL_API_KEY=xxx
heroku config:set GHL_LOCATION_ID=xxx
heroku config:set ZAP_WEBHOOK_URL=xxx
heroku config:set EMAIL_ADDRESS=xxx
heroku config:set EMAIL_PASSWORD=xxx
```

### Deploy

```bash
git add .
git commit -m "Your commit message"
git push heroku main
```

### Monitor Logs

```bash
heroku logs --tail
```

## HIPAA Compliance Requirements

This system handles Protected Health Information (PHI). All code changes must maintain:

1. **No PHI in Logs**: Never log patient names, phones, MRNs, or dates of birth
   - Use generic messages like "Record {index} processed" instead of "Processed Jane Doe"
   - Error notifications use masked data or reference-by-position only

2. **Immediate File Deletion**: CSV files containing PHI must be deleted immediately after processing
   - Always call `cleanup_downloaded_files(download_dir)` in `finally` block
   - Heroku's ephemeral filesystem provides additional protection (/tmp cleared on dyno restart)

3. **HTTPS Only**: All API calls use encrypted transport
   - EZDERM: https://pms.ezderm.com
   - GHL API: https://services.leadconnectorhq.com
   - Zapier webhooks: https://hooks.zapier.com

4. **Secure Credential Handling**:
   - Never hardcode credentials in code
   - Use environment variables exclusively
   - Never log credential values (passwords are logged as "(not logged for security)")

## Common Development Scenarios

### Adding a New Provider to Report Generation

1. Edit `main.py:143-147` to add provider name to `providers_counts` dictionary
2. Ensure EZDERM custom report includes the new provider's data
3. Test with `python main.py daily` to verify parsing

### Modifying EZDERM Navigation

If EZDERM UI changes (CSS selectors, page structure):

1. **Update Selectors**: Check `recovery_system.py:249` (report div XPath) and `:256` (CSV button selector)
2. **Test with Visible Browser**: Temporarily disable headless mode to debug
3. **Screenshot on Error**: Error notifications automatically include screenshots at `/tmp/error.png`

### Changing CSV Parsing Logic

Both scripts parse EZDERM CSVs but with different structures:

- **recovery_system.py**: Patient data (8 summary rows + header + data + total row)
  - Modify `parse_recovery_csv()` function (line 56)
  - Pay attention to row skipping logic (lines 84-88)

- **main.py**: Provider summary counts (searches for "Provider Name: Count" pattern)
  - Modify CSV reading loop (lines 148-165)
  - Uses pattern matching, not column-based parsing

### Adding New GHL Custom Fields

To track additional appointment data in GoHighLevel:

1. Create custom field in GHL admin UI first
2. Add to `recovery_system.py:177-181` in `customFields` array
3. Map from CSV data in `record` dictionary (parsed at line 105)

## ISO 9001:2015 Documentation Standards

All Python files must include document control header:

```python
"""
filename.py - Brief description

Project: P2P-2025-001-A (Automated Appointment Recovery System)
Document ID: [UNIQUE-ID]
Version: X.Y.Z
Created: YYYY-MM-DD
Owner: Giovanni Boulay

Compliance:
- ISO 9001:2015 Section X.X.X (Requirement Name)
- HIPAA-minded practices (specific considerations)

Purpose:
[Detailed purpose and scope]
"""
```

## Troubleshooting

### "CSV file not found" Error

- **Cause**: Download timeout or EZDERM UI changed
- **Fix**: Check Heroku logs for detailed error message with screenshot
- **Debug**: Increase timeout in `wait_for_csv_download(timeout_seconds=120)`

### "Missing required EZDERM credentials" Error

- **Cause**: Environment variables not set
- **Fix**: Verify with `heroku config` that EZDERM_USERNAME and EZDERM_PASSWORD are set
- **Local**: Ensure `.env` file exists and is properly formatted

### "Rate limit" from GHL API

- **Cause**: Too many API requests in short period
- **Fix**: Current implementation continues on individual failures (line 196-199)
- **Monitor**: Check `failure_count` in logs for pattern of failures

### Script Exits Early on Scheduler

- **Cause**: Likely day-of-week validation (e.g., daily report on weekend)
- **Expected Behavior**: Scripts log "Skipping actual report generation" and exit 0
- **Not a Bug**: This is intentional scheduling logic (see `main.py:245-286`)

## Related Documentation

- **PRD**: `../PRD_P2P-2025-001-A_Automated_Recovery_System.md` - Product requirements
- **WBS**: `../WBS_P2P-2025-001-A_Automated_Recovery_System.md` - Work breakdown structure
- **Deployment Checklist**: `DEPLOYMENT_CHECKLIST.md` - Pre-deployment validation
- **CSV Structure**: `../P2P-2025-001 CSV STRUCTURE VALIDATION.md` - EZDERM export format details
- **Work Instruction 1.1.2**: `../P2P-2025-001-WI-1.1.2 - EZDERM Custom Report Research.md` - Report configuration guide
