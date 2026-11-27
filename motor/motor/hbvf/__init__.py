"""Paquete HBVF de sentinel: componentes mínimos del informe 14.4.

- ``pattern_catalog.json``: catálogo HG-01..HG-07 (familias, pesos y estados).
- ``behavior_validation``: validación de patrones contra explicaciones legítimas.
- ``mitigation_engine``: mitigaciones no excluyentes, solo texto consultivo (S10).
- ``model_evaluation``: métricas precision/recall/F1 (informe 14.6).
- ``almacen``: persistencia SQLite de fuentes, patrones y decisiones.
"""
