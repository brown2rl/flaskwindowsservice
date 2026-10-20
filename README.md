# Flask Windows Service

A small Flask application that can run directly as a web server or be installed
and managed as a Windows service.

## Requirements

- Python 3
- Windows for Windows Service installation and management

Install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Configuration

The server reads the following environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `INTRANET_IP` | `0.0.0.0` | Address the HTTP server binds to |
| `PORT` | `5000` | HTTP server port |
| `SERVICE_NAME` | `DefaultService` | Windows service name |
| `SERVICE_DESCRIPTION` | `FlaskServerService` | Windows service description |
| `LOG_LEVEL` | `INFO` | Python logging level |

For local runs, `INTRANET_IP` and `PORT` can be placed in a `.env` file beside
`flask_windows_service.py`. The application loads that file when it creates the
Flask app. `SERVICE_NAME`, `SERVICE_DESCRIPTION`, and `LOG_LEVEL` are read when
the module is imported, so configure those in the process or system environment
before starting the service.

## Run locally

Start the Flask development server:

```powershell
python flask_windows_service.py
```

The `GET /` endpoint returns JSON with the service name and status:

```json
{"service": "auth", "status": "running"}
```

## Install as a Windows service

Open PowerShell as Administrator, set any desired service configuration in the
environment, and run:

```powershell
python flask_windows_service.py install
python flask_windows_service.py start
```

Manage the service using the same script:

```powershell
python flask_windows_service.py stop
python flask_windows_service.py remove
```

The service binds to the configured `INTRANET_IP` and `PORT`. Service logs are
written to `service.log` beside the Python script when running as a service or
in service debug mode.
