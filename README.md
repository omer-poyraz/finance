.\.venv\Scripts\python.exe -m uvicorn main:app --reload

# Finance Intelligence Engine

Professional Python project scaffold for a modular BIST analysis engine.

## First Setup

1. Open the project folder in VS Code.
2. Create a virtual environment:

   ```powershell
   python -m venv .venv
   ```

3. Install dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Create your `.env` file if it does not exist and set database values.

## First Run

Use FastAPI through Uvicorn. Do not run the project with `python main.py`.

```powershell
uvicorn main:app --reload
```

Or:

```powershell
python -m uvicorn main:app --reload
```

## VS Code Workflow

- The workspace automatically points Python to `.venv`.
- Press `F5` to start the app with the debug launcher.
- Use `Terminal -> Run Task -> Start Project` to start the service from tasks.

## Notes

- The application entrypoint is the FastAPI app exposed as `main:app`.
- Stage 1 only prepares the project infrastructure.
- Collector, analyzer, decision, database, and scheduler business logic will be added in later stages.
