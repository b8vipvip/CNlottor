# CNlottor architecture

CNlottor v0.3 separates the system into five layers:

1. `core`: lottery rules, normalized draw schemas and SQLite storage.
2. `data_engine`: providers, parsing, validation and synchronization.
3. `model_engine`: generic PyTorch sequence encoder and lottery-aware output heads.
4. `analysis_engine`: statistics, position-aware rules, Gaussian Copula candidates and rolling backtests.
5. `api` plus Flutter clients: service boundary for Windows and Android.

The Android application is intentionally a client. PyTorch training remains on the Python service because native Android is not a reliable environment for the full training stack. Windows can run the service locally; Android connects over LAN or HTTPS.
