# Ticket Closing Automation - Setup Guide

This guide explains how to run this project in a clean Python virtual environment.

## 1) Prerequisites

- Windows PowerShell
- Python 3.13+ available via `py`

## 2) Create Virtual Environment

Run this from the project root:

```powershell
py -3.13 -m virtualenv .venv
```

## 3) Activate Virtual Environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks scripts, run once in PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again.

## 4) Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

## 5) Verify Installation

```powershell
python -m pip list
```

Expected key packages:

- `python-dotenv`
- `requests`

## 6) Run the Main Script

```powershell
python batch_processor.py
```

## 7) Exit Virtual Environment

```powershell
deactivate
```

## 8) Project Structure (Quick View)

- `batch_processor.py` - main automation flow
- `batch_queue.py` - file scanning and batch reservation
- `naming_config.py` - certificate filename parsing rules
- `requirements.txt` - Python dependencies
- `.env` - credentials/config (local only)
- `certificates/` - certificate assets
- `config/` - project configuration files
- `test-results/` - test outputs
