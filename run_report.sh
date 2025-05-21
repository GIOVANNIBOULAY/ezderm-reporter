#!/bin/bash
echo "$(date): Starting run_report.sh $1" >> /Users/giovan/Desktop/PROJECTS/ezderm-reporter/cron.log
source /Users/giovan/Desktop/PROJECTS/ezderm-reporter/env/bin/activate
/Users/giovan/Desktop/PROJECTS/ezderm-reporter/env/bin/python3 /Users/giovan/Desktop/PROJECTS/ezderm-reporter/main.py $1 >> /Users/giovan/Desktop/PROJECTS/ezderm-reporter/cron.log 2>&1
deactivate
echo "$(date): Finished run_report.sh $1" >> /Users/giovan/Desktop/PROJECTS/ezderm-reporter/cron.log
