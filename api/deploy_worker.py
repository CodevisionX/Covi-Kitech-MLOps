import os
import sys
import logging
import bentoml
import traceback

# 로그 설정
logging.basicConfig(level=logging.DEBUG)

def build_process():
    model_uri = os.getenv("MODEL_URI")
    deployment_id = os.getenv("DEPLOYMENT_ID")
    
    model_type = os.getenv("MODEL_TYPE")
    
    print(f">>> [BUILDER] 모델 수입 시작: {model_uri}", flush=True)

    try:
        # 환경 변수나 강제 설정 없이 순수하게 실행
        # BentoML이 알아서 /var/run/docker.sock을 감지하거나 
        # 로컬 파일 시스템을 사용합니다.
        bento_model = bentoml.mlflow.import_model(
            name=f"model_dep_{deployment_id}",
            model_uri=model_uri,
            labels={
                "model_type": model_type
            }
        )

        bento_model.info.metadata["model_type"] = model_type
        bento_model.flush()
        
        print(f">>> [BUILDER] 수입 및 라벨 주입 완료: {bento_model.tag}")
        print(f"DEBUG: Saved Labels -> {bento_model.info.labels}")
        
    except Exception as e:
        print(f">>> [BUILDER] 에러 발생: {str(e)}", flush=True)
        traceback.print_exc()

if __name__ == "__main__":
    build_process()