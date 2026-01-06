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
    
    print(f">>> [BUILDER] 모델 수입 시작: {model_uri}", flush=True)

    try:
        # 환경 변수나 강제 설정 없이 순수하게 실행
        # BentoML이 알아서 /var/run/docker.sock을 감지하거나 
        # 로컬 파일 시스템을 사용합니다.
        bento_model = bentoml.mlflow.import_model(
            name=f"model_dep_{deployment_id}",
            model_uri=model_uri
        )
        print(f">>> [BUILDER] 수입 완료 성공: {bento_model.tag}", flush=True)
        
    except Exception as e:
        print(f">>> [BUILDER] 에러 발생: {str(e)}", flush=True)
        traceback.print_exc()

if __name__ == "__main__":
    build_process()