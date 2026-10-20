import logging
import os
import sys
import threading


def create_app():
    """Create the Flask app and register its status route."""
    from dotenv import load_dotenv
    from flask import Flask, jsonify

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    app = Flask(__name__)

    @app.get("/")
    def index():
        """Return the service name and running status."""
        return jsonify({"service": "auth", "status": "running"})

    return app


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def get_server_address():
    """Return the host and port used by both development and service servers."""
    return os.getenv("INTRANET_IP", "0.0.0.0"), int(os.getenv("PORT", "5000"))


def configure_service_logging():
    handler = logging.FileHandler(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "service.log"),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


if os.name == "nt":
    try:
        import servicemanager
        import win32event
        import win32service
        import win32serviceutil
    except ImportError:
        servicemanager = None
        win32event = None
        win32service = None
        win32serviceutil = None
else:
    servicemanager = None
    win32event = None
    win32service = None
    win32serviceutil = None


running_as_service = (
    servicemanager is not None
    and getattr(servicemanager, "RunningAsService", lambda: False)()
)
running_in_service_debug = (
    win32serviceutil is not None
    and len(sys.argv) > 1
    and sys.argv[1].lower() == "-debug"
)
if running_as_service or running_in_service_debug:
    configure_service_logging()
    logging.info(
        "Service module imported; RunningAsService=%s, service_debug=%s",
        running_as_service,
        running_in_service_debug,
    )
app = None


if win32serviceutil is not None:
    class FlaskWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_ = os.getenv("SERVICE_NAME", "DefaultService")
        _svc_display_name_ = "Digital Enzyme auth service"
        _svc_description_ = os.getenv(
            "SERVICE_DESCRIPTION",
            "FlaskServerService",
        )

        def __init__(self, args):
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.server_ready = threading.Event()
            self.http_server = None
            self.server_thread = None
            self.server_error = None

        def SvcRun(self):
            logging.info("SvcRun entered")
            try:
                super().SvcRun()
            except Exception:
                logging.exception("SvcRun failed")
                raise

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            logging.info("SvcDoRun entered")
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)

            def start_server():
                global app
                try:
                    logging.info("Starting Flask server thread")
                    app = create_app()
                    host, port = get_server_address()
                    logging.info("Creating Flask app for %s:%s", host, port)
                    from werkzeug.serving import make_server

                    self.http_server = make_server(host, port, app, threaded=True)
                    logging.info("Flask server bound to %s:%s", host, port)
                    self.server_ready.set()
                    self.http_server.serve_forever()
                except Exception as error:
                    self.server_error = error
                    logging.exception("Flask server thread failed")
                finally:
                    self.server_ready.set()

            try:
                logging.info("Windows service starting")
                self.server_thread = threading.Thread(
                    target=start_server,
                    name="DigitalEnzymeFlaskServer",
                )
                self.server_thread.start()
                self.server_ready.wait()
                if self.server_error is not None:
                    raise RuntimeError(
                        f"Could not start Flask server: {self.server_error}"
                    ) from self.server_error

                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, ""),
                )

                while self.server_thread.is_alive():
                    result = win32event.WaitForSingleObject(self.stop_event, 1000)
                    if result == win32event.WAIT_OBJECT_0:
                        break
                else:
                    if self.server_error is not None:
                        raise RuntimeError(
                            f"Flask server stopped unexpectedly: {self.server_error}"
                        ) from self.server_error
                    raise RuntimeError("The Flask server stopped unexpectedly")

                if not self.server_thread.is_alive():
                    if self.server_error is not None:
                        raise RuntimeError(
                            f"Flask server stopped unexpectedly: {self.server_error}"
                        ) from self.server_error
                    raise RuntimeError("The Flask server stopped unexpectedly")
            except Exception as error:
                logging.exception("Windows service failed")
                servicemanager.LogErrorMsg(
                    f"{self._svc_name_} failed: {error}"
                )
                raise
            finally:
                if self.http_server is not None:
                    if self.server_thread is not None and self.server_thread.is_alive():
                        self.http_server.shutdown()
                        self.server_thread.join()
                    self.http_server.server_close()

            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, ""),
            )
            logging.info("Windows service stopped")


def configure_service_python_path(*_install_options):
    if win32serviceutil is None:
        raise RuntimeError("Windows service installation requires pywin32")
    win32serviceutil.SetServiceCustomOption(
        FlaskWindowsService._svc_name_,
        "PythonPath",
        os.path.dirname(os.path.abspath(__file__)),
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if os.name != "nt":
            raise RuntimeError("Windows service commands are only supported on Windows")
        if win32serviceutil is None:
            raise RuntimeError(
                "Windows service commands require pywin32; install it with "
                "'python -m pip install pywin32'"
            )
        service_class_string = (
            f"{os.path.splitext(os.path.abspath(__file__))[0]}."
            "FlaskWindowsService"
        )
        win32serviceutil.HandleCommandLine(
            FlaskWindowsService,
            serviceClassString=service_class_string,
            customOptionHandler=configure_service_python_path,
        )
    else:
        app = create_app()
        host, port = get_server_address()
        app.run(host=host, port=port)
