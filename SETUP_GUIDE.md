# Ticket Closing Automation - Setup Guide

This guide is written for a beginner and explains how to set up the project, run it safely, and use the unified ticket status update command.

## 1) What you need

Before starting, make sure you have:

- Windows PowerShell
- Python 3.13+ installed
- Access to the project folder
- Valid API credentials in the environment or `.env` file if you want to update live tickets

## 2) Open the project folder

Open PowerShell in the project folder.

Example:

```powershell
cd "C:\path\to\Ticket_Automation"
```

## 3) Create a Python virtual environment

This keeps the project dependencies isolated.

```powershell
py -3.13 -m virtualenv .venv
```

## 4) Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks scripts, run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again.

## 5) Install dependencies

```powershell
python -m pip install -r requirements.txt
```

## 6) Verify the setup

```powershell
python -m pip list
```

You should see packages such as:

- `python-dotenv`
- `requests`

## 7) Understand the main files

Here is a quick overview:

- `batch_processor.py` - main ticket processing flow
- `batch_queue.py` - job scanning and queue handling
- `rto_approval_processor.py` - RTO-related processing flow
- `ticket_status_cli.py` - unified command-line tool for updating ticket status
- `chassis_list.txt` - sample chassis numbers you can use for bulk updates
- `requirements.txt` - required Python packages
- `.env` - local credentials and configuration
- `logs/` - daily processing logs
- `reports/` - generated reports

## 8) Run the original batch workflow

If you want to run the normal processing flow:

```powershell
python batch_processor.py
```

## 9) Use the unified ticket status update command

You no longer need separate scripts for different actions. Use one command and pass the chassis and desired status.

### 9.1 Update one chassis

```powershell
python ticket_status_cli.py --chassis MAT805021TFD05775 --status-code STS_CO_17
```

### 9.2 Update many chassis from a file

```powershell
python ticket_status_cli.py --chassis-file chassis_list.txt --status-code STS_CO_18
```

### 9.3 Preview without making changes

Use `--dry-run` to check what would happen without updating the ticket.

```powershell
python ticket_status_cli.py --chassis MAT805021TFD05775 --status-code STS_CO_17 --dry-run
```

### 9.4 Friendly status names

You can also use friendly names instead of raw codes:

```powershell
python ticket_status_cli.py --chassis MAT805021TFD05775 --status close
```

Supported friendly values include:

- `close`
- `on-hold`
- `rto-hold`
- `started`
- `completed`
- `cancel`

### 9.5 Common status codes

These are the most common codes you may use:

- `STS_CO_17` - On Hold Due to Waiting for RTO Approval
- `STS_CO_18` - Ticket Completed and Closed
- `STS_CO_20` - Ticket Cancelled
- `STS_CO_06` - Completed

## 10) Exit the virtual environment

When you are done:

```powershell
deactivate
```

## 11) Troubleshooting

If something does not work:

- Make sure the virtual environment is activated
- Make sure Python is installed and available as `python`
- Check that the required packages are installed
- Check your credentials in `.env` or the environment variables
- For a safe test, always try `--dry-run` first
