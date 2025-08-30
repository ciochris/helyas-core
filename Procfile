web: gunicorn -w 1 -k uvicorn.workers.UvicornWorker backend.synapse_brain:app --timeout 120 --graceful-timeout 30
