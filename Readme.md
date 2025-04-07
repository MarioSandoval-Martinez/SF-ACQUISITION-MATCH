# DupCheck-Acquisition

## Overview
**DupCheck-Acquisition** is a Python script designed to identify duplicate accounts by comparing acquisition data against Salesforce records. This helps ensure data integrity and prevents redundant entries in the CRM.

## Features
- Matches acquisition data against Salesforce records
- Identifies potential duplicates based on defined criteria
- Outputs results in a structured format for review

## Requirements
- Python 3.x
- Required dependencies (install via `pip install -r requirements.txt`)

## Installation
1. Clone the repository:  
   ```sh
   git clone https://github.com/yourusername/DupCheck-Acquisition.git
   cd DupCheck-Acquisition
   ```
2. Create a virtual environment (optional but recommended):  
   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
3. Install dependencies:  
   ```sh
   pip install -r requirements.txt
   ```

## Usage
Run the script with:  
```sh
python dup_check.py
```

Modify `config.json` (if applicable) to adjust matching rules.

## .gitignore
Below is a recommended `.gitignore` file for this project:

```
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Virtual environment
venv/
.env/
*.env

# Distribution / packaging
build/
dist/
*.egg-info/

# Jupyter Notebook checkpoints
.ipynb_checkpoints/

# Logs and databases
*.log
*.sqlite3

# VS Code settings
.vscode/
.settings/

# Mac system files
.DS_Store

# Pip dependency files
pip-log.txt
pip-delete-this-directory.txt
```

## Contributing
Feel free to submit issues or pull requests to improve the script.

## License

