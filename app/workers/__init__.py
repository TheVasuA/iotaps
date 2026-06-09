"""IoTAPS background workers package.

The 8 workers defined here are supervised by supervisord (see
infra/supervisor/supervisord.conf) and run in the `workers` Compose service
(Req 30.1). Worker logic is implemented in later tasks; these modules provide
the entrypoints the supervisor launches.
"""
