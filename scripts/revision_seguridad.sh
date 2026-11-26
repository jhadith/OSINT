#!/usr/bin/env bash
# Corre en local las mismas revisiones del pipeline DevSecOps (menos CodeQL y ZAP).
# Uso: ./scripts/revision_seguridad.sh   (con el entorno virtual de Python activado)
set -euo pipefail
cd "$(dirname "$0")/.."

paso() { printf '\n== %s\n' "$1"; }

paso "Pruebas del motor"
(cd motor && python -m pytest -q)

paso "Pruebas del backend"
(cd backend && python -m pytest -q)

paso "Bandit (severidad media o alta)"
python -m bandit -q -r backend/app motor/motor -ll

paso "pip-audit"
pip-audit -r backend/requirements.txt

paso "Consola web: lint, build y npm audit"
(cd web && npm ci --no-fund && npm run lint -- src && npm run build && npm audit --audit-level=high)

if command -v gitleaks >/dev/null 2>&1; then
  paso "Gitleaks"
  gitleaks detect --config .gitleaks.toml --no-banner
else
  printf '\n(Gitleaks no está instalado: se omite. Con Docker: docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.21.2 detect --source /repo --config /repo/.gitleaks.toml)\n'
fi

printf '\nTodo en verde.\n'
