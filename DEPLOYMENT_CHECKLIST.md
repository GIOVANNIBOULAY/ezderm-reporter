# P2P-2025-001-A Deployment Checklist
   
   **Project:** Automated Appointment Recovery System  
   **Document ID:** DEPLOY-P2P-2025-001-A  
   **Version:** 1.0.0  
   **Date:** 2025-11-13  
   **Owner:** Giovanni Boulay
   
   ## Pre-Deployment Verification
   
   ### Code Quality Gates (ISO 9001:2015 Section 8.6)
   - [ ] All Python files pass `py_compile` syntax validation
   - [ ] Zero TODOs remaining in codebase
   - [ ] Import tests successful for all modules
   - [ ] HIPAA compliance verified (no PHI in logs)
   - [ ] Error handling tested (try/except/finally structure)
   - [ ] Document control headers present (Doc ID, Version, Owner)
   
   ### Environment Configuration
   - [ ] `.env` file contains all required variables:
     - EZDERM_USERNAME
     - EZDERM_PASSWORD
     - GHL_API_KEY
     - GHL_LOCATION_ID
     - EMAIL_ADDRESS (optional - for error notifications)
     - EMAIL_PASSWORD (optional - for error notifications)
     - ADMIN_EMAIL (optional - defaults to gio@gervainlabs.com)
   
   ### Heroku Configuration
   - [ ] Buildpacks installed in order:
     1. `heroku/python`
     2. `heroku-community/chrome-for-testing`
     3. `heroku-community/chromedriver`
   - [ ] Environment variables set via `heroku config:set`
   - [ ] Scheduler job configured: `python3 recovery_system.py` at 4:30 PM CST daily
   
   ### EZDERM Prerequisites
   - [ ] Saved report "Recovery-System-Daily" exists in EZDERM
   - [ ] Report filters configured: Date Range = "Today", Status = No Show + Canceled + Rescheduled via SMS
   - [ ] EZDERM credentials valid and tested
   
   ### GoHighLevel Prerequisites
   - [ ] API key has `contacts.write` permission
   - [ ] Location ID confirmed: `tApSBFFtY2JiB9hV8LLd`
   - [ ] Custom fields created in GHL:
     - appointment_date
     - appointment_status
     - import_date
   - [ ] SMS recovery workflow configured to trigger on "Recovery-Pending" tag
   
   ## Deployment Steps
   
   1. **Git Commit:**
```bash
      git add recovery_system.py ezderm_common.py main.py DEPLOYMENT_CHECKLIST.md
      git commit -m "P2P-2025-001-A: Implement recovery system v1.0.1"
```
   
   2. **Push to Heroku:**
```bash
      git push heroku main
```
   
   3. **Verify Deployment:**
```bash
      heroku logs --tail
```
   
   4. **Test Scheduler:**
```bash
      heroku run python3 recovery_system.py
```
   
   ## Post-Deployment Monitoring
   
   - [ ] First automated run completes successfully (check logs)
   - [ ] GHL contacts created with correct tags
   - [ ] SMS recovery workflow triggers
   - [ ] No error notification emails received
   - [ ] CSV cleanup verified (check `/tmp/downloads` empty after run)
   
   ## Rollback Plan (if needed)
   
   1. **Disable Scheduler:**
```bash
      heroku addons:open scheduler
      # Delete or disable "python3 recovery_system.py" job
```
   
   2. **Revert Code:**
```bash
      git revert HEAD
      git push heroku main
```
   
   3. **Notify Stakeholders:**
      - Tony Jackson (practice owner)
      - Marion (office manager)
      - Document incident in ISO 9001 corrective action log
   
   ## Success Criteria
   
   - [ ] Zero defects in first 3 production runs
   - [ ] >95% of valid records successfully posted to GHL
   - [ ] SMS recovery workflows trigger within 5 minutes of import
   - [ ] No PHI exposure incidents
   - [ ] System runs within 2-minute execution time budget