## backend

### quick start

- **create conda env**: `conda env create -f environment.yaml`
- **activate**: `conda activate ideological_profiling`
- **set db env (example)**:

```bash
setx DATABASE_URL "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/ideological_profiling"
```

- **init db**:

```bash
python -m scripts.init_db
python -m scripts.generate_mock_data
```

- **run api**:

```bash
python -m api_server.app
```

