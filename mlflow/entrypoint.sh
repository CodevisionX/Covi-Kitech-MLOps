#!/bin/sh
# MLflow 서버 시작 전 DB 스키마 업그레이드.
# - 새 DB: 서버가 최초 실행 시 테이블을 만들므로 아무것도 하지 않습니다.
# - 기존 DB(이전 버전 스키마): `mlflow db upgrade` 로 현재 버전 스키마로 올립니다.
# MLFLOW_AUTO_DB_UPGRADE=false 로 끌 수 있습니다.
set -e

BACKEND_URI=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--backend-store-uri" ]; then BACKEND_URI="$arg"; fi
  case "$arg" in --backend-store-uri=*) BACKEND_URI="${arg#*=}";; esac
  prev="$arg"
done

if [ "${MLFLOW_AUTO_DB_UPGRADE:-true}" = "true" ] && [ -n "$BACKEND_URI" ]; then
  case "$BACKEND_URI" in
    postgresql*|mysql*|sqlite*|mssql*)
      # 종료 코드: 10 = 기존 스키마 있음, 0 = 새 DB, 그 외 = 확인 실패
      set +e
      python - "$BACKEND_URI" <<'PY'
import sys
import sqlalchemy as sa
engine = sa.create_engine(sys.argv[1])
sys.exit(10 if sa.inspect(engine).has_table("alembic_version") else 0)
PY
      rc=$?
      set -e
      if [ "$rc" -eq 10 ]; then
        echo "[mlflow-entrypoint] 기존 DB 스키마를 확인했습니다. mlflow db upgrade 를 실행합니다."
        mlflow db upgrade "$BACKEND_URI"
      elif [ "$rc" -eq 0 ]; then
        echo "[mlflow-entrypoint] 새 DB 입니다. 업그레이드를 건너뜁니다."
      else
        echo "[mlflow-entrypoint] DB 스키마 확인에 실패했습니다 (exit $rc)." >&2
        exit "$rc"
      fi
      ;;
  esac
fi

exec "$@"
