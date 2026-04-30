@echo off
echo Registering Qandle scheduled tasks...

schtasks /create /tn "Qandle Clock In"  /xml "D:\local\qandle_clocker\task_clock_in.xml"  /f
schtasks /create /tn "Qandle Clock Out" /xml "D:\local\qandle_clocker\task_clock_out.xml" /f

echo.
echo Done. Tasks registered:
schtasks /query /tn "Qandle Clock In"
schtasks /query /tn "Qandle Clock Out"
pause
